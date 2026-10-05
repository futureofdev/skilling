"""Verify raw endpoint preconditions before exercising Skilling's adapter."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from ._support import endpoint_fixture


def test_raw_conditional_create_update_and_coherent_body(request: pytest.FixtureRequest) -> None:
    if request.config.getoption("--store-profile", default=None) not in ("aws", "seaweed"):
        pytest.skip("Real S3 capability probe requires an explicit endpoint profile")
    from botocore.exceptions import ClientError

    endpoint = endpoint_fixture(request)
    client, bucket = endpoint.client, endpoint.bucket
    key = endpoint.prefix + "/raw-capability"
    barrier = Barrier(2)

    def create(body: bytes) -> str:
        barrier.wait(timeout=10)
        try:
            client.put_object(Bucket=bucket, Key=key, Body=body, IfNoneMatch="*")
            return "created"
        except ClientError as error:
            assert error.response.get("ResponseMetadata", {}).get("HTTPStatusCode") in (409, 412)
            return "refused"

    with ThreadPoolExecutor(2) as workers:
        assert sorted(workers.map(create, (b"first", b"second"))) == ["created", "refused"]
    response = client.get_object(Bucket=bucket, Key=key)
    etag = response["ETag"]
    try:
        assert response["Body"].read() in (b"first", b"second")
    finally:
        response["Body"].close()
    with pytest.raises(ClientError) as duplicate:
        client.put_object(Bucket=bucket, Key=key, Body=b"duplicate", IfNoneMatch="*")
    assert duplicate.value.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 412
    updated = client.put_object(Bucket=bucket, Key=key, Body=b"updated", IfMatch=etag)
    with pytest.raises(ClientError) as stale:
        client.put_object(Bucket=bucket, Key=key, Body=b"stale", IfMatch=etag)
    assert stale.value.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 412
    response = client.get_object(Bucket=bucket, Key=key)
    try:
        assert response["Body"].read() == b"updated"
        assert response["ETag"] == updated["ETag"]
    finally:
        response["Body"].close()
