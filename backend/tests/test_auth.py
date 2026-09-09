import pytest
from conftest import login
from redis.exceptions import ConnectionError

from app.core.config import Settings


def test_login_cookie_and_logout_destroy_session(env):
    result = login(env)
    cookie = result.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert "max-age=3600" in cookie
    saved_cookie = env.client.cookies.get("tenantfiles_dev")
    assert env.client.get("/api/me").status_code == 200
    assert (
        env.client.post("/api/auth/logout", headers={"Origin": "http://testserver"}).status_code
        == 204
    )
    env.client.cookies.set("tenantfiles_dev", saved_cookie)
    assert env.client.get("/api/me").status_code == 401


def test_login_rotates_old_session(env):
    login(env)
    old = env.client.cookies.get("tenantfiles_dev")
    login(env, "atlas")
    assert env.client.get("/api/me").json()["customer"]["id"] == "atlas"
    env.client.cookies.clear()
    env.client.cookies.set("tenantfiles_dev", old)
    assert env.client.get("/api/me").status_code == 401


@pytest.mark.parametrize(
    "origin", [None, "https://evil.example", "http://testserver.evil.example", "null"]
)
def test_login_and_logout_require_exact_origin(env, origin):
    headers = {"Origin": origin} if origin else {}
    assert (
        env.client.post(
            "/api/auth/login", json={"api_key": env.keys["amy"]}, headers=headers
        ).status_code
        == 403
    )
    assert env.client.post("/api/auth/logout", headers=headers).status_code == 403


def test_cross_site_read_rejected_and_no_cors(env):
    login(env)
    for headers in [{"Origin": "https://evil.example"}, {"Sec-Fetch-Site": "cross-site"}]:
        r = env.client.get("/api/files", headers=headers)
        assert r.status_code == 403
        assert "access-control-allow-origin" not in r.headers


def test_invalid_key_validation_never_reflects_secret(env):
    key = "TOP-SECRET-DO-NOT-REFLECT" * 20
    r = env.client.post(
        "/api/auth/login", json={"api_key": key}, headers={"Origin": "http://testserver"}
    )
    assert r.status_code == 422 and "TOP-SECRET" not in r.text
    for bad in ["bad", env.keys["amy"][:-1] + "!", "tf_" + "a" * 32 + "." + "x" * 43]:
        r = env.client.post(
            "/api/auth/login", json={"api_key": bad}, headers={"Origin": "http://testserver"}
        )
        assert r.status_code == 401


def test_login_rate_limit_returns_retry_after(env):
    env.settings.login_limit_per_minute = 2
    assert login(env).status_code == 200
    assert login(env).status_code == 200
    r = login(env)
    assert r.status_code == 429 and r.headers["retry-after"] == "60"


def test_customer_rate_limit(env):
    login(env)
    env.settings.request_limit_per_minute = 1
    assert env.client.get("/api/me").status_code == 200
    assert env.client.get("/api/files").status_code == 429


def test_redis_failure_is_fail_closed(env, monkeypatch):
    login(env)

    def broken(*args, **kwargs):
        raise ConnectionError("internal redis credential must not leak")

    monkeypatch.setattr(env.redis, "get", broken)
    r = env.client.get("/api/files")
    assert r.status_code == 503 and "credential" not in r.text
    monkeypatch.setattr(env.redis, "eval", broken)
    assert login(env).status_code == 503


def test_session_ttl_enforced(env):
    login(env)
    session_key = next(env.redis.scan_iter("session:*"))
    assert 0 < env.redis.ttl(session_key) <= 3600
    env.redis.delete(session_key)
    assert env.client.get("/api/me").status_code == 401


def test_host_header_is_validated(env):
    assert env.client.get("/health/live", headers={"Host": "evil.example"}).status_code == 400


def test_ready_checks_dependencies(env, monkeypatch):
    assert env.client.get("/health/live").status_code == 200
    assert env.client.get("/health/ready").status_code == 200

    def broken():
        raise ConnectionError("offline")

    monkeypatch.setattr(env.redis, "ping", broken)
    assert env.client.get("/health/ready").status_code == 503
    assert env.client.get("/health/live").status_code == 200


@pytest.mark.parametrize(
    "overrides",
    [
        {"public_origin": "http://portal.example.com"},
        {"s3_mode": "local"},
        {"database_url": "sqlite:///bad.db"},
        {"s3_endpoint_url": "http://s3"},
        {"app_secret": "x" * 40},
        {"allowed_hosts": ["*"]},
    ],
)
def test_production_rejects_unsafe_settings(overrides):
    kwargs = dict(
        environment="production",
        public_origin="https://portal.example.com",
        app_secret="abcdef0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        database_url="postgresql+psycopg://user:pass@db/tenantfiles?sslmode=verify-full",
        redis_url="rediss://redis:6379/0",
        s3_mode="sts",
    )
    kwargs.update(overrides)
    with pytest.raises(ValueError):
        Settings(_env_file=None, **kwargs)


def test_secure_cookie_prefix():
    settings = Settings(
        _env_file=None, app_secret="x" * 40, public_origin="https://portal.example.com"
    )
    assert settings.secure_cookie and settings.cookie_name == "__Host-tenantfiles"


def test_app_secret_rotation_invalidates_existing_session_and_key(env):
    from pydantic import SecretStr

    login(env)
    env.settings.app_secret = SecretStr("rotated-secret-abcdefghijklmnopqrstuvwxyz-123456")
    assert env.client.get("/api/me").status_code == 401
    assert env.client.get("/api/me", headers={"X-API-Key": env.keys["amy"]}).status_code == 401


def test_production_requires_verified_database_and_redis_tls():
    kwargs = dict(
        environment="production",
        public_origin="https://portal.example.com",
        app_secret="abcdef0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        database_url="postgresql+psycopg://user:pass@db/tenantfiles?sslmode=verify-full",
        redis_url="rediss://redis:6379/0",
        s3_mode="sts",
    )
    assert Settings(_env_file=None, **kwargs).secure_cookie
    for override in [
        {"database_url": "postgresql+psycopg://user:pass@db/tenantfiles"},
        {"redis_url": "redis://redis:6379/0"},
        {"app_secret": "REPLACE_WITH_RANDOM_64_HEX_CHARACTERS"},
    ]:
        with pytest.raises(ValueError):
            Settings(_env_file=None, **{**kwargs, **override})
