"""Exercise Git/cache acquisition from persistent installed wheel and sdist tools."""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from package_smoke import (
    Commands,
    clean_environment,
    expected_manifest,
    inspect_artifact,
    install_tool,
    source_identity,
    stage_inputs,
)


def git(root: Path, *arguments: str) -> None:
    home = root.parent / "git-home"
    home.mkdir(exist_ok=True)
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        env=clean_environment(
            {
                "HOME": str(home),
                "USERPROFILE": str(home),
                "XDG_CONFIG_HOME": str(home / ".config"),
            }
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, (arguments, result.stdout, result.stderr)


def repository(example: Path, root: Path) -> None:
    shutil.copytree(example, root)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "core.autocrlf", "false")
    git(root, "config", "user.name", "Installed source probe")
    git(root, "config", "user.email", "probe@example.invalid")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "fixture")


def probe(
    manifest_path: Path,
    case: Path,
    tool_dir: Path,
    checkout_sentinel: Path,
    python_version: str,
) -> None:
    import skilling
    from skilling.sources import CacheConflict, resolve

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert not checkout_sentinel.exists(), checkout_sentinel
    assert f"{sys.version_info.major}.{sys.version_info.minor}" == python_version, sys.version
    imported = Path(skilling.__file__).resolve()
    assert imported.is_relative_to(Path(sys.prefix).resolve()), imported
    assert Path(sys.prefix).resolve().is_relative_to(tool_dir.resolve()), sys.prefix
    package_root = imported.parent
    for relative, expected_hash in manifest["files"].items():
        installed = package_root / Path(relative).relative_to("skilling")
        assert installed.is_file() and _sha256(installed) == expected_hash, installed

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


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def smoke(source: Path, dist: Path, evidence: Path, python_version: str) -> None:
    assert f"{sys.version_info.major}.{sys.version_info.minor}" == python_version, sys.version
    evidence.mkdir(parents=True, exist_ok=False)
    manifest = expected_manifest(source)
    source_artifacts = [
        dist / f"skilling-{manifest['version']}-py3-none-any.whl",
        dist / f"skilling-{manifest['version']}.tar.gz",
    ]
    (evidence / "artifacts.json").write_text(
        json.dumps([inspect_artifact(artifact, source) for artifact in source_artifacts], indent=2),
        encoding="utf-8",
    )
    root = Path(tempfile.mkdtemp(prefix="skilling-installed-sources-"))
    assert not root.resolve().is_relative_to(source)
    package_controller = Path(__file__).with_name("package_smoke.py")
    import_controller = Path(__file__).with_name("import_package_probe.py")
    stage, artifacts = stage_inputs(
        source, dist, root, [Path(__file__), package_controller, import_controller]
    )
    (evidence / "environment.json").write_text(
        json.dumps(
            {
                "source_identity": source_identity(source),
                "temporary_root": str(root),
                "controller_python": sys.version,
                "expected_python": python_version,
                "platform": platform.platform(),
                "package_version": manifest["version"],
                "skips": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    commands = Commands(evidence, forbidden=source)
    succeeded = False
    try:
        for kind, artifact in zip(("wheel", "sdist"), artifacts, strict=True):
            case = root / kind
            case.mkdir()
            env, python, tool_dir = install_tool(commands, artifact, case, python_version)
            checkout_sentinel = case / "checkout-unavailable"
            assert not checkout_sentinel.exists()
            for name in ("remote", "equivalent", "different"):
                repository(stage / "course", case / name)
            (case / "different/extra.txt").write_text("Different payload\n", encoding="utf-8")
            git(case / "different", "add", "-A")
            git(case / "different", "commit", "-qm", "change content")
            started = json.loads(
                commands.run(
                    [
                        "skilling",
                        "start",
                        (case / "remote").as_uri(),
                        str(case / "workspace"),
                        "--json",
                    ],
                    case,
                    env,
                )
            )
            assert started["course"]["id"] == "welcome-skilling"
            nested = case / "workspace/notes/nested"
            nested.mkdir(parents=True)
            first = json.loads(
                commands.run(["skilling", "next", "--course", "welcome-skilling"], nested, env)
            )
            assert first["beat"]["name"] == "welcome"
            commands.run(
                [
                    str(python),
                    str(stage / "source_package_smoke.py"),
                    "--probe",
                    "--manifest",
                    str(stage / "expected.json"),
                    "--case",
                    str(case),
                    "--tool-dir",
                    str(tool_dir),
                    "--checkout-sentinel",
                    str(checkout_sentinel),
                    "--python-version",
                    python_version,
                ],
                case,
                env,
            )
            relocated = case / "relocated"
            resumed = json.loads(
                commands.run(["skilling", "next", "--course", "welcome-skilling"], relocated, env)
            )
            assert resumed["beat"]["name"] == "welcome"
            commands.run(["skilling", "progress", "--course", "welcome-skilling"], relocated, env)
            commands.run(
                [
                    str(python),
                    str(stage / "import_package_probe.py"),
                    "--fixture",
                    str(stage / "course"),
                    "--case",
                    str(case / "imports"),
                    "--tool-dir",
                    str(tool_dir),
                    "--checkout-sentinel",
                    str(checkout_sentinel),
                    "--python-version",
                    python_version,
                ],
                case,
                env,
            )
            shutil.copytree(relocated / ".skilling", evidence / f"{kind}-workspace")
        succeeded = True
    finally:
        (evidence / "result.json").write_text(
            json.dumps({"passed": succeeded, "commands": commands.count}), encoding="utf-8"
        )
        if succeeded:
            shutil.rmtree(root, onerror=remove_read_only)
    print(f"Installed wheel/sdist Git source proof passed; evidence: {evidence}")


def remove_read_only(operation: Callable[..., object], filename: str, error: object) -> None:
    """Cleanup only the controller's temporary tree, including Windows Git objects."""
    path = Path(filename)
    if path.is_symlink() or not path.is_file():
        raise OSError("cannot safely remove temporary Git content")
    path.chmod(path.stat().st_mode | stat.S_IWRITE)
    operation(filename)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--dist", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--case", type=Path)
    parser.add_argument("--tool-dir", type=Path)
    parser.add_argument("--checkout-sentinel", type=Path)
    parser.add_argument(
        "--python-version", default=f"{sys.version_info.major}.{sys.version_info.minor}"
    )
    args = parser.parse_args()
    if args.probe:
        if (
            args.case is None
            or args.manifest is None
            or args.tool_dir is None
            or args.checkout_sentinel is None
        ):
            parser.error("--probe requires --case, --manifest, --tool-dir, and --checkout-sentinel")
        probe(
            args.manifest.resolve(),
            args.case.resolve(),
            args.tool_dir.resolve(),
            args.checkout_sentinel.resolve(),
            args.python_version,
        )
    else:
        if args.source is None or args.dist is None:
            parser.error("--source and --dist are required")
        evidence = args.evidence or Path(tempfile.gettempdir()) / (
            "skilling-source-evidence-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        )
        smoke(args.source.resolve(), args.dist.resolve(), evidence.resolve(), args.python_version)


if __name__ == "__main__":
    main()
