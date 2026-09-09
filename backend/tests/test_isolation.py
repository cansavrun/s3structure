from datetime import timedelta

import pytest
from conftest import login
from sqlalchemy import select

from app.model import ApiKey, AuditEvent, Customer
from app.services.admin import AdminService
from app.util.time import now

PATH = "2026/09/berlin/production.csv"


def test_authentication_required_for_every_file_route(env):
    for route in [
        "/api/me",
        "/api/files",
        f"/api/files/preview?path={PATH}",
        f"/api/files/download?path={PATH}",
    ]:
        assert env.client.get(route).status_code == 401


@pytest.mark.parametrize("customer", ["amy", "atlas", "private"])
def test_each_customer_sees_own_bucket_or_prefix(env, customer):
    assert login(env, customer).status_code == 200
    root = env.client.get("/api/files").json()
    assert root["folders"] == [{"name": "2026", "path": "2026/"}]
    listing = env.client.get("/api/files", params={"path": "2026/09/berlin/"})
    assert len(listing.json()["files"]) == 2
    download = env.client.get("/api/files/download", params={"path": "2026/09/berlin/note.txt"})
    assert download.content == f"private for {customer}".encode()
    assert "attachment" in download.headers["content-disposition"]
    assert download.headers["content-type"] == "application/octet-stream"
    assert download.headers["cache-control"] == "no-store"
    assert "shared-files" not in str(root)


@pytest.mark.parametrize(
    "path",
    [
        "../atlas_c002/2026/09/berlin/note.txt",
        "/atlas_c002/2026/09/berlin/note.txt",
        "2026/../../../atlas_c002/note.txt",
        "%2e%2e/atlas_c002/a.csv",
        "%252e%252e/atlas_c002/a.csv",
        "..\\atlas_c002\\a.csv",
        "2026//09/a.csv",
        "2026/./09/a.csv",
        "2026/09/\x00x.csv",
        "x\r\nContent-Type:x.csv",
        "*/secret.csv",
        "${aws:username}/x.csv",
        "a?b.csv",
    ],
)
@pytest.mark.parametrize("route", ["/api/files", "/api/files/preview", "/api/files/download"])
def test_path_escape_is_rejected(env, path, route):
    login(env)
    assert env.client.get(route, params={"path": path}).status_code == 400


def test_other_prefix_and_bucket_parameters_cannot_change_scope(env):
    login(env)
    r = env.client.get(
        "/api/files/download",
        params={
            "path": "atlas_c002/2026/09/berlin/note.txt",
            "bucket": "private-files",
            "customer_id": "atlas",
        },
    )
    assert r.status_code == 404
    r = env.client.get(
        "/api/files/download",
        params={
            "path": "2026/09/berlin/note.txt",
            "bucket": "private-files",
            "customer_id": "atlas",
        },
    )
    assert r.content == b"private for amy"


def test_prefix_boundary_amy_does_not_include_amy2(env):
    env.s3.put_object(Bucket="shared-files", Key="amy_c0012/private.csv", Body=b"secret")
    login(env)
    assert "private" not in str(env.client.get("/api/files").json())


def test_cross_tenant_and_cross_folder_cursor_is_rejected(env):
    login(env)
    page = env.client.get("/api/files", params={"path": "2026/09/berlin", "limit": 1}).json()
    token = page["next_cursor"]
    assert token
    second = env.client.get("/api/files", params={"path": "2026/09/berlin/", "cursor": token})
    assert second.status_code == 200
    assert second.json()["files"][0]["name"] != page["files"][0]["name"]
    assert env.client.get("/api/files", params={"cursor": token}).status_code == 400
    login(env, "atlas")
    assert (
        env.client.get(
            "/api/files", params={"path": "2026/09/berlin/", "cursor": token}
        ).status_code
        == 400
    )
    assert env.client.get("/api/files", params={"cursor": token + "tamper"}).status_code == 400


@pytest.mark.parametrize("change", ["revoke", "expire", "disable"])
def test_existing_session_loses_access_immediately_after_admin_change(env, change):
    login(env)
    with env.factory.begin() as db:
        key = db.scalar(select(ApiKey).where(ApiKey.customer_id == "amy"))
        if change == "revoke":
            key.revoked_at = now()
        elif change == "expire":
            key.expires_at = now() - timedelta(seconds=1)
        else:
            db.get(Customer, "amy").active = False
    assert env.client.get("/api/me").status_code == 401
    assert env.client.get("/api/files/download", params={"path": PATH}).status_code == 401


@pytest.mark.parametrize("prefix", ["amy_c001/", "amy_c001/sub/", ""])
def test_overlapping_storage_registration_rejected(env, prefix):
    with env.factory.begin() as db, pytest.raises(ValueError, match="çakışıyor"):
        AdminService(db).add_customer(
            customer_id="intruder", name="Intruder", bucket="shared-files", prefix=prefix
        )


def test_similarly_named_nonoverlapping_tenant_allowed(env):
    with env.factory.begin() as db:
        customer = AdminService(db).add_customer(
            customer_id="amy2", name="Amy 2", bucket="shared-files", prefix="amy_c0012"
        )
        assert customer.prefix == "amy_c0012/"


def test_api_key_auth_without_browser_session_and_keys_are_hashed(env):
    response = env.client.get("/api/me", headers={"X-API-Key": env.keys["amy"]})
    assert response.status_code == 200
    assert response.json()["customer"]["id"] == "amy"
    with env.factory() as db:
        key = db.scalar(select(ApiKey).where(ApiKey.customer_id == "amy"))
        assert key.digest != env.keys["amy"] and len(key.digest) == 64


def test_audit_contains_actor_and_action_but_never_credentials(env):
    login(env)
    env.client.get("/api/files/download", params={"path": PATH})
    with env.factory() as db:
        events = list(db.scalars(select(AuditEvent)))
        assert [e.action for e in events] == ["auth.login", "files.download_authorized"]
        assert all(e.customer_id == "amy" for e in events)
        assert env.keys["amy"] not in str([vars(e) for e in events])
