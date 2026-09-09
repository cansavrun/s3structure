from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from conftest import login
from sqlalchemy import select

from app.model import ApiKey, AuditEvent, Customer
from app.services.admin import AdminService
from app.services.auth import AuthService


def test_customer_key_and_audit_rollback_together(env):
    with pytest.raises(RuntimeError, match="cancel"), env.factory.begin() as db:
        service = AdminService(db)
        service.add_customer(
            customer_id="newco", name="New Company", bucket="new-bucket", prefix="newco/"
        )
        service.issue_key(env.settings.app_secret.get_secret_value(), "newco", "New Key", 30)
        service.record_action("add-customer", "newco")
        raise RuntimeError("cancel")
    with env.factory() as db:
        assert db.get(Customer, "newco") is None
        assert db.scalar(select(ApiKey).where(ApiKey.customer_id == "newco")) is None
        assert db.scalar(select(AuditEvent).where(AuditEvent.customer_id == "newco")) is None


def test_admin_service_issues_lists_and_revokes_a_real_key(env):
    secret = env.settings.app_secret.get_secret_value()
    with env.factory.begin() as db:
        service = AdminService(db)
        key, raw = service.issue_key(secret, "amy", "New integration", 30)
        key_id = key.id
        listing = service.list_keys("amy")
        assert raw not in str(listing) and key.digest not in str(listing)
        assert any(item["id"] == key_id for item in listing)
        assert {item["id"] for item in service.list_customers()} == {"amy", "atlas", "private"}
    assert env.client.get("/api/me", headers={"X-API-Key": raw}).status_code == 200
    with env.factory.begin() as db:
        assert AdminService(db).revoke_key(key_id).id == key_id
    assert env.client.get("/api/me", headers={"X-API-Key": raw}).status_code == 401


def test_admin_disable_customer_invalidates_existing_session(env):
    login(env)
    with env.factory.begin() as db:
        AdminService(db).disable_customer("amy")
    assert env.client.get("/api/me").status_code == 401
    with env.factory.begin() as db, pytest.raises(ValueError, match="Aktif müşteri"):
        AdminService(db).issue_key("unused", "amy", "new key", 30)


@pytest.mark.parametrize("method", ["revoke_key", "disable_customer"])
def test_missing_admin_target_is_a_controlled_error(env, method):
    with env.factory.begin() as db, pytest.raises(ValueError, match="bulunamadı"):
        getattr(AdminService(db), method)("missing")


@pytest.mark.parametrize(
    "overrides",
    [
        {"customer_id": "../escape"},
        {"bucket": "Bad Bucket"},
        {"name": " "},
        {"prefix": "../escape"},
        {"role_arn": "not-an-arn"},
        {"external_id": "!"},
        {"kms_key_arn": "bad-kms"},
    ],
)
def test_invalid_customer_registration_does_not_write(env, overrides):
    fields = {
        "customer_id": "newco",
        "name": "New Company",
        "bucket": "new-bucket",
        "prefix": "newco/",
    }
    with env.factory.begin() as db, pytest.raises(ValueError):
        AdminService(db).add_customer(**{**fields, **overrides})
    with env.factory() as db:
        assert db.get(Customer, "newco") is None


@pytest.mark.parametrize("days,name", [(0, "key"), (366, "key"), (30, " ")])
def test_invalid_key_policy_is_rejected(env, days, name):
    with env.factory.begin() as db, pytest.raises(ValueError, match="Geçerlilik"):
        AdminService(db).issue_key("unused", "amy", name, days)


def test_auth_expiry_respects_non_utc_offsets(env, monkeypatch):
    current = datetime(2026, 9, 9, 12, tzinfo=UTC)
    monkeypatch.setattr("app.services.auth.now", lambda: current)
    customers, keys = Mock(), Mock()
    customers.get.return_value = Customer(id="amy", active=True)
    # 14:30+03:00 = 11:30 UTC: geçmiştir; tzinfo'yu değiştirmek yanlışlıkla geçerli yapardı.
    key = ApiKey(
        customer_id="amy",
        revoked_at=None,
        expires_at=datetime(2026, 9, 9, 14, 30, tzinfo=timezone(timedelta(hours=3))),
    )
    keys.get.return_value = key
    service = AuthService(env.settings, customers, keys, Mock(), Mock())
    assert service.principal_for_key("key") is None
    key.expires_at = datetime(2026, 9, 9, 15, 30, tzinfo=timezone(timedelta(hours=3)))
    assert service.principal_for_key("key").customer.id == "amy"
