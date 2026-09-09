from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict
from contextlib import contextmanager

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from itsdangerous import BadData, URLSafeTimedSerializer

from app.core.config import Settings
from app.core.errors import ErrorKind, ServiceError
from app.model import Customer
from app.util.paths import relative_path, scoped_key


def tenant_policy(customer: Customer, region: str) -> dict:
    bucket_arn = f"arn:aws:s3:::{customer.bucket}"
    statements = [
        {
            "Effect": "Allow",
            "Action": "s3:ListBucket",
            "Resource": bucket_arn,
            "Condition": {"StringLike": {"s3:prefix": [customer.prefix + "*"]}},
        },
        {
            "Effect": "Allow",
            "Action": "s3:GetObject",
            "Resource": f"{bucket_arn}/{customer.prefix}*",
        },
    ]
    if customer.kms_key_arn:
        statements.append(
            {
                "Effect": "Allow",
                "Action": "kms:Decrypt",
                "Resource": customer.kms_key_arn,
                "Condition": {"StringEquals": {"kms:ViaService": f"s3.{region}.amazonaws.com"}},
            }
        )
    return {"Version": "2012-10-17", "Statement": statements}


@contextmanager
def translate_s3_errors():
    try:
        yield
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"NoSuchKey", "404", "AccessDenied", "403", "NoSuchBucket"}:
            # Dışarıya bucket adı, AWS hata metni veya başka müşterinin varlığı sızmaz.
            raise ServiceError(ErrorKind.NOT_FOUND, "Dosya veya klasör bulunamadı") from exc
        if code in {"PreconditionFailed", "412"}:
            raise ServiceError(
                ErrorKind.CONFLICT, "Dosya değişti. Lütfen yeniden deneyin."
            ) from exc
        if code == "InvalidObjectState":
            raise ServiceError(
                ErrorKind.CONFLICT, "Dosya arşivde. Yöneticinizden geri yükleme isteyin."
            ) from exc
        raise ServiceError(
            ErrorKind.UNAVAILABLE, "Depolama servisi geçici olarak kullanılamıyor"
        ) from exc
    except BotoCoreError as exc:
        raise ServiceError(ErrorKind.UNAVAILABLE, "Depolama servisine ulaşılamıyor") from exc


class S3Repository:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.signer = URLSafeTimedSerializer(
            settings.app_secret.get_secret_value(), salt="s3-cursor"
        )
        self._clients: OrderedDict[tuple, tuple[float, object]] = OrderedDict()
        self._lock = threading.Lock()
        self.config = Config(
            connect_timeout=5,
            read_timeout=30,
            retries={"max_attempts": 3, "mode": "standard"},
            max_pool_connections=32,
        )

    def client(self, customer: Customer):
        # Cache anahtarı tüm yetki bağlamını içerir; A müşterisinin client'ı B'ye verilmez.
        cache_key = (
            customer.id,
            customer.bucket,
            customer.prefix,
            customer.role_arn,
            customer.external_id,
            customer.kms_key_arn,
        )
        with self._lock:
            cached = self._clients.get(cache_key)
            if cached and cached[0] > time.monotonic():
                self._clients.move_to_end(cache_key)
                return cached[1]
            session = boto3.session.Session(region_name=self.settings.aws_region)
            if self.settings.s3_mode == "local":
                client = session.client(
                    "s3", endpoint_url=self.settings.s3_endpoint_url, config=self.config
                )
            else:
                if not customer.role_arn or not customer.external_id:
                    raise ServiceError(
                        ErrorKind.UNAVAILABLE, "Müşteri depolama ayarları tamamlanmamış"
                    )
                with translate_s3_errors():
                    sts = session.client("sts", config=self.config)
                    try:
                        result = sts.assume_role(
                            RoleArn=customer.role_arn,
                            ExternalId=customer.external_id,
                            RoleSessionName=f"tenant-{customer.id}",
                            DurationSeconds=900,
                            Policy=json.dumps(
                                tenant_policy(customer, self.settings.aws_region),
                                separators=(",", ":"),
                            ),
                        )
                    finally:
                        sts.close()
                creds = result["Credentials"]
                client = session.client(
                    "s3",
                    config=self.config,
                    aws_access_key_id=creds["AccessKeyId"],
                    aws_secret_access_key=creds["SecretAccessKey"],
                    aws_session_token=creds["SessionToken"],
                )
            # 15 dakikalık credential'ı 10 dakika tutarız; cache sınırsız büyümez.
            self._clients[cache_key] = (time.monotonic() + 600, client)
            if len(self._clients) > 256:
                self._clients.popitem(last=False)
            return client

    def list(self, customer: Customer, path: str, cursor: str | None, limit: int) -> dict:
        prefix = scoped_key(customer.prefix, path, folder=True)
        scope = [customer.id, customer.bucket, prefix]
        kwargs = {"Bucket": customer.bucket, "Prefix": prefix, "Delimiter": "/", "MaxKeys": limit}
        if cursor:
            try:
                payload = self.signer.loads(cursor, max_age=900)
                if payload["scope"] != scope:
                    raise BadData("wrong scope")
                kwargs["ContinuationToken"] = payload["token"]
            except (BadData, KeyError, TypeError) as exc:
                raise ServiceError(
                    ErrorKind.INVALID_INPUT, "Sayfalama süresi dolmuş veya geçersiz. Yenileyin."
                ) from exc
        with translate_s3_errors():
            result = self.client(customer).list_objects_v2(**kwargs)
        folders = []
        files = []
        for item in result.get("CommonPrefixes", []):
            key = item["Prefix"]
            if not key.startswith(prefix):
                continue
            relative = key[len(customer.prefix) :]
            try:
                relative_path(relative, folder=True)
            except ServiceError:
                continue
            folders.append({"name": relative.rstrip("/").split("/")[-1], "path": relative})
        for item in result.get("Contents", []):
            key = item["Key"]
            if key.endswith("/") or not key.startswith(prefix):
                continue
            relative = key[len(customer.prefix) :]
            try:
                relative_path(relative)
            except ServiceError:
                continue
            files.append(
                {
                    "name": relative.split("/")[-1],
                    "path": relative,
                    "size": item["Size"],
                    "modified_at": item["LastModified"],
                    "is_csv": relative.lower().endswith(".csv"),
                }
            )
        token = result.get("NextContinuationToken")
        return {
            "path": path,
            "folders": folders,
            "files": files,
            "next_cursor": self.signer.dumps({"scope": scope, "token": token}) if token else None,
        }

    def open_download(self, customer: Customer, path: str):
        key = scoped_key(customer.prefix, path)
        with translate_s3_errors():
            return self.client(customer).get_object(Bucket=customer.bucket, Key=key)

    def read_limited(self, customer: Customer, path: str, limit: int) -> tuple[bytes, int]:
        key = scoped_key(customer.prefix, path)
        client = self.client(customer)
        with translate_s3_errors():
            head = client.head_object(Bucket=customer.bucket, Key=key)
            if head["ContentLength"] > limit:
                raise ServiceError(
                    ErrorKind.TOO_LARGE,
                    "Bu CSV önizleme boyutunu aşıyor. Dosyayı indirebilirsiniz.",
                )
            # HEAD ile GET arasında dosya değişirse önceki boyut kontrolüne güvenemeyiz.
            result = client.get_object(Bucket=customer.bucket, Key=key, IfMatch=head["ETag"])
            body = result["Body"]
            try:
                raw = body.read(limit + 1)
            finally:
                body.close()
        if len(raw) > limit:
            raise ServiceError(ErrorKind.TOO_LARGE, "CSV önizleme boyutunu aşıyor")
        return raw, head["ContentLength"]

    def close(self):
        for _, client in self._clients.values():
            client.close()
        self._clients.clear()
