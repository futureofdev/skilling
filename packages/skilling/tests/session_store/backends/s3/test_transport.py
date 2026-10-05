"""Transport refusal paths supplement, never replace, actual endpoint tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skilling.store import RecoveryRequired, SessionCapacity, SessionSchemaError
from skilling.store._backends._s3 import S3SessionStore
from skilling.store._backends._s3._control import CONTROL, ready
from skilling.store._backends._s3._objects import (
    MAX_BYTES,
    ConditionalFailure,
    Objects,
    UncertainWrite,
)
from skilling.store._protocol import SessionScope


@pytest.fixture
def objects():
    boto3 = pytest.importorskip("boto3")
    from botocore.config import Config

    client = boto3.client(
        "s3",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        config=Config(retries={"total_max_attempts": 1}, connect_timeout=1, read_timeout=1),
        region_name="us-east-1",
    )
    yield Objects(client, "task-test-bucket", "task-prefix")
    client.close()


@pytest.mark.parametrize(
    ("code", "status"),
    [("PreconditionFailed", 412), ("ConditionalRequestConflict", 409), ("NoSuchKey", 404)],
)
def test_conditional_errors_never_retry(objects: Objects, code: str, status: int) -> None:
    from botocore.stub import Stubber

    with Stubber(objects.client) as stub:
        stub.add_client_error("put_object", service_error_code=code, http_status_code=status)
        with pytest.raises(ConditionalFailure):
            objects.put("stream", b"{}", '"opaque-etag"')
        stub.assert_no_pending_responses()


def test_opaque_etag_and_size_boundary(objects: Objects) -> None:
    from botocore.stub import Stubber

    raw = b"x" * MAX_BYTES
    with Stubber(objects.client) as stub:
        stub.add_response(
            "put_object",
            {},
            {
                "Bucket": objects.bucket,
                "Key": objects.prefix + "stream",
                "Body": raw,
                "ContentType": "application/json",
                "IfMatch": '"not-a-digest"',
            },
        )
        objects.put("stream", raw, '"not-a-digest"')
        with pytest.raises(SessionCapacity):
            objects.put("stream", raw + b"x")
        stub.assert_no_pending_responses()


def test_server_error_is_uncertain_and_secret_free(objects: Objects) -> None:
    from botocore.stub import Stubber

    with Stubber(objects.client) as stub:
        stub.add_client_error(
            "put_object",
            service_error_code="InternalError",
            service_message="secret-placeholder",
            http_status_code=500,
        )
        with pytest.raises(UncertainWrite) as error:
            objects.put("stream", b"{}")
        assert "secret-placeholder" not in str(error.value)
        assert error.value.__cause__ is None


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema_version":2}',
        b'{"schema_version":true,"mode":"READY","owner":"x"}',
        b'{"schema_version":1,"mode":"READY","owner":"x","unknown":1}',
    ],
)
def test_corrupt_control_refuses_without_write(objects: Objects, raw: bytes) -> None:
    import io

    from botocore.response import StreamingBody
    from botocore.stub import Stubber

    with Stubber(objects.client) as stub:
        stub.add_response(
            "get_object",
            {"Body": StreamingBody(io.BytesIO(raw), len(raw)), "ETag": '"e"'},
            {"Bucket": objects.bucket, "Key": objects.prefix + CONTROL},
        )
        with pytest.raises(SessionSchemaError):
            ready(objects)
        stub.assert_no_pending_responses()


def test_bad_scope_refuses_before_access(objects: Objects) -> None:
    from botocore.stub import Stubber

    store = S3SessionStore(objects)
    with Stubber(objects.client), pytest.raises(RecoveryRequired):
        store.read(replace(SessionScope("p", "l", "c"), namespace=""))
