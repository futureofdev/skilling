"""Exercise Git/cache acquisition from isolated installed wheel and sdist environments."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Callable
from pathlib import Path

from package_smoke import Commands, inspect_artifact


def git(root: Path, *arguments: str) -> None:
    subprocess.run(["git", *arguments], cwd=root, capture_output=True, check=True)


def repository(example: Path, root: Path) -> None:
    shutil.copytree(example, root)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "core.autocrlf", "false")
    git(root, "config", "user.name", "Installed source probe")
    git(root, "config", "user.email", "probe@example.invalid")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "fixture")


def probe(source: Path, case: Path, python_version: str) -> None:
    import skilling
    from skilling.sources import CacheConflict, resolve

    assert f"{sys.version_info.major}.{sys.version_info.minor}" == python_version, sys.version
    imported = Path(skilling.__file__).resolve()
    assert imported.is_relative_to(Path(sys.prefix).resolve()), imported
    assert not imported.is_relative_to(source), imported
    remote = case / "remote"
    ref = remote.as_uri()
    cache = case / "workspace/.skilling/courses"
    first = resolve(ref, cache=cache)
    equivalent = resolve((case / "equivalent").as_uri(), cache=cache)
    assert equivalent.course == first.course and equivalent.path == first.path
    before = (cache / ".index.json").read_bytes()
    try:
        resolve((case / "different").as_uri(), cache=cache)
    except CacheConflict:
        pass
    else:
        raise AssertionError("different installed source silently borrowed existing content")
    assert (cache / ".index.json").read_bytes() == before
    remote.rename(case / "offline")
    (case / "equivalent").rename(case / "equivalent-offline")
    workspace = case / "workspace"
    workspace.rename(case / "relocated")
    durable = case / "relocated/.skilling/courses" / first.path.name
    hit = resolve(ref, cache=durable.parent)
    assert hit.course == type(hit.course).load(durable)
    assert hit.course.manifest == first.course.manifest
    assert hit.path == hit.course.root == durable
    assert all(lesson.path.is_file() for lesson in hit.course.lessons())
    assert not list(durable.rglob(".git"))
    print(
        json.dumps(
            {
                "import": str(imported),
                "prefix": sys.prefix,
                "python": sys.version,
                "expected_python": python_version,
                "course": hit.course.id,
                "durable": str(durable),
                "equivalent": True,
                "conflict": True,
                "offline_relocated": True,
            },
            indent=2,
        )
    )


def smoke(source: Path, dist: Path, evidence: Path, python_version: str) -> None:
    assert f"{sys.version_info.major}.{sys.version_info.minor}" == python_version, sys.version
    evidence.mkdir(parents=True, exist_ok=False)
    commands = Commands(evidence)
    version = tomllib.loads((source / "packages/skilling/pyproject.toml").read_text())["project"][
        "version"
    ]
    artifacts = [dist / f"skilling-{version}-py3-none-any.whl", dist / f"skilling-{version}.tar.gz"]
    (evidence / "artifacts.json").write_text(
        json.dumps([inspect_artifact(artifact, source) for artifact in artifacts], indent=2)
    )
    root = Path(tempfile.mkdtemp(prefix="skilling-installed-sources-"))
    assert not root.resolve().is_relative_to(source)
    (evidence / "environment.json").write_text(
        json.dumps(
            {
                "source": str(source),
                "temporary_root": str(root),
                "controller_python": sys.version,
                "expected_python": python_version,
                "platform": platform.platform(),
                "package_version": version,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    succeeded = False
    try:
        for kind, artifact in zip(("wheel", "sdist"), artifacts, strict=True):
            case = root / kind
            case.mkdir()
            env = case / "env"
            commands.run(["uv", "venv", "--python", sys.executable, str(env)], case)
            binaries = env / ("Scripts" if os.name == "nt" else "bin")
            python = binaries / ("python.exe" if os.name == "nt" else "python")
            cli = binaries / ("skilling.exe" if os.name == "nt" else "skilling")
            commands.run(["uv", "pip", "install", "--python", str(python), str(artifact)], case)
            for name in ("remote", "equivalent", "different"):
                repository(source / "examples/hello-skilling", case / name)
            (case / "different/extra.txt").write_text("Different payload\n")
            git(case / "different", "add", "-A")
            git(case / "different", "commit", "-qm", "change content")
            commands.run(
                [str(cli), "start", (case / "remote").as_uri(), str(case / "workspace"), "--json"],
                case,
            )
            first = json.loads(
                commands.run([str(cli), "next", "--course", "hello-skilling"], case / "workspace")
            )
            assert first["beat"]["name"] == "welcome"
            commands.run(
                [
                    str(python),
                    str(Path(__file__).resolve()),
                    "--probe",
                    "--source",
                    str(source),
                    "--case",
                    str(case),
                    "--python-version",
                    python_version,
                ],
                case,
            )
            resumed = json.loads(
                commands.run([str(cli), "next", "--course", "hello-skilling"], case / "relocated")
            )
            assert resumed["beat"]["name"] == "welcome"
            commands.run([str(cli), "progress", "--course", "hello-skilling"], case / "relocated")
            commands.run(
                [
                    str(python),
                    str(Path(__file__).with_name("import_package_probe.py").resolve()),
                    "--source",
                    str(source),
                    "--case",
                    str(case / "imports"),
                    "--python-version",
                    python_version,
                ],
                case,
            )
            shutil.copytree(case / "relocated/.skilling", evidence / f"{kind}-workspace")
        succeeded = True
    finally:
        (evidence / "result.json").write_text(json.dumps({"passed": succeeded, "root": str(root)}))
        if succeeded:
            shutil.rmtree(root, onerror=remove_read_only)
    print(f"Installed wheel/sdist Git source proof passed; evidence: {evidence}")


def remove_read_only(operation: Callable[..., object], filename: str, error: object) -> None:
    """Cleanup only the controller's owned temporary tree, including Windows Git objects."""
    path = Path(filename)
    if path.is_symlink() or not path.is_file():
        raise OSError("cannot safely remove temporary Git content")
    path.chmod(path.stat().st_mode | stat.S_IWRITE)
    operation(filename)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--dist", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--case", type=Path)
    parser.add_argument(
        "--python-version", default=f"{sys.version_info.major}.{sys.version_info.minor}"
    )
    args = parser.parse_args()
    if args.probe:
        if args.case is None:
            parser.error("--probe requires --case")
        probe(args.source.resolve(), args.case.resolve(), args.python_version)
    else:
        if args.dist is None or args.evidence is None:
            parser.error("--dist and --evidence are required")
        smoke(
            args.source.resolve(), args.dist.resolve(), args.evidence.resolve(), args.python_version
        )


if __name__ == "__main__":
    main()
