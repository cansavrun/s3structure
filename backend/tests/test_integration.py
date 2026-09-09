"""Gerçek servisler: yalnızca özel *_test DB ve izole Redis namespace kullanılır."""

import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from redis import Redis
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

from app.core.database import make_database
from app.repository.sessions import RATE_SCRIPT
from app.services.admin import AdminService


@pytest.mark.integration
def test_postgres_migration_and_concurrent_overlapping_registration(monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL gerekli")
    assert make_url(url).database.endswith("_test"), "Yalnızca *_test veritabanı"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("APP_SECRET", "integration-test-secret-1234567890")
    monkeypatch.setenv("ENVIRONMENT", "test")
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    engine, factory = make_database(url)
    try:
        command.upgrade(config, "head")
        assert {"customers", "api_keys", "audit_events"} <= set(inspect(engine).get_table_names())
        with engine.begin() as db:
            db.execute(text("TRUNCATE customers, api_keys, audit_events CASCADE"))

        def register(i):
            try:
                with factory.begin() as db:
                    AdminService(db).add_customer(
                        customer_id=f"customer{i}",
                        name=f"Customer {i}",
                        bucket="integration-bucket",
                        prefix="same/",
                    )
                return "created"
            except ValueError:
                return "conflict"

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(register, [1, 2])) == ["conflict", "created"]
        command.check(config)
        command.downgrade(config, "base")
        assert "customers" not in inspect(engine).get_table_names()
        command.upgrade(config, "head")
    finally:
        engine.dispose()


@pytest.mark.integration
def test_real_redis_rate_counter_is_atomic_under_concurrency():
    url = os.environ.get("TEST_REDIS_URL")
    if not url:
        pytest.skip("TEST_REDIS_URL gerekli")
    client = Redis.from_url(url)
    key = f"integration-test:{secrets.token_hex(16)}"
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            counts = list(pool.map(lambda _: client.eval(RATE_SCRIPT, 1, key, 60), range(32)))
        assert sorted(counts) == list(range(1, 33))
        assert 0 < client.ttl(key) <= 60
    finally:
        client.delete(key)
        client.close()
