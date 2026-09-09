"""HTTP sözleşmesini sınar: gerçek endpoint, OpenAPI ve hatalı servis yanıtları."""

import logging
from datetime import datetime

import pytest
from conftest import login

from app.services.files import FileService


def test_customer_contract_only_exposes_public_identity(env):
    response = login(env)
    assert response.status_code == 200
    assert response.json() == {"customer": {"id": "amy", "name": "Amy"}}
    me = env.client.get("/api/me")
    assert me.status_code == 200
    assert set(me.json()) == {"customer", "key_name", "expires_at", "preview_max_bytes"}
    assert me.json()["customer"] == response.json()["customer"]
    datetime.fromisoformat(me.json()["expires_at"])


@pytest.mark.parametrize("extra", ["customer_id", "bucket", "role_arn"])
def test_login_rejects_unknown_fields_without_echoing_values_or_creating_session(env, extra):
    response = env.client.post(
        "/api/auth/login",
        json={"api_key": env.keys["amy"], extra: "private-input-must-not-leak"},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 422
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert "private-input" not in response.text and env.keys["amy"] not in response.text
    assert not list(env.redis.scan_iter("session:*"))
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize("bad_key", [None, 123, True, [], {}])
def test_login_requires_a_string(env, bad_key):
    response = env.client.post(
        "/api/auth/login",
        json={"api_key": bad_key},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 422


def test_response_filters_internal_fields_at_every_nesting_level(env, monkeypatch):
    original_list = FileService.list
    original_preview = FileService.preview

    def list_with_internal_metadata(*args):
        result = original_list(*args)
        result["bucket"] = "internal-bucket-must-not-leak"
        for item in [*result["folders"], *result["files"]]:
            item["role_arn"] = "internal-role-must-not-leak"
        return result

    def preview_with_internal_metadata(*args):
        return {**original_preview(*args), "aws_credentials": "internal-secret-must-not-leak"}

    monkeypatch.setattr(FileService, "list", list_with_internal_metadata)
    monkeypatch.setattr(FileService, "preview", preview_with_internal_metadata)
    login(env)
    folders = env.client.get("/api/files").json()
    assert set(folders) == {"path", "folders", "files", "next_cursor"}
    assert folders["folders"] == [{"name": "2026", "path": "2026/"}]
    response = env.client.get("/api/files", params={"path": "2026/09/berlin/"})
    assert response.status_code == 200
    for item in response.json()["files"]:
        assert set(item) == {"name", "path", "size", "modified_at", "is_csv"}
        assert datetime.fromisoformat(item["modified_at"]).tzinfo is not None
    preview = env.client.get("/api/files/preview", params={"path": "2026/09/berlin/production.csv"})
    assert preview.status_code == 200
    assert set(preview.json()) == {"name", "headers", "rows", "truncated", "row_limit", "size"}
    assert "internal-" not in response.text + preview.text


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("size", -1),
        ("size", "123"),
        ("size", True),
        ("modified_at", "invalid-date"),
        ("is_csv", "true"),
    ],
)
def test_invalid_file_response_is_safe_500_and_does_not_log_payload(
    env, monkeypatch, caplog, field, bad_value
):
    original = FileService.list

    def broken(*args):
        result = original(*args)
        result["files"][0][field] = bad_value
        result["files"][0]["name"] = "private-filename-must-not-leak"
        return result

    monkeypatch.setattr(FileService, "list", broken)
    login(env)
    with caplog.at_level(logging.ERROR, logger="tenantfiles"):
        response = env.client.get("/api/files", params={"path": "2026/09/berlin/"})
    assert response.status_code == 500
    assert response.json() == {
        "detail": "Sunucu yanıtı oluşturulamadı",
        "request_id": response.headers["x-request-id"],
    }
    assert response.headers["cache-control"] == "no-store"
    assert "private-filename" not in response.text + caplog.text
    assert "invalid_response" in caplog.text
    assert response.headers["x-request-id"] in caplog.text


@pytest.mark.parametrize(
    "bad_result",
    [
        {"rows": [[123, "240"]]},
        {"rows": [["missing column"]]},
        {"row_limit": 1},
        {"truncated": "false"},
    ],
)
def test_invalid_preview_response_is_rejected(env, monkeypatch, bad_result):
    original = FileService.preview
    monkeypatch.setattr(FileService, "preview", lambda *args: {**original(*args), **bad_result})
    login(env)
    response = env.client.get(
        "/api/files/preview", params={"path": "2026/09/berlin/production.csv"}
    )
    assert response.status_code == 500
    assert response.json()["detail"] == "Sunucu yanıtı oluşturulamadı"


def test_missing_required_nullable_cursor_is_a_server_error(env, monkeypatch):
    # Optional/null ile "alan hiç yok" farklı sözleşmelerdir; React next_cursor bekler.
    monkeypatch.setattr(FileService, "list", lambda *args: {"path": "", "folders": [], "files": []})
    login(env)
    assert env.client.get("/api/files").status_code == 500


def test_openapi_describes_json_contracts_errors_and_binary_download(env):
    document = env.client.get("/api/openapi.json").json()
    paths = document["paths"]
    for method, path, model in [
        ("get", "/health/live", "LiveResponse"),
        ("get", "/health/ready", "ReadyResponse"),
        ("post", "/api/auth/login", "LoginResponse"),
        ("get", "/api/me", "MeResponse"),
        ("get", "/api/files", "FilePageResponse"),
        ("get", "/api/files/preview", "CsvPreviewResponse"),
    ]:
        operation = paths[path][method]
        assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
            "$ref": f"#/components/schemas/{model}"
        }
        for code in ("422", "500", "503"):
            assert operation["responses"][code]["content"]["application/json"]["schema"] == {
                "$ref": "#/components/schemas/ErrorResponse"
            }
    schemas = document["components"]["schemas"]
    assert schemas["LoginRequest"]["additionalProperties"] is False
    assert set(schemas["CustomerResponse"]["properties"]) == {"id", "name"}
    assert schemas["FileResponse"]["properties"]["modified_at"]["format"] == "date-time"
    assert "next_cursor" in schemas["FilePageResponse"]["required"]
    assert "content" not in paths["/api/auth/logout"]["post"]["responses"]["204"]
    assert paths["/api/files/download"]["get"]["responses"]["200"]["content"] == {
        "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
    }


def test_empty_logout_and_original_download_bytes_are_preserved(env):
    login(env)
    download = env.client.get(
        "/api/files/download", params={"path": "2026/09/berlin/production.csv"}
    )
    assert download.headers["content-type"] == "application/octet-stream"
    assert download.content == b"site,kwh\nberlin,120\nhamburg,240\n"
    logout = env.client.post("/api/auth/logout", headers={"Origin": "http://testserver"})
    assert logout.status_code == 204 and logout.content == b""
