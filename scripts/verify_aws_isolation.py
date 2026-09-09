"""Staging AWS kabulü: iki mevcut test dosyası; yalnızca list/head/get, asla yazma/silme yok."""

import argparse
import sys
from functools import partial
from pathlib import Path

from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.core.config import Settings
from app.core.database import make_database
from app.model import Customer
from app.repository.s3 import S3Repository
from app.util.paths import scoped_key


def denied(call):
    try:
        result = call()
    except ClientError as exc:
        if exc.response["Error"]["Code"] in {"AccessDenied", "403"}:
            return
        raise RuntimeError(
            "Ret AccessDenied olmalı; 404 veya başka hata izolasyon kanıtı değildir"
        ) from exc
    if "Body" in result:
        result["Body"].close()
    raise RuntimeError(
        "İZOLASYON HATASI: diğer müşterinin kaynağına erişim başarılı oldu"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--customer-a", required=True)
    parser.add_argument(
        "--path-a",
        required=True,
        help="A'nın mevcut test dosyası, müşteriye göre göreli",
    )
    parser.add_argument("--customer-b", required=True)
    parser.add_argument(
        "--path-b",
        required=True,
        help="B'nin mevcut test dosyası, müşteriye göre göreli",
    )
    args = parser.parse_args()
    if args.customer_a == args.customer_b:
        parser.error("İki farklı müşteri gerekli")
    settings = Settings()
    if settings.s3_mode != "sts":
        parser.error("Bu kabul testi gerçek AWS STS modu gerektirir")
    engine, factory = make_database(settings.database_url.get_secret_value())
    storage = S3Repository(settings)
    try:
        with factory() as db:
            customers = [
                db.get(Customer, args.customer_a),
                db.get(Customer, args.customer_b),
            ]
            if any(customer is None for customer in customers):
                parser.error("Müşteri bulunamadı")
            paths = [args.path_a, args.path_b]
            clients = [storage.client(c) for c in customers]
            # Önce hedef nesnelerin gerçekten var ve doğru sahibince erişilebilir olduğunu kanıtla.
            for customer, path, client in zip(customers, paths, clients, strict=True):
                key = scoped_key(customer.prefix, path)
                client.head_object(Bucket=customer.bucket, Key=key)
                result = client.get_object(Bucket=customer.bucket, Key=key)
                result["Body"].close()  # Dosya içeriği indirilmez/yazdırılmaz.
                client.list_objects_v2(
                    Bucket=customer.bucket, Prefix=customer.prefix, MaxKeys=1
                )
            for index in [0, 1]:
                other = customers[1 - index]
                key = scoped_key(other.prefix, paths[1 - index])
                client = clients[index]
                denied(partial(client.get_object, Bucket=other.bucket, Key=key))
                denied(
                    partial(
                        client.list_objects_v2,
                        Bucket=other.bucket,
                        Prefix=other.prefix,
                        MaxKeys=1,
                    )
                )
        print(
            "PASS: Her müşteri kendi mevcut test nesnesini okudu; çapraz list/get AWS tarafından reddedildi."
        )
    finally:
        storage.close()
        engine.dispose()


if __name__ == "__main__":
    main()
