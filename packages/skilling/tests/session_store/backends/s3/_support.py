"""Disposable endpoint fixture, selected explicitly and never silently skipped."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from skilling.store._backends._s3 import S3SessionStore

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


@dataclass(frozen=True)
class S3Endpoint:
    client: S3Client
    bucket: str
    prefix: str


@dataclass(frozen=True)
class S3Fixture(S3Endpoint):
    store: S3SessionStore


def endpoint_fixture(request: pytest.FixtureRequest) -> S3Endpoint:
    import boto3
    from botocore.config import Config

    path = request.config.getoption("--store-config", default=None)
    if not path:
        pytest.fail("Explicit S3 service profile requires --store-config")
    values = json.loads(Path(path).read_text())
    profile = request.config.getoption("--store-profile")
    for key in ("bucket", "prefix", "region"):
        if not isinstance(values.get(key), str) or not values[key]:
            pytest.fail(f"S3 service config requires nonempty {key}")
    if values.get("profile") != profile:
        pytest.fail("S3 service profile differs from private configuration")
    if profile == "aws" and not values.get("disposable", False):
        pytest.fail("AWS config must explicitly declare disposable=true")
    if profile == "aws" and values.get("endpoint"):
        pytest.fail("Real AWS verification must use the SDK's regional AWS endpoint")
    session = boto3.Session(profile_name=values.get("credential_profile"))
    client = session.client(
        "s3",
        endpoint_url=values.get("endpoint"),
        region_name=values["region"],
        aws_access_key_id=values.get("access_key") if profile == "seaweed" else None,
        aws_secret_access_key=values.get("secret_key") if profile == "seaweed" else None,
        config=Config(
            retries={"total_max_attempts": 1},
            connect_timeout=5,
            read_timeout=10,
            s3={"addressing_style": "path"},
        ),
    )
    prefix = values["prefix"].rstrip("/") + "/s3-contract-" + uuid4().hex
    fixture = S3Endpoint(client, values["bucket"], prefix)

    def cleanup() -> None:
        pages = client.get_paginator("list_objects_v2").paginate(
            Bucket=fixture.bucket, Prefix=prefix + "/"
        )
        for page in pages:
            for obj in page.get("Contents", ()):
                key = obj.get("Key")
                if key is None or not key.startswith(prefix + "/"):
                    raise RuntimeError("Cleanup key escaped task prefix")
                client.delete_object(Bucket=fixture.bucket, Key=key)
        client.close()

    request.addfinalizer(cleanup)
    return fixture


def s3_fixture(request: pytest.FixtureRequest) -> S3Fixture:
    endpoint = endpoint_fixture(request)
    store = S3SessionStore.open(endpoint.client, endpoint.bucket, endpoint.prefix)
    return S3Fixture(endpoint.client, endpoint.bucket, endpoint.prefix, store)
