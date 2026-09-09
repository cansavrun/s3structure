from datetime import timedelta
from types import SimpleNamespace

import boto3
import fakeredis
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from app.core.config import Settings
from app.core.database import make_database
from app.core.security import mint_key
from app.main import create_app
from app.model import ApiKey, Base, Customer
from app.util.time import now


@pytest.fixture
def env(tmp_path, monkeypatch):
    for key, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_EC2_METADATA_DISABLED": "true",
    }.items():
        monkeypatch.setenv(key, value)
    settings = Settings(
        _env_file=None,
        app_secret="test-only-secret-do-not-use-in-production-123",
        environment="test",
        s3_mode="local",
        aws_region="us-east-1",
        public_origin="http://testserver",
        login_limit_per_minute=1000,
        request_limit_per_minute=10000,
    )
    engine, factory = make_database(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine)
    redis = fakeredis.FakeRedis(decode_responses=True)
    keys = {}
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="shared-files")
        s3.create_bucket(Bucket="private-files")
        with factory.begin() as db:
            for cid, bucket, prefix in [
                ("amy", "shared-files", "amy_c001/"),
                ("atlas", "shared-files", "atlas_c002/"),
                ("private", "private-files", ""),
            ]:
                db.add(Customer(id=cid, name=cid.title(), bucket=bucket, prefix=prefix))
                db.flush()
                kid, raw, hashed = mint_key(settings.app_secret.get_secret_value())
                db.add(
                    ApiKey(
                        id=kid,
                        customer_id=cid,
                        name="test user",
                        digest=hashed,
                        expires_at=now() + timedelta(days=1),
                    )
                )
                keys[cid] = raw
                for filename, body in [
                    ("production.csv", b"site,kwh\nberlin,120\nhamburg,240\n"),
                    ("note.txt", f"private for {cid}".encode()),
                ]:
                    s3.put_object(
                        Bucket=bucket, Key=f"{prefix}2026/09/berlin/{filename}", Body=body
                    )
            db.flush()
        app = create_app(settings, session_factory=factory, redis_client=redis)
        with TestClient(app) as client:
            yield SimpleNamespace(
                settings=settings,
                factory=factory,
                engine=engine,
                redis=redis,
                s3=s3,
                app=app,
                client=client,
                keys=keys,
            )
        redis.close()
        engine.dispose()


def login(env, customer="amy"):
    return env.client.post(
        "/api/auth/login",
        json={"api_key": env.keys[customer]},
        headers={"Origin": "http://testserver"},
    )
