"""Müşteri/anahtar yönetimi. Transaction dışarıdaki CLI/UoW tarafından tamamlanır."""

import re
import secrets
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.errors import ServiceError
from app.core.security import mint_key
from app.model import ApiKey, AuditEvent, Customer
from app.repository.api_keys import ApiKeyRepository
from app.repository.audit import AuditRepository
from app.repository.customers import CustomerRepository
from app.util.paths import tenant_prefix
from app.util.time import now


class AdminService:
    def __init__(self, db: Session):
        self.customers = CustomerRepository(db)
        self.keys = ApiKeyRepository(db)
        self.audit = AuditRepository(db)

    def add_customer(
        self,
        *,
        customer_id: str,
        name: str,
        bucket: str,
        prefix: str,
        role_arn: str | None = None,
        external_id: str | None = None,
        kms_key_arn: str | None = None,
    ) -> Customer:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,47}", customer_id):
            raise ValueError("Müşteri ID 2–48 karakter; küçük harf, rakam, _ ve - içermeli")
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket):
            raise ValueError("Geçersiz bucket adı")
        if not name.strip() or len(name) > 160:
            raise ValueError("Müşteri adı 1–160 karakter olmalı")
        try:
            prefix = tenant_prefix(prefix)
        except ServiceError as exc:
            raise ValueError(exc.message) from exc
        if role_arn and not re.fullmatch(
            r"arn:aws:iam::\d{12}:role/[A-Za-z0-9_+=,.@/-]+", role_arn
        ):
            raise ValueError("Geçersiz IAM role ARN")
        if external_id and not re.fullmatch(r"[A-Za-z0-9_+=,.@:/-]{2,128}", external_id):
            raise ValueError("Geçersiz external ID")
        if kms_key_arn and not re.fullmatch(
            r"arn:aws:kms:[a-z0-9-]+:\d{12}:key/[a-z0-9-]+", kms_key_arn
        ):
            raise ValueError("Geçersiz KMS key ARN")
        self.customers.lock_registration()
        if self.customers.get(customer_id):
            raise ValueError("Bu müşteri ID zaten var")
        for existing in self.customers.in_bucket(bucket):
            if existing.prefix.startswith(prefix) or prefix.startswith(existing.prefix):
                raise ValueError("Bu bucket/prefix başka bir müşteri alanıyla çakışıyor")
        customer = Customer(
            id=customer_id,
            name=name.strip(),
            bucket=bucket,
            prefix=prefix,
            role_arn=role_arn,
            external_id=external_id,
            kms_key_arn=kms_key_arn,
        )
        return self.customers.add(customer)

    def issue_key(self, secret: str, customer_id: str, name: str, days: int) -> tuple[ApiKey, str]:
        customer = self.customers.get(customer_id)
        if customer is None or not customer.active:
            raise ValueError("Aktif müşteri bulunamadı")
        if not 1 <= days <= 365 or not name.strip() or len(name) > 160:
            raise ValueError("Geçerlilik 1–365 gün; anahtar adı 1–160 karakter olmalı")
        key_id, raw, hashed = mint_key(secret)
        key = ApiKey(
            id=key_id,
            customer_id=customer_id,
            name=name.strip(),
            digest=hashed,
            expires_at=now() + timedelta(days=days),
        )
        self.keys.add(key)
        return key, raw

    def revoke_key(self, key_id: str) -> ApiKey:
        key = self.keys.get(key_id)
        if key is None:
            raise ValueError("Anahtar bulunamadı")
        key.revoked_at = now()
        return key

    def disable_customer(self, customer_id: str) -> Customer:
        customer = self.customers.get(customer_id)
        if customer is None:
            raise ValueError("Müşteri bulunamadı")
        customer.active = False
        return customer

    def list_customers(self) -> list[dict]:
        return [
            {"id": c.id, "name": c.name, "bucket": c.bucket, "prefix": c.prefix, "active": c.active}
            for c in self.customers.all()
        ]

    def list_keys(self, customer_id: str) -> list[dict]:
        return [
            {
                "id": k.id,
                "name": k.name,
                "expires_at": k.expires_at.isoformat(),
                "revoked": k.revoked_at is not None,
            }
            for k in self.keys.for_customer(customer_id)
        ]

    def record_action(self, command: str, customer_id: str | None = None) -> None:
        self.audit.add(
            AuditEvent(
                action="admin." + command,
                outcome="success",
                request_id=secrets.token_hex(16),
                customer_id=customer_id,
            )
        )
