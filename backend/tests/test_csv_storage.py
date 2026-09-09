import io
import json
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from conftest import login

from app.api.errors import ERROR_STATUS
from app.core.errors import ServiceError
from app.model import Customer
from app.repository.s3 import S3Repository, tenant_policy, translate_s3_errors


def preview_bytes(env, data, name="sample.csv"):
    env.s3.put_object(Bucket="shared-files", Key="amy_c001/" + name, Body=data)
    login(env)
    return env.client.get("/api/files/preview", params={"path": name})


def test_csv_preview(env):
    r = preview_bytes(env, b"site,kwh\nberlin,120\nhamburg,240\n")
    assert r.status_code == 200
    assert r.json()["headers"] == ["site", "kwh"]
    assert r.json()["rows"] == [["berlin", "120"], ["hamburg", "240"]]
    assert r.json()["truncated"] is False


@pytest.mark.parametrize(
    "content,headers,rows",
    [
        (b"\xef\xbb\xbfsite;kwh\nberlin;120\n", ["site", "kwh"], [["berlin", "120"]]),
        (b'a,b\n"hello\nworld","x,y"\n', ["a", "b"], [["hello\nworld", "x,y"]]),
        (b"a\n<script>alert(1)</script>\n", ["a"], [["<script>alert(1)</script>"]]),
        (b"", [], []),
        (b"single\nvalue\n", ["single"], [["value"]]),
    ],
)
def test_csv_edge_cases(env, content, headers, rows):
    r = preview_bytes(env, content)
    assert r.status_code == 200
    assert r.json()["headers"] == headers and r.json()["rows"] == rows


@pytest.mark.parametrize(
    "content", [b"a,b\n\xff,x\n", b"a,b\n\x00,x\n", b'a,b\n"unclosed,x\n', b"a,b\n1,2,3\n"]
)
def test_malformed_csv_rejected(env, content):
    assert preview_bytes(env, content).status_code == 422


def test_preview_limits(env):
    env.settings.preview_max_bytes = 1024
    assert preview_bytes(env, b"a\n" + b"x\n" * 1024).status_code == 413
    env.settings.preview_max_rows = 2
    r = preview_bytes(env, b"a\n1\n2\n3\n")
    assert r.json()["rows"] == [["1"], ["2"]] and r.json()["truncated"]
    env.settings.preview_max_columns = 1
    assert preview_bytes(env, b"a,b\n1,2\n").status_code == 422
    assert preview_bytes(env, b"test", "file.html").status_code == 415


def test_object_change_between_head_and_get_uses_if_match(env, monkeypatch):
    login(env)
    s3 = Mock()
    s3.head_object.return_value = {"ContentLength": 2, "ETag": '"v1"'}
    s3.get_object.side_effect = ClientError({"Error": {"Code": "PreconditionFailed"}}, "GetObject")
    monkeypatch.setattr(env.app.state.resources.storage, "client", lambda c: s3)
    r = env.client.get("/api/files/preview", params={"path": "a.csv"})
    assert r.status_code == 409
    assert s3.get_object.call_args.kwargs["IfMatch"] == '"v1"'


def test_download_stream_closes_body(env, monkeypatch):
    login(env)
    body = io.BytesIO(b"large" * 40000)
    monkeypatch.setattr(
        env.app.state.resources.storage,
        "open_download",
        lambda *args: {"Body": body, "ContentLength": 200000},
    )
    r = env.client.get("/api/files/download", params={"path": "safe.csv"})
    assert len(r.content) == 200000 and body.closed


def test_session_policy_has_exact_prefix_and_no_write_access():
    customer = Customer(id="amy", bucket="shared-files", prefix="amy_c001/", kms_key_arn=None)
    policy = tenant_policy(customer, "eu-central-1")
    assert policy["Statement"][0]["Condition"]["StringLike"]["s3:prefix"] == ["amy_c001/*"]
    assert policy["Statement"][1]["Resource"] == "arn:aws:s3:::shared-files/amy_c001/*"
    assert {s["Action"] for s in policy["Statement"]} == {"s3:ListBucket", "s3:GetObject"}


def test_sts_client_is_scoped_and_cached_per_customer(env, monkeypatch):
    env.settings.s3_mode = "sts"
    storage = S3Repository(env.settings)
    session = Mock()
    sts = Mock()
    sts.assume_role.return_value = {
        "Credentials": {
            "AccessKeyId": "scoped",
            "SecretAccessKey": "secret",
            "SessionToken": "token",
        }
    }
    session.client.side_effect = lambda name, **kw: sts if name == "sts" else Mock()
    monkeypatch.setattr("app.repository.s3.boto3.session.Session", lambda **kw: session)
    amy = Customer(
        id="amy",
        bucket="shared-files",
        prefix="amy_c001/",
        role_arn="arn:aws:iam::123456789012:role/amy",
        external_id="amy-external",
    )
    atlas = Customer(
        id="atlas",
        bucket="shared-files",
        prefix="atlas_c002/",
        role_arn="arn:aws:iam::123456789012:role/atlas",
        external_id="atlas-external",
    )
    first = storage.client(amy)
    assert first is storage.client(amy)
    assert first is not storage.client(atlas)
    assert sts.assume_role.call_count == 2
    call = sts.assume_role.call_args_list[0].kwargs
    assert call["ExternalId"] == "amy-external"
    assert json.loads(call["Policy"])["Statement"][1]["Resource"].endswith("/amy_c001/*")
    storage.close()


@pytest.mark.parametrize(
    "code,status",
    [
        ("AccessDenied", 404),
        ("NoSuchKey", 404),
        ("SlowDown", 503),
        ("InvalidObjectState", 409),
        ("PreconditionFailed", 409),
    ],
)
def test_storage_errors_do_not_leak_aws_details(code, status):
    with pytest.raises(ServiceError) as exc, translate_s3_errors():
        raise ClientError({"Error": {"Code": code, "Message": "private-bucket-name"}}, "GetObject")
    assert ERROR_STATUS[exc.value.kind] == status and "private-bucket" not in exc.value.message


def test_storage_connection_error():
    with pytest.raises(ServiceError) as exc, translate_s3_errors():
        raise EndpointConnectionError(endpoint_url="https://secret")
    assert ERROR_STATUS[exc.value.kind] == 503
