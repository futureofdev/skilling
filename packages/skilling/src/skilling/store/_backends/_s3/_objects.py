"""Bounded single-object operations; the caller owns SDK lifecycle and credentials."""

from __future__ import annotations

import math
from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING

from ..._protocol import RecoveryRequired, SessionCapacity, SessionScope, StoreError

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

MAX_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class ObjectValue:
    body: bytes
    etag: str


class ConditionalFailure(Exception):
    """A rejected conditional write never authorizes rebasing."""


class ReadUnavailable(StoreError):
    """A transport failure prevented observation of the current object."""


class UncertainWrite(Exception):
    """A write may have reached the server; do not retry it automatically."""


def digest(component: str) -> str:
    return sha256(component.encode("utf-8")).hexdigest()


def stream_key(scope: SessionScope) -> str:
    return f"streams/{digest(scope.namespace)}/{digest(scope.course_id)}/{digest(scope.learner_id)}"


class Objects:
    def __init__(self, client: S3Client, bucket: str, prefix: str) -> None:
        if not isinstance(bucket, str) or not bucket or "/" in bucket:
            raise ValueError("S3 requires an explicit bucket")
        if (
            not isinstance(prefix, str)
            or not prefix
            or prefix.startswith("/")
            or any(part in ("", ".", "..") for part in prefix.rstrip("/").split("/"))
            or len(prefix.encode()) > 512
            or any(ord(c) < 32 for c in prefix)
        ):
            raise ValueError("S3 requires a nonempty bounded isolated prefix")
        config = client.meta.config
        # Botocore creates these documented attributes dynamically; its stubs omit them.
        retries = config.retries  # type: ignore[attr-defined]
        if not retries or retries.get("total_max_attempts") != 1:
            raise ValueError('S3 client must use retries={"total_max_attempts": 1}')
        timeouts = (config.connect_timeout, config.read_timeout)  # type: ignore[attr-defined]
        for timeout in timeouts:
            if (
                not isinstance(timeout, (int, float))
                or not math.isfinite(timeout)
                or not 0 < timeout <= 60
            ):
                raise ValueError("S3 client waits must be positive and at most 60 seconds")
        self.client, self.bucket, self.prefix = client, bucket, prefix.rstrip("/") + "/"

    def get(self, key: str) -> ObjectValue | None:
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self.prefix + key)
            body = response["Body"]
            try:
                raw = body.read(MAX_BYTES + 1)
            finally:
                body.close()
            if len(raw) > MAX_BYTES:
                raise SessionCapacity("S3 object exceeds the 16 MiB aggregate limit")
            etag = response.get("ETag")
            if not etag:
                raise RecoveryRequired("S3 object has no opaque ETag")
            return ObjectValue(raw, etag)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                return None
            raise ReadUnavailable("S3 read failed; inspect the selected endpoint") from None
        except BotoCoreError:
            raise ReadUnavailable("S3 read failed; inspect the selected endpoint") from None

    def put(self, key: str, raw: bytes, etag: str | None = None) -> None:
        from botocore.exceptions import BotoCoreError, ClientError

        if len(raw) > MAX_BYTES:
            raise SessionCapacity("S3 aggregate exceeds the 16 MiB limit; no write attempted")
        try:
            if etag is None:
                self.client.put_object(
                    Bucket=self.bucket,
                    Key=self.prefix + key,
                    Body=raw,
                    ContentType="application/json",
                    IfNoneMatch="*",
                )
            else:
                self.client.put_object(
                    Bucket=self.bucket,
                    Key=self.prefix + key,
                    Body=raw,
                    ContentType="application/json",
                    IfMatch=etag,
                )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if code in (
                "PreconditionFailed",
                "ConditionalRequestConflict",
                "NoSuchKey",
            ) or status in (409, 412, 404):
                raise ConditionalFailure from None
            if status is not None and status < 500:
                raise StoreError("S3 write refused by selected endpoint") from None
            raise UncertainWrite from None
        except BotoCoreError:
            raise UncertainWrite from None

    def keys(self, subprefix: str = "") -> tuple[str, ...]:
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            pages = self.client.get_paginator("list_objects_v2").paginate(
                Bucket=self.bucket, Prefix=self.prefix + subprefix
            )
            keys: list[str] = []
            for page in pages:
                for entry in page.get("Contents", ()):
                    key = entry.get("Key")
                    if key is None or not key.startswith(self.prefix + subprefix):
                        raise RecoveryRequired("S3 inventory escaped selected prefix")
                    keys.append(key[len(self.prefix) :])
            if len(keys) != len(set(keys)):
                raise RecoveryRequired("S3 inventory contains duplicate keys")
            return tuple(sorted(keys))
        except (BotoCoreError, ClientError):
            raise StoreError("S3 inventory failed; inspect the selected endpoint") from None
