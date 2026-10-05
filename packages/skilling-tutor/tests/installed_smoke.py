"""Install matching local core/tutor wheel and sdist pairs outside the checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
import zipfile
from datetime import UTC, datetime
from email.parser import BytesParser
from pathlib import Path


def _environment() -> dict[str, str]:
    environment = dict(os.environ)
    virtual_environment = environment.get("VIRTUAL_ENV")
    if virtual_environment:
        root = Path(virtual_environment).resolve()
        environment["PATH"] = os.pathsep.join(
            entry
            for entry in environment.get("PATH", "").split(os.pathsep)
            if entry and not Path(entry).resolve().is_relative_to(root)
        )
    for name in list(environment):
        if name.startswith(("SKILLING_", "GIT_")) or name in {
            "PYTHONPATH",
            "PYTHONHOME",
            "VIRTUAL_ENV",
            "UV_PROJECT_ENVIRONMENT",
            "UV_PYTHON",
            "PWD",
            "OLDPWD",
        }:
            environment.pop(name)
    environment.update(PYTHONNOUSERSITE="1", UV_NO_CONFIG="1", PYDANTIC_AI_NO_BANNER="1")
    return environment


def _inspect(path: Path, *, tutor: bool, version: str, license_bytes: bytes) -> dict[str, object]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            files = {
                name: archive.read(name) for name in archive.namelist() if not name.endswith("/")
            }
    else:
        with tarfile.open(path) as archive:
            files = {}
            for member in archive.getmembers():
                if member.isfile():
                    stream = archive.extractfile(member)
                    assert stream is not None
                    files[member.name] = stream.read()
    metadata = next(
        value
        for name, value in files.items()
        if name.endswith("METADATA") or name.endswith("PKG-INFO")
    )
    parsed = BytesParser().parsebytes(metadata)
    assert parsed["Name"] == ("skilling-tutor" if tutor else "skilling")
    assert parsed["Version"] == version
    assert parsed["Requires-Python"] == ">=3.11"
    assert parsed["License-Expression"] == "Apache-2.0"
    assert any(name.endswith("/py.typed") for name in files)
    assert any(
        name.endswith("/LICENSE") and content == license_bytes for name, content in files.items()
    )
    dependencies = parsed.get_all("Requires-Dist", [])
    if tutor:
        assert sorted(dependencies) == [
            "pydantic-ai-harness[skills]<0.53.0,>=0.52.0",
            "pydantic-ai-slim<2.53.0,>=2.52.0",
            "skilling<0.9.0,>=0.8.0",
        ]
        assert not any(name.endswith("entry_points.txt") for name in files)
    else:
        assert all("pydantic-ai" not in dependency for dependency in dependencies)
    return {
        "name": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "dependencies": dependencies,
        "version": parsed["Version"],
        "license_sha256": hashlib.sha256(license_bytes).hexdigest(),
    }


def _inspect_app(path: Path, license_bytes: bytes) -> dict[str, object]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            files = {
                name: archive.read(name) for name in archive.namelist() if not name.endswith("/")
            }
    else:
        with tarfile.open(path) as archive:
            files = {}
            for member in archive.getmembers():
                if member.isfile():
                    stream = archive.extractfile(member)
                    assert stream is not None
                    files[member.name] = stream.read()
    parsed = BytesParser().parsebytes(
        next(
            value
            for name, value in files.items()
            if name.endswith("METADATA") or name.endswith("PKG-INFO")
        )
    )
    assert parsed["Name"] == "skilling-producer-example"
    assert parsed["Version"] == "0.1.0" and parsed["Requires-Python"] == ">=3.11"
    assert parsed["License-Expression"] == "Apache-2.0"
    assert any(name.endswith("/LICENSE") and body == license_bytes for name, body in files.items())
    for asset in ("index.html", "app.js", "styles.css"):
        assert any(name.endswith(f"/static/{asset}") for name in files), f"Missing asset: {asset}"
    dependencies = parsed.get_all("Requires-Dist", [])
    assert sorted(dependencies) == [
        "fastapi<0.143,>=0.142.2",
        "skilling-tutor<0.2.0,>=0.1.0",
        "uvicorn<0.55,>=0.54.0",
    ]
    return {
        "name": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "dependencies": dependencies,
        "version": parsed["Version"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-dist", type=Path, required=True)
    parser.add_argument("--tutor-dist", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--python-version", default="3.11")
    parser.add_argument("--app", type=Path, help="Reference app source for the installed journey")
    parser.add_argument(
        "--store-profile", choices=("file", "sqlite", "postgres", "s3"), default="sqlite"
    )
    parser.add_argument(
        "--store-config", type=Path, help="Private explicit disposable backend configuration"
    )
    parser.add_argument(
        "--check-backend-extras",
        action="store_true",
        help="Verify installed optional SDK wheels without contacting services",
    )
    args = parser.parse_args()
    if args.store_profile in ("postgres", "s3") and args.store_config is None:
        parser.error("remote profiles require --store-config")
    evidence = args.evidence.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).resolve().parents[3]
    core_version = tomllib.loads((source / "packages/skilling/pyproject.toml").read_text())[
        "project"
    ]["version"]
    tutor_version = tomllib.loads((source / "packages/skilling-tutor/pyproject.toml").read_text())[
        "project"
    ]["version"]
    assert isinstance(core_version, str) and isinstance(tutor_version, str)
    artifacts = []
    commands = []
    environment = _environment()
    with tempfile.TemporaryDirectory(prefix="skilling-tutor-installed-") as temporary:
        stage = Path(temporary).resolve()
        assert not stage.is_relative_to(source)
        child = stage / "probe.py"
        shutil.copyfile(Path(__file__).with_name("installed_child.py"), child)
        backend_child = stage / "backend_probe.py"
        shutil.copyfile(
            source / "packages/skilling/tests/backends/installed_probe.py", backend_child
        )
        shutil.copytree(source / "examples/welcome-skilling", stage / "welcome-skilling")
        backend_config = None
        if args.store_config is not None:
            backend_config = stage / "private-store-config.json"
            shutil.copyfile(args.store_config.resolve(), backend_config)
            backend_config.chmod(0o600)
            configuration = json.loads(backend_config.read_text())
            for name in ("dsn_env", "restore_dsn_env", "profile_env"):
                reference = configuration.get(name)
                if reference is not None:
                    if not isinstance(reference, str) or reference not in os.environ:
                        raise ValueError("Selected backend environment reference is missing")
                    environment[reference] = os.environ[reference]

        def run(argv: list[str]) -> None:
            started = datetime.now(UTC).isoformat()
            result = subprocess.run(
                argv, cwd=stage, env=environment, capture_output=True, text=True, encoding="utf-8"
            )
            index = len(commands) + 1
            (evidence / f"{index:02d}.stdout").write_text(result.stdout, encoding="utf-8")
            (evidence / f"{index:02d}.stderr").write_text(result.stderr, encoding="utf-8")
            commands.append({"argv": argv, "started": started, "exit": result.returncode})
            (evidence / "commands.json").write_text(
                json.dumps(commands, indent=2), encoding="utf-8"
            )
            assert result.returncode == 0, f"Command failed: see {evidence / f'{index:02d}.stderr'}"

        app_dist = None
        app_probe = None
        if args.app is not None:
            app_source = args.app.resolve()
            copied_app = stage / "app-source"
            shutil.copytree(
                app_source,
                copied_app,
                ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".venv", "dist"),
            )
            app_dist = stage / "app-dist"
            run(["uv", "build", "--no-sources", str(copied_app), "--out-dir", str(app_dist)])
            app_probe = stage / "app_probe.py"
            shutil.copyfile(app_source / "tests/journey.py", app_probe)

        for kind, pattern in (("wheel", "*.whl"), ("sdist", "*.tar.gz")):
            (core,) = args.core_dist.resolve().glob(pattern)
            (tutor,) = args.tutor_dist.resolve().glob(pattern)
            artifacts.extend(
                (
                    _inspect(
                        core,
                        tutor=False,
                        version=core_version,
                        license_bytes=(source / "packages/skilling/LICENSE").read_bytes(),
                    ),
                    _inspect(
                        tutor,
                        tutor=True,
                        version=tutor_version,
                        license_bytes=(source / "packages/skilling-tutor/LICENSE").read_bytes(),
                    ),
                )
            )
            local_core = stage / core.name
            local_tutor = stage / tutor.name
            shutil.copyfile(core, local_core)
            shutil.copyfile(tutor, local_tutor)
            venv = stage / kind
            run(["uv", "venv", "--python", args.python_version, str(venv)])
            python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            run(
                ["uv", "pip", "install", "--python", str(python), str(local_core), str(local_tutor)]
            )
            run([str(python), str(child), core_version, tutor_version])
            if args.store_profile in ("postgres", "s3"):
                run(
                    [
                        "uv",
                        "pip",
                        "install",
                        "--python",
                        str(python),
                        f"{local_core}[{args.store_profile}]",
                    ]
                )
            run(
                [
                    str(python),
                    str(backend_child),
                    "--store-profile",
                    args.store_profile,
                    "--course-source",
                    str(stage / "welcome-skilling"),
                    "--workspace",
                    str(stage / f"{kind}-backend"),
                    *(["--store-config", str(backend_config)] if backend_config else []),
                ]
            )
            if app_dist is not None and app_probe is not None:
                (app_artifact,) = app_dist.glob(pattern)
                artifacts.append(
                    _inspect_app(app_artifact, (source / "packages/skilling/LICENSE").read_bytes())
                )
                run(
                    [
                        "uv",
                        "pip",
                        "install",
                        "--python",
                        str(python),
                        str(app_artifact),
                        "httpx>=0.28,<0.29",
                    ]
                )
                run(
                    [
                        str(python),
                        "-c",
                        "import pathlib,sys,skilling_producer_example as app; "
                        "origin=pathlib.Path(app.__file__).resolve(); "
                        "assert origin.is_relative_to(pathlib.Path(sys.prefix).resolve()); "
                        "print('installed app origin:', app.__file__)",
                    ]
                )
                run(
                    [
                        str(python),
                        str(app_probe),
                        "--workspace",
                        str(stage / f"{kind}-workspace"),
                        "--course-source",
                        str(stage / "welcome-skilling"),
                    ]
                )
                run(
                    [
                        str(python),
                        str(app_probe),
                        "--store-profile",
                        args.store_profile,
                        "--workspace",
                        str(stage / f"{kind}-configured-app"),
                        "--course-source",
                        str(stage / "welcome-skilling"),
                        *(["--store-config", str(backend_config)] if backend_config else []),
                    ]
                )
            if args.check_backend_extras:
                run(
                    [
                        "uv",
                        "pip",
                        "install",
                        "--python",
                        str(python),
                        "--only-binary",
                        "psycopg-binary",
                        f"{local_core}[postgres,s3]",
                    ]
                )
                run(
                    [
                        str(python),
                        "-c",
                        "import os; os.environ['PSYCOPG_IMPL']='binary'; "
                        "import pathlib,sys,boto3,psycopg,psycopg_pool,skilling.store; "
                        "assert psycopg.pq.__impl__ == 'binary'; "
                        "root=pathlib.Path(sys.prefix).resolve(); "
                        "assert all(pathlib.Path(m.__file__).resolve().is_relative_to(root) "
                        "for m in (boto3,psycopg,psycopg_pool,skilling.store)); "
                        "assert callable(skilling.store.PostgresSessionStore.open); "
                        "assert callable(skilling.store.S3SessionStore.open); "
                        "print('installed backend extras PASS; no service calls')",
                    ]
                )
        core_only = stage / "core-only"
        run(["uv", "venv", "--python", args.python_version, str(core_only)])
        python = core_only / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run(["uv", "pip", "install", "--python", str(python), str(local_core)])
        run(
            [
                str(python),
                "-c",
                "import importlib.util, skilling.session; "
                "assert importlib.util.find_spec('pydantic_ai') is None; "
                "assert importlib.util.find_spec('skilling_tutor') is None; "
                "assert importlib.util.find_spec('fastapi') is None; "
                "assert importlib.util.find_spec('uvicorn') is None; "
                "print('core-only PASS')",
            ]
        )
    (evidence / "manifest.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "store_profile": args.store_profile,
                "backend_extras_checked": args.check_backend_extras,
                "backend_probe_sha256": hashlib.sha256(
                    (source / "packages/skilling/tests/backends/installed_probe.py").read_bytes()
                ).hexdigest(),
                "platform": platform.platform(),
                "python_requested": args.python_version,
                "artifacts": artifacts,
                "app_source": str(args.app) if args.app is not None else None,
                "app_probe_sha256": hashlib.sha256(
                    (args.app / "tests/journey.py").read_bytes()
                ).hexdigest()
                if args.app is not None
                else None,
                "child_sha256": hashlib.sha256(child.read_bytes()).hexdigest()
                if child.exists()
                else hashlib.sha256(
                    Path(__file__).with_name("installed_child.py").read_bytes()
                ).hexdigest(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Matched wheel/sdist and core-only smokes passed: {evidence}")


if __name__ == "__main__":
    main()
