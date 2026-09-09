"""Katman sınırları, bağımlılık ömürleri ve transport'tan bağımsız iş kuralları."""

import ast
import io
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.core.resources import Resources
from app.main import create_app
from app.model import ApiKey, Customer
from app.model.principal import Principal
from app.services.files import FileService


@pytest.mark.parametrize(
    "layer,forbidden",
    [
        (
            "model",
            {
                "app.api",
                "app.services",
                "app.repository",
                "app.schema",
                "fastapi",
                "redis",
                "boto3",
            },
        ),
        (
            "schema",
            {"app.api", "app.services", "app.repository", "app.model", "fastapi", "sqlalchemy"},
        ),
        ("repository", {"app.api", "app.services", "app.schema", "fastapi", "starlette"}),
        ("services", {"app.api", "fastapi", "starlette", "boto3", "redis"}),
        ("api/routes", {"app.repository", "sqlalchemy", "boto3", "redis"}),
        ("util", {"app.api", "app.services", "app.repository", "app.model", "fastapi"}),
    ],
)
def test_layers_do_not_import_in_the_wrong_direction(layer, forbidden):
    root = Path(__file__).resolve().parents[1] / "app" / layer
    violations = []
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden):
                    violations.append(f"{path.name}:{node.lineno} imports {name}")
    assert not violations, "\n".join(violations)


def test_repository_does_not_commit_callers_transaction():
    root = Path(__file__).resolve().parents[1] / "app" / "repository"
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr != "commit", f"{path.name}:{node.lineno} commits"


def test_two_app_factories_do_not_share_settings_or_credential_scope(env):
    second_settings = env.settings.model_copy(
        update={"app_secret": SecretStr("a-second-independent-application-secret-123456")}
    )
    second = create_app(
        second_settings,
        session_factory=env.factory,
        redis_client=env.redis,
        storage=env.app.state.resources.storage,
    )
    with TestClient(second) as client:
        headers = {"X-API-Key": env.keys["amy"]}
        assert client.get("/api/me", headers=headers).status_code == 401
        assert env.client.get("/api/me", headers=headers).status_code == 200
    assert env.client.get("/api/me", headers=headers).status_code == 200


def test_injected_resources_are_owned_by_the_caller(env):
    storage, redis = Mock(), Mock()
    app = create_app(env.settings, session_factory=env.factory, redis_client=redis, storage=storage)
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
    storage.close.assert_not_called()
    redis.close.assert_not_called()


def test_cleanup_releases_other_resources_when_one_close_fails():
    engine, redis, storage = Mock(), Mock(), Mock()
    storage.close.side_effect = RuntimeError("close failed")
    resources = Resources(
        settings=Mock(),
        session_factory=Mock(),
        redis=redis,
        storage=storage,
        engine=engine,
        owns_redis=True,
        owns_storage=True,
    )
    with pytest.raises(RuntimeError, match="close failed"):
        resources.close()
    redis.close.assert_called_once()
    engine.dispose.assert_called_once()


def test_file_service_closes_stream_if_audit_cannot_be_committed():
    # FastAPI/TestClient/S3 başlatmadan iş kuralını doğrudan sınayabiliriz.
    storage, audit = Mock(), Mock()
    stream = io.BytesIO(b"private-data")
    storage.open_download.return_value = {"Body": stream, "ContentLength": 12}
    audit.record.side_effect = SQLAlchemyError("audit offline")
    service = FileService(storage, audit, Settings(_env_file=None, app_secret="x" * 40))
    principal = Principal(Customer(id="amy", prefix="amy/"), ApiKey(id="test-key"))
    with pytest.raises(SQLAlchemyError):
        service.download(principal, "2026/09/site/data.csv")
    assert stream.closed
    storage.open_download.assert_called_once_with(principal.customer, "2026/09/site/data.csv")


def test_database_failure_response_does_not_expose_sql_or_secrets(env, monkeypatch):
    def unavailable(*args):
        raise SQLAlchemyError("postgresql://private-password@internal-host")

    monkeypatch.setattr("app.services.health.check_database", unavailable)
    response = env.client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "Veritabanına ulaşılamıyor"}
    assert "private-password" not in response.text
