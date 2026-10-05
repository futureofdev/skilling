"""Own isolated Compose fixtures and private configs; never adopt existing resources."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

COMPOSE = Path(__file__).with_name("compose.yaml")
PROJECT = re.compile(r"skilling-persistence-[0-9a-f]{24}\Z")


@dataclass(frozen=True)
class Fixture:
    schema_version: int
    profile: str
    project: str
    owner: str
    password: str
    endpoint: str = ""
    port: int = 0
    bucket: str = "skilling-test"
    prefix: str = ""
    region: str = "us-east-1"
    access_key: str = "local-test"
    secret_key: str = "local-test"

    @classmethod
    def load(cls, path: Path, profile: str) -> Fixture:
        value = cls(**json.loads(path.read_text()))
        if (
            value.schema_version != 1
            or value.profile != profile
            or not PROJECT.fullmatch(value.project)
            or value.owner != str(path.resolve())
        ):
            raise ValueError("Fixture configuration does not own these resources")
        return value


def compose(fixture: Fixture, *args: str, timeout: int = 120) -> str:
    env = dict(os.environ, PERSISTENCE_POSTGRES_PASSWORD=fixture.password)
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(COMPOSE),
            "-p",
            fixture.project,
            "--profile",
            fixture.profile,
            *args,
        ],
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode:
        # Docker errors can echo resolved configuration, so never print raw output.
        raise RuntimeError(f"Docker Compose {args[0]} failed (exit {result.returncode})")
    return result.stdout.strip()


def write_config(path: Path, value: Fixture, *, exclusive: bool) -> None:
    flags = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if exclusive else os.O_TRUNC)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w") as output:
        json.dump(asdict(value), output, indent=2)
        output.write("\n")


def wait_s3(endpoint: str) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            with urlopen(endpoint, timeout=2) as response:
                if response.status == 200:
                    return
        except HTTPError as exc:
            if exc.code == 403:
                return
        except (URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(0.25)
    raise RuntimeError("SeaweedFS endpoint did not become available within 60 seconds")


def create_local_bucket(fixture: Fixture) -> None:
    """Provision only our anonymous, task-owned SeaweedFS endpoint."""
    if fixture.profile != "seaweed" or not fixture.endpoint.startswith("http://127.0.0.1:"):
        raise ValueError("Bucket provisioning is restricted to the local SeaweedFS fixture")
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            request = Request(fixture.endpoint + "/" + fixture.bucket, method="PUT")
            with urlopen(request, timeout=2) as response:
                if response.status == 200:
                    return
        except HTTPError as exc:
            if exc.code < 500:
                raise RuntimeError("Local SeaweedFS bucket provisioning was refused") from None
        except (URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(0.25)
    raise RuntimeError("Local SeaweedFS bucket did not become ready within 60 seconds")


def start(profile: str, path: Path) -> None:
    path = path.resolve()
    token = secrets.token_hex(12)
    fixture = Fixture(
        1,
        profile,
        "skilling-persistence-" + token,
        str(path),
        secrets.token_urlsafe(24),
        prefix="run-" + token + "/",
    )
    write_config(path, fixture, exclusive=True)
    try:
        compose(fixture, "up", "-d", "--wait", "--wait-timeout", "90", profile, timeout=240)
        internal_port = "5432" if profile == "postgres" else "8333"
        address = compose(fixture, "port", profile, internal_port)
        if not address.startswith("127.0.0.1:"):
            raise RuntimeError("Fixture must bind exclusively to IPv4 loopback")
        port = int(address.rsplit(":", 1)[1])
        fixture = Fixture(
            **(asdict(fixture) | {"port": port, "endpoint": f"http://127.0.0.1:{port}"})
        )
        if profile == "seaweed":
            wait_s3(fixture.endpoint)
            version = compose(fixture, "exec", "-T", "seaweed", "weed", "version")
            if not re.search(r"\b4\.48\b", version):
                raise RuntimeError("Unexpected SeaweedFS version")
            create_local_bucket(fixture)
        else:
            version = compose(
                fixture,
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "skilling_test",
                "-d",
                "skilling_test",
                "-Atc",
                "SHOW server_version",
            )
            if not version.startswith("17.11"):
                raise RuntimeError("Unexpected PostgreSQL version")
        write_config(path, fixture, exclusive=False)
        print(f"Started {profile} {version.strip()} on loopback; private config: {path}")
    except BaseException:
        # Retain the ownership file if cleanup fails, so recovery remains explicit.
        compose(fixture, "down", "--volumes", "--remove-orphans")
        path.unlink()
        raise


def stop(profile: str, path: Path) -> None:
    fixture = Fixture.load(path, profile)
    ids = compose(fixture, "ps", "-aq")
    if ids:
        for container in ids.splitlines():
            result = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    '{{index .Config.Labels "com.docker.compose.project"}}',
                    container,
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=15,
            )
            if result.stdout.strip() != fixture.project:
                raise ValueError("Container ownership differs from fixture manifest")
    compose(fixture, "down", "--volumes", "--remove-orphans")
    path.unlink()
    print(f"Stopped task-owned {profile} fixture")


def restart(profile: str, path: Path) -> None:
    fixture = Fixture.load(path, profile)
    compose(fixture, "restart", profile, timeout=90)
    port = int(
        compose(fixture, "port", profile, "5432" if profile == "postgres" else "8333").rsplit(
            ":", 1
        )[1]
    )
    fixture = Fixture(**(asdict(fixture) | {"port": port, "endpoint": f"http://127.0.0.1:{port}"}))
    if profile == "seaweed":
        wait_s3(fixture.endpoint)
    else:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                compose(
                    fixture,
                    "exec",
                    "-T",
                    "postgres",
                    "pg_isready",
                    "-U",
                    "skilling_test",
                    "-d",
                    "skilling_test",
                    timeout=5,
                )
                break
            except RuntimeError:
                time.sleep(0.25)
        else:
            raise RuntimeError("PostgreSQL did not restart within 60 seconds")
    write_config(path, fixture, exclusive=False)
    print(f"Restarted task-owned {profile}; reload private config for its current loopback port")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("start", "stop", "restart"))
    parser.add_argument("--profile", choices=("postgres", "seaweed"), required=True)
    parser.add_argument("--config-out", type=Path)
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    if args.command == "start":
        if args.config_out is None or args.config is not None:
            parser.error("start requires --config-out and forbids --config")
        start(args.profile, args.config_out)
    else:
        if args.config is None or args.config_out is not None:
            parser.error("stop/restart requires --config and forbids --config-out")
        if args.command == "restart":
            restart(args.profile, args.config)
        else:
            stop(args.profile, args.config)


if __name__ == "__main__":
    main()
