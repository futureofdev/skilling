"""Independent process with a captured expectation and explicit release barrier."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from skilling.store import Conflict
from skilling.store._backends._s3 import S3SessionStore

from ..test_sqlite import SCOPE, mutation


def main() -> None:
    import boto3
    from botocore.config import Config

    config_path, prefix, directory, number = sys.argv[1:]
    config = json.loads(Path(config_path).read_text())
    session = boto3.Session(profile_name=config.get("credential_profile"))
    client = session.client(
        "s3",
        endpoint_url=config.get("endpoint"),
        region_name=config["region"],
        aws_access_key_id=config.get("access_key"),
        aws_secret_access_key=config.get("secret_key"),
        config=Config(
            retries={"total_max_attempts": 1},
            connect_timeout=5,
            read_timeout=10,
            s3={"addressing_style": "path"},
        ),
    )
    root = Path(directory)
    try:
        store = S3SessionStore.open(client, config["bucket"], prefix)
        command = mutation(store.read(SCOPE))
        (root / f"ready-{number}").touch()
        deadline = time.monotonic() + 30
        while not (root / "release").exists():
            if time.monotonic() > deadline:
                raise RuntimeError("Worker release timed out")
            time.sleep(0.01)
        try:
            store.commit(command)
            result = "accepted"
        except Conflict:
            result = "conflict"
        (root / f"result-{number}").write_text(result)
    finally:
        client.close()


if __name__ == "__main__":
    main()
