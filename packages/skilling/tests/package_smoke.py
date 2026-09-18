"""Inspect and exercise installed wheel and sdist artifacts outside the checkout.

The controller may read the checkout while preparing a disposable stage. Installed children
receive only staged paths and invoke the persistent tool by its bare command name.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from datetime import UTC, datetime
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import TypedDict, cast

SUMMARY = "Learner CLI and LLM-free reference implementation for the open Skilling course format."
PROJECT_URLS = {
    "Homepage": "https://github.com/futureofdev/skilling",
    "Documentation": "https://github.com/futureofdev/skilling/tree/main/docs",
    "Source": "https://github.com/futureofdev/skilling",
    "Issues": "https://github.com/futureofdev/skilling/issues",
}
CLASSIFIERS = [
    "Environment :: Console",
    "Intended Audience :: Education",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3 :: Only",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Programming Language :: Python :: 3.14",
    "Programming Language :: Python :: Implementation :: CPython",
    "Topic :: Education",
    "Typing :: Typed",
]
DEPENDENCIES = {"pydantic", "pyyaml", "typer", "rich", "tzdata"}
COURSE_ID = "welcome-skilling"


class ExpectedManifest(TypedDict):
    name: str
    version: str
    license_sha256: str
    files: dict[str, str]
    skill_resources: list[str]


class RetainedResources(TypedDict):
    format_version: int
    source: dict[str, object]
    package: dict[str, object]
    artifacts: list[dict[str, object]]
    controllers: dict[str, str]
    fixture: dict[str, str]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def retained_fixture_hashes(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in [*directories, *files]:
            path = current_path / name
            assert not path.is_symlink(), path
        for name in files:
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            assert ".." not in Path(relative).parts and not Path(relative).is_absolute(), relative
            hashes[relative] = sha256(path.read_bytes())
    return dict(sorted(hashes.items()))


def clean_environment(overrides: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    virtual_environment = env.get("VIRTUAL_ENV")
    names = {
        "SKILLING_STATE_ROOT",
        "SKILLING_WORKSPACE",
        "SKILLING_CACHE_DIR",
        "SKILLING_NOW",
        "PYTHONPATH",
        "PYTHONHOME",
        "VIRTUAL_ENV",
        "UV_PROJECT_ENVIRONMENT",
        "UV_PYTHON",
        "FORCE_COLOR",
        "CLICOLOR",
        "CLICOLOR_FORCE",
        "PWD",
        "OLDPWD",
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_COMMON_DIR",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CEILING_DIRECTORIES",
        "GIT_CONFIG",
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_SYSTEM",
        "GIT_CONFIG_COUNT",
    }
    names.update(name for name in env if name.startswith("GIT_CONFIG_KEY_"))
    names.update(name for name in env if name.startswith("GIT_CONFIG_VALUE_"))
    for name in names:
        env.pop(name, None)
    if virtual_environment is not None:
        virtual_root = Path(virtual_environment).resolve()
        env["PATH"] = os.pathsep.join(
            entry
            for entry in env.get("PATH", "").split(os.pathsep)
            if entry and not Path(entry).resolve().is_relative_to(virtual_root)
        )
    env.update(
        {
            "PYTHONTZPATH": "",
            "PYTHONNOUSERSITE": "1",
            "NO_COLOR": "1",
            "PYTHONIOENCODING": "utf-8",
            "UV_NO_CONFIG": "1",
        }
    )
    if overrides:
        env.update(overrides)
    return env


def environment_value(environment: dict[str, str], name: str) -> str:
    """Read an environment key with Windows' case-insensitive name semantics."""
    if name in environment:
        return environment[name]
    matches = [value for key, value in environment.items() if key.casefold() == name.casefold()]
    assert len(matches) == 1, f"expected one {name} environment entry, found {len(matches)}"
    return matches[0]


def installed_executable(argv: list[str], environment: dict[str, str]) -> str | None:
    """Resolve a bare installed CLI from its child PATH for Windows subprocess reliability."""
    if argv[0] != "skilling":
        return None
    executable = shutil.which("skilling", path=environment_value(environment, "PATH"))
    assert executable is not None, "skilling is absent from the isolated tool PATH"
    executable_path = Path(executable)
    tool_bin = Path(environment_value(environment, "UV_TOOL_BIN_DIR"))
    assert executable_path.parent.resolve() == tool_bin.resolve(), executable_path
    return str(executable_path)


class Commands:
    def __init__(
        self,
        evidence: Path,
        forbidden: Path | None = None,
        allow_forbidden_arguments: bool = False,
    ) -> None:
        self.evidence = evidence
        self.forbidden = str(forbidden.resolve()) if forbidden is not None else None
        self.allow_forbidden_arguments = allow_forbidden_arguments
        self.count = 0

    def run(
        self,
        argv: list[str],
        cwd: Path,
        env: dict[str, str] | None = None,
        expected_exit: int = 0,
    ) -> str:
        if self.forbidden is not None and not self.allow_forbidden_arguments:
            exposed = [value for value in [*argv, str(cwd)] if self.forbidden in value]
            assert not exposed, f"installed command exposed checkout path: {exposed}"
        self.count += 1
        stem = self.evidence / f"{self.count:02d}"
        started = datetime.now(UTC).isoformat()
        process_env = dict(env) if env is not None else clean_environment()
        removed_checkout_environment: list[str] = []
        if self.forbidden is not None:
            for name, value in list(process_env.items()):
                if self.forbidden in value:
                    removed_checkout_environment.append(name)
                    del process_env[name]
            removed_checkout_environment.sort()
            exposed_env = sorted(
                name for name, value in process_env.items() if self.forbidden in value
            )
            assert not exposed_env, f"installed environment exposed checkout path: {exposed_env}"
        executable = installed_executable(argv, process_env)
        result = subprocess.run(
            argv,
            cwd=cwd,
            env=process_env,
            executable=executable,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
        )
        stem.with_suffix(".stdout").write_text(result.stdout, encoding="utf-8")
        stem.with_suffix(".stderr").write_text(result.stderr, encoding="utf-8")
        stem.with_suffix(".json").write_text(
            json.dumps(
                {
                    "argv": argv,
                    "cwd": str(cwd),
                    "started": started,
                    "finished": datetime.now(UTC).isoformat(),
                    "exit_code": result.returncode,
                    "expected_exit": expected_exit,
                    "resolved_executable": executable,
                    "removed_checkout_environment": removed_checkout_environment,
                    "isolated_environment": {
                        name: process_env.get(name)
                        for name in (
                            "HOME",
                            "USERPROFILE",
                            "UV_TOOL_DIR",
                            "UV_TOOL_BIN_DIR",
                            "UV_CACHE_DIR",
                            "UV_NO_CONFIG",
                            "PYTHONTZPATH",
                            "PYTHONNOUSERSITE",
                        )
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        if result.returncode != expected_exit:
            raise RuntimeError(
                f"Command exited {result.returncode}, expected {expected_exit}: {argv}\n"
                f"{result.stdout}\n{result.stderr}"
            )
        return result.stdout


def package_files(source: Path) -> list[Path]:
    package = source / "packages/skilling/src/skilling"
    return sorted(
        path
        for path in package.rglob("*")
        if path.is_file() and (path.suffix in {".py", ".md"} or path.name == "py.typed")
    )


def expected_manifest(source: Path) -> ExpectedManifest:
    package_root = source / "packages/skilling/src"
    files = {
        path.relative_to(package_root).as_posix(): sha256(path.read_bytes())
        for path in package_files(source)
    }
    skills = sorted(
        name for name in files if name.startswith("skilling/skills/") and name.endswith(".md")
    )
    project = tomllib.loads(
        (source / "packages/skilling/pyproject.toml").read_text(encoding="utf-8")
    )
    return {
        "name": "skilling",
        "version": project["project"]["version"],
        "license_sha256": sha256((source / "LICENSE").read_bytes()),
        "files": files,
        "skill_resources": skills,
    }


def _dependency_name(requirement: str) -> str:
    match = re.match(r"[A-Za-z0-9_.-]+", requirement)
    assert match is not None, requirement
    return match.group().lower().replace("_", "-")


def _metadata_facts(metadata_bytes: bytes, source: Path) -> dict[str, object]:
    message = BytesParser(policy=policy.default).parsebytes(metadata_bytes)
    project = tomllib.loads(
        (source / "packages/skilling/pyproject.toml").read_text(encoding="utf-8")
    )["project"]
    metadata_version = tuple(int(part) for part in message["Metadata-Version"].split("."))
    assert metadata_version >= (2, 4), metadata_version
    assert message["Name"] == "skilling"
    assert message["Version"] == project["version"]
    assert message["Summary"] == SUMMARY == project["description"]
    assert message["Requires-Python"] == project["requires-python"] == ">=3.11"
    assert message["License-Expression"] == "Apache-2.0"
    assert message.get_all("License-File") == ["LICENSE"]
    assert message.get("License") is None
    assert message["Description-Content-Type"].startswith("text/markdown")
    urls = {}
    for row in message.get_all("Project-URL", []):
        label, url = row.split(", ", 1)
        urls[label] = url
    assert urls == PROJECT_URLS == project["urls"]
    classifiers = message.get_all("Classifier", [])
    assert classifiers == CLASSIFIERS == project["classifiers"]
    dependencies = {_dependency_name(value) for value in message.get_all("Requires-Dist", [])}
    assert dependencies == DEPENDENCIES
    separator = b"\r\n\r\n" if b"\r\n\r\n" in metadata_bytes else b"\n\n"
    description = metadata_bytes.split(separator, 1)[1]
    readme = (source / "packages/skilling/README.md").read_bytes()
    assert description.rstrip(b"\r\n") == readme.rstrip(b"\r\n")
    return {
        "metadata_version": message["Metadata-Version"],
        "name": message["Name"],
        "version": message["Version"],
        "summary": message["Summary"],
        "requires_python": message["Requires-Python"],
        "license_expression": message["License-Expression"],
        "license_files": message.get_all("License-File"),
        "description_content_type": message["Description-Content-Type"],
        "project_urls": urls,
        "classifiers": classifiers,
        "dependencies": sorted(dependencies),
        "long_description_sha256": sha256(description),
    }


def inspect_artifact(artifact: Path, source: Path) -> dict[str, object]:
    expected = {
        path.relative_to(source / "packages/skilling/src").as_posix(): path.read_bytes()
        for path in package_files(source)
    }
    license_bytes = (source / "LICENSE").read_bytes()
    assert (source / "packages/skilling/LICENSE").read_bytes() == license_bytes

    if artifact.suffix == ".whl":
        with zipfile.ZipFile(artifact) as archive:
            names = archive.namelist()
            metadata_path = next(name for name in names if name.endswith(".dist-info/METADATA"))
            license_path = next(
                name for name in names if name.endswith(".dist-info/licenses/LICENSE")
            )
            entry_path = next(
                name for name in names if name.endswith(".dist-info/entry_points.txt")
            )
            for relative, content in expected.items():
                assert archive.read(relative) == content, (artifact, relative)
            assert archive.read(license_path) == license_bytes
            entry_points = archive.read(entry_path).decode("utf-8")
            assert "[console_scripts]" in entry_points
            assert "skilling = skilling.cli:main" in entry_points
            metadata = _metadata_facts(archive.read(metadata_path), source)
    else:
        with tarfile.open(artifact) as archive:
            names = archive.getnames()
            prefix = artifact.name.removesuffix(".tar.gz")
            metadata_path = f"{prefix}/PKG-INFO"
            license_path = f"{prefix}/LICENSE"
            for relative, content in expected.items():
                member = archive.extractfile(f"{prefix}/src/{relative}")
                assert member is not None, relative
                assert member.read() == content, (artifact, relative)
            license_member = archive.extractfile(license_path)
            assert license_member is not None
            assert license_member.read() == license_bytes
            metadata_member = archive.extractfile(metadata_path)
            assert metadata_member is not None
            metadata = _metadata_facts(metadata_member.read(), source)
            pyproject_member = archive.extractfile(f"{prefix}/pyproject.toml")
            assert pyproject_member is not None
            built_project = tomllib.loads(pyproject_member.read().decode("utf-8"))
            assert built_project["project"]["scripts"] == {"skilling": "skilling.cli:main"}

    assert not [name for name in names if "/examples/" in name or "/spec/" in name], names
    resource_hashes = {name: sha256(content) for name, content in expected.items()}
    return {
        "file": artifact.name,
        "sha256": sha256(artifact.read_bytes()),
        "size": artifact.stat().st_size,
        "metadata": metadata,
        "license_path": license_path,
        "license_sha256": sha256(license_bytes),
        "entry_point": "skilling = skilling.cli:main",
        "matched_package_files": len(expected),
        "package_manifest_sha256": sha256(
            json.dumps(resource_hashes, sort_keys=True).encode("utf-8")
        ),
        "contains_course_catalogue": False,
    }


def _retained_metadata_facts(metadata_bytes: bytes, expected: dict[str, object]) -> None:
    message = BytesParser(policy=policy.default).parsebytes(metadata_bytes)
    assert tuple(int(part) for part in message["Metadata-Version"].split(".")) >= (2, 4)
    assert message["Name"] == expected["name"]
    assert message["Version"] == expected["version"]
    assert message["Summary"] == expected["summary"]
    assert message["Requires-Python"] == expected["requires_python"]
    assert message["License-Expression"] == expected["license_expression"]
    assert message.get_all("License-File") == ["LICENSE"]
    urls = dict(row.split(", ", 1) for row in message.get_all("Project-URL", []))
    assert urls == expected["project_urls"]
    assert message.get_all("Classifier", []) == expected["classifiers"]
    dependencies = sorted(_dependency_name(value) for value in message.get_all("Requires-Dist", []))
    assert dependencies == expected["dependencies"]
    separator = b"\r\n\r\n" if b"\r\n\r\n" in metadata_bytes else b"\n\n"
    description = metadata_bytes.split(separator, 1)[1]
    assert sha256(description) == expected["readme_sha256"]


def inspect_retained_artifact(artifact: Path, expected: dict[str, object]) -> None:
    """Inspect an artifact using only the retained resource contract."""
    expected_files = expected["files"]
    assert isinstance(expected_files, dict)
    if artifact.suffix == ".whl":
        with zipfile.ZipFile(artifact) as archive:
            names = archive.namelist()
            metadata_path = next(name for name in names if name.endswith(".dist-info/METADATA"))
            license_path = next(
                name for name in names if name.endswith(".dist-info/licenses/LICENSE")
            )
            entry_path = next(
                name for name in names if name.endswith(".dist-info/entry_points.txt")
            )
            for relative, digest in expected_files.items():
                assert sha256(archive.read(relative)) == digest, (artifact, relative)
            assert sha256(archive.read(license_path)) == expected["license_sha256"]
            assert str(expected["entry_point"]) in archive.read(entry_path).decode("utf-8")
            _retained_metadata_facts(archive.read(metadata_path), expected)
    else:
        with tarfile.open(artifact) as archive:
            names = archive.getnames()
            prefix = artifact.name.removesuffix(".tar.gz")
            for relative, digest in expected_files.items():
                member = archive.extractfile(f"{prefix}/src/{relative}")
                assert member is not None, relative
                assert sha256(member.read()) == digest, (artifact, relative)
            license_member = archive.extractfile(f"{prefix}/LICENSE")
            assert license_member is not None
            assert sha256(license_member.read()) == expected["license_sha256"]
            metadata_member = archive.extractfile(f"{prefix}/PKG-INFO")
            assert metadata_member is not None
            _retained_metadata_facts(metadata_member.read(), expected)
            project_member = archive.extractfile(f"{prefix}/pyproject.toml")
            assert project_member is not None
            project = tomllib.loads(project_member.read().decode("utf-8"))
            assert project["project"]["scripts"] == {"skilling": "skilling.cli:main"}
    assert not [name for name in names if "/examples/" in name or "/spec/" in name], names


def source_identity(source: Path) -> dict[str, object]:
    def output(*arguments: str) -> str:
        return subprocess.run(
            list(arguments),
            cwd=source,
            env=clean_environment(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout.strip()

    return {
        "commit": output("git", "rev-parse", "HEAD"),
        "tree": output("git", "rev-parse", "HEAD^{tree}"),
        "tracked_clean": not bool(output("git", "status", "--porcelain", "--untracked-files=no")),
        "git": output("git", "--version"),
        "uv": output("uv", "--version"),
    }


def stage_inputs(
    fixture: Path,
    dist: Path,
    root: Path,
    scripts: list[Path],
    manifest: ExpectedManifest,
) -> tuple[Path, list[Path]]:
    stage = root / "stage"
    stage.mkdir()
    shutil.copytree(fixture, stage / "course")
    for script in scripts:
        shutil.copy2(script, stage / script.name)
    (stage / "expected.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    artifacts = [
        dist / f"skilling-{manifest['version']}-py3-none-any.whl",
        dist / f"skilling-{manifest['version']}.tar.gz",
    ]
    staged_artifacts = []
    for artifact in artifacts:
        destination = stage / artifact.name
        shutil.copy2(artifact, destination)
        assert sha256(destination.read_bytes()) == sha256(artifact.read_bytes())
        staged_artifacts.append(destination)
    return stage, staged_artifacts


def tool_environment(case: Path) -> tuple[dict[str, str], Path]:
    tool_dir = case / "tools"
    bin_dir = case / "bin"
    cache_dir = case / "uv-cache"
    home = case / "home"
    for path in (tool_dir, bin_dir, cache_dir, home):
        path.mkdir()
    base = clean_environment()
    inherited_path = environment_value(base, "PATH")
    for name in list(base):
        if name.casefold() == "path":
            del base[name]
    base.update(
        {
            "UV_TOOL_DIR": str(tool_dir),
            "UV_TOOL_BIN_DIR": str(bin_dir),
            "UV_CACHE_DIR": str(cache_dir),
            "HOME": str(home),
            "USERPROFILE": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "PATH": str(bin_dir) + os.pathsep + inherited_path,
        }
    )
    return base, tool_dir


def tool_python(tool_dir: Path) -> Path:
    binaries = tool_dir / "skilling" / ("Scripts" if os.name == "nt" else "bin")
    return binaries / ("python.exe" if os.name == "nt" else "python")


def install_tool(
    commands: Commands, artifact: Path, case: Path, python_version: str
) -> tuple[dict[str, str], Path, Path]:
    env, tool_dir = tool_environment(case)
    commands.run(
        ["uv", "tool", "install", "--python", python_version, "--force", str(artifact)],
        case,
        env,
    )
    python = tool_python(tool_dir)
    assert python.is_file(), python
    return env, python, tool_dir


def probe(
    manifest_path: Path,
    workspace: Path,
    tool_dir: Path,
    checkout_sentinel: Path,
    python_version: str,
) -> None:
    """Run inside the persistent tool environment without checkout knowledge."""
    from datetime import date, timedelta
    from importlib import metadata
    from zoneinfo import TZPATH

    import skilling
    from skilling.course import Course, today_in
    from skilling.delivery import complete_lesson, completed_coordinate, load_or_create
    from skilling.skills import SKILL_NAMES, skill_files
    from skilling.store import FileProgressStore

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert not checkout_sentinel.exists(), checkout_sentinel
    assert f"{sys.version_info.major}.{sys.version_info.minor}" == python_version, sys.version
    imported = Path(skilling.__file__).resolve()
    assert imported.is_relative_to(Path(sys.prefix).resolve()), imported
    assert Path(sys.prefix).resolve().is_relative_to(tool_dir.resolve()), sys.prefix
    assert skilling.__version__ == metadata.version("skilling") == manifest["version"]
    package_root = imported.parent
    for relative, expected_hash in manifest["files"].items():
        installed = package_root / Path(relative).relative_to("skilling")
        assert sha256(installed.read_bytes()) == expected_hash, installed
    assert TZPATH == (), TZPATH
    assert today_in("Pacific/Auckland", datetime(2026, 8, 3, 23, 30, tzinfo=UTC)) == date(
        2026, 8, 4
    )
    assert today_in("America/New_York", datetime(2026, 1, 15, 4, 30, tzinfo=UTC)) == date(
        2026, 1, 14
    )
    assert today_in("America/New_York", datetime(2026, 7, 15, 4, 30, tzinfo=UTC)) == date(
        2026, 7, 15
    )

    bundled_count = 0
    for name in SKILL_NAMES:
        for bundled in skill_files(name):
            bundled_path = Path(bundled).resolve()
            key = "skilling/" + bundled_path.relative_to(package_root).as_posix()
            assert sha256(bundled_path.read_bytes()) == manifest["files"][key]
            relative = bundled_path.relative_to(
                bundled_path.parents[1]
                if bundled_path.parent.name == "references"
                else bundled_path.parent
            )
            for host in (".agents", ".claude"):
                installed = workspace / host / "skills" / name / relative
                assert sha256(installed.read_bytes()) == manifest["files"][key], installed
            bundled_count += 1
    assert bundled_count == len(manifest["skill_resources"])

    course = Course.load(workspace / ".skilling/courses/welcome-skilling@1.0.0")
    store = FileProgressStore(workspace / ".skilling/state")
    moment = datetime(2026, 8, 3, 23, 30, tzinfo=UTC)
    record, revision = load_or_create(store, course, "local", now=moment)
    record = record.model_copy(
        update={
            "timezone": "Pacific/Auckland",
            "last_activity": date(2026, 8, 3),
            "streak_days": 2,
        }
    )
    revision = store.put_record(record, revision)
    for lesson in course.lessons():
        result = complete_lesson(store, course, record, revision, lesson, now=moment)
        record, revision = result.record, result.revision
    assert record.last_activity == date(2026, 8, 4)
    assert record.streak_days == 3
    receipt = store.get_completion_receipt("local", course.id)
    assert receipt is not None and receipt.completed_at == moment
    last = course.lesson_at(receipt.coordinate)
    assert last is not None and last.coordinate == "1.2"
    retried = complete_lesson(store, course, record, revision, last, now=moment + timedelta(days=1))
    assert retried.already_completed and retried.revision == revision
    assert completed_coordinate(course, record, store.get_log("local", course.id)) == "1.2"
    homework, _ = store.get_homework("local", course.id)
    assert homework is not None and homework.unlocked_at == moment

    print(
        json.dumps(
            {
                "import": str(imported),
                "prefix": sys.prefix,
                "python": sys.version,
                "platform": platform.platform(),
                "bundled_files": bundled_count,
                "dependencies": {d.metadata["Name"]: d.version for d in metadata.distributions()},
                "completed": record.completed,
                "timezone": record.timezone,
                "receipt": receipt.coordinate,
            },
            indent=2,
        )
    )


def state_hashes(workspace: Path) -> dict[str, str]:
    root = workspace / ".skilling/state"
    return {
        path.relative_to(root).as_posix(): sha256(path.read_bytes())
        for path in root.rglob("*")
        if path.is_file() and path.name != ".skilling.lock"
    }


def submission_probe(workspace: Path, token: str, tool_dir: Path, checkout_sentinel: Path) -> None:
    from datetime import timedelta

    import skilling
    from skilling.delivery import submit_homework
    from skilling.store import FileProgressStore, ProgressStore, SubmissionCommit, SubmissionToken

    assert not checkout_sentinel.exists(), checkout_sentinel
    assert Path(skilling.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    assert Path(sys.prefix).resolve().is_relative_to(tool_dir.resolve())
    store = FileProgressStore(workspace / ".skilling/state")
    assert isinstance(store, ProgressStore)
    identity = SubmissionToken.parse(token)
    receipt = store.get_submission_receipt("local", COURSE_ID, token)
    assert receipt is not None
    before = state_hashes(workspace)
    retry = submit_homework(
        store,
        "local",
        COURSE_ID,
        identity.coordinate,
        token=token,
        now=receipt.archive.submitted_at + timedelta(days=1),
    )
    assert retry == receipt.archive
    committed = store.commit_submission(SubmissionCommit(receipt, identity.slot_revision, None))
    assert committed.replayed and committed.receipt == receipt
    assert store.get_homework("local", COURSE_ID) == (None, None)
    assert store.get_homework_archive("local", COURSE_ID) == [receipt.archive]
    assert state_hashes(workspace) == before
    print(json.dumps({"public_submission_api": "passed", "replay_state_unchanged": True}))


def check_submission(
    commands: Commands,
    python: Path,
    workspace: Path,
    stage: Path,
    tool_dir: Path,
    checkout_sentinel: Path,
    env: dict[str, str],
) -> None:
    before = state_hashes(workspace)
    checked = json.loads(
        commands.run(["skilling", "homework", "check", "--course", COURSE_ID], workspace, env)
    )
    assert state_hashes(workspace) == before
    token = checked["submission_token"]
    assert isinstance(token, str) and token and checked["active"] is not None
    argv = ["skilling", "homework", "submit", "--course", COURSE_ID, "--token", token]
    submitted = json.loads(commands.run(argv, workspace, env))
    after = state_hashes(workspace)
    replayed = json.loads(commands.run(argv, workspace, env))
    assert replayed["archived"] == submitted["archived"]
    assert state_hashes(workspace) == after
    empty = json.loads(
        commands.run(["skilling", "homework", "check", "--course", COURSE_ID], workspace, env)
    )
    assert empty["active"] is None and empty["submission_token"] is None
    commands.run(
        [
            str(python),
            str(stage / "package_smoke.py"),
            "--submission-probe",
            token,
            "--workspace",
            str(workspace),
            "--tool-dir",
            str(tool_dir),
            "--checkout-sentinel",
            str(checkout_sentinel),
        ],
        workspace,
        env,
    )


def retained_manifest(resources: RetainedResources) -> ExpectedManifest:
    package = resources["package"]
    files = cast(dict[str, object], package["files"])
    skills = cast(list[object], package["skill_resources"])
    return {
        "name": str(package["name"]),
        "version": str(package["version"]),
        "license_sha256": str(package["license_sha256"]),
        "files": {str(name): str(digest) for name, digest in files.items()},
        "skill_resources": [str(name) for name in skills],
    }


def smoke(
    source: Path | None,
    dist: Path,
    evidence: Path,
    python_version: str,
    fixture: Path | None = None,
    expected_resources_path: Path | None = None,
    source_must_not_exist: Path | None = None,
) -> None:
    assert f"{sys.version_info.major}.{sys.version_info.minor}" == python_version, sys.version
    evidence.mkdir(parents=True, exist_ok=False)
    resources: RetainedResources | None = None
    if expected_resources_path is None:
        assert source is not None
        manifest = expected_manifest(source)
        source_artifacts = [
            dist / f"skilling-{manifest['version']}-py3-none-any.whl",
            dist / f"skilling-{manifest['version']}.tar.gz",
        ]
        inspections = [inspect_artifact(artifact, source) for artifact in source_artifacts]
        identity = source_identity(source)
        fixture = fixture or source / "examples/welcome-skilling"
    else:
        resources = json.loads(expected_resources_path.read_text(encoding="utf-8"))
        assert resources is not None
        assert resources["format_version"] == 1
        manifest = retained_manifest(resources)
        source_artifacts = [dist / str(row["file"]) for row in resources["artifacts"]]
        assert sorted(path.name for path in source_artifacts) == sorted(
            [
                f"skilling-{manifest['version']}-py3-none-any.whl",
                f"skilling-{manifest['version']}.tar.gz",
            ]
        )
        for artifact, row in zip(source_artifacts, resources["artifacts"], strict=True):
            assert artifact.stat().st_size == row["size"], artifact
            assert sha256(artifact.read_bytes()) == row["sha256"], artifact
            inspect_retained_artifact(artifact, resources["package"])
        inspections = resources["artifacts"]
        identity = resources["source"]
        assert fixture is not None, "--fixture is required with --expected-resources"
    assert fixture.is_dir(), fixture
    if expected_resources_path is not None:
        assert resources is not None
        assert retained_fixture_hashes(fixture) == resources["fixture"]
    if source_must_not_exist is not None:
        assert not source_must_not_exist.exists(), source_must_not_exist
    (evidence / "artifacts.json").write_text(json.dumps(inspections, indent=2), encoding="utf-8")
    root = Path(tempfile.mkdtemp(prefix="skilling-package-smoke-"))
    if source is not None:
        assert not root.resolve().is_relative_to(source)
    stage, artifacts = stage_inputs(fixture, dist, root, [Path(__file__)], manifest)
    (evidence / "environment.json").write_text(
        json.dumps(
            {
                "source_identity": identity,
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
    commands = Commands(
        evidence,
        forbidden=source or source_must_not_exist,
        allow_forbidden_arguments=source is None and source_must_not_exist is not None,
    )
    succeeded = False
    try:
        for kind, artifact in zip(("wheel", "sdist"), artifacts, strict=True):
            case = root / kind
            case.mkdir()
            env, python, tool_dir = install_tool(commands, artifact, case, python_version)
            checkout_sentinel = source_must_not_exist or case / "checkout-unavailable"
            assert not checkout_sentinel.exists()
            version_output = commands.run(["skilling", "--version"], case, env)
            assert manifest["version"] in version_output
            help_output = commands.run(["skilling", "--help"], case, env)
            assert "start" in help_output and "courses" in help_output
            workspace = case / "workspace"
            started = json.loads(
                commands.run(
                    ["skilling", "start", str(stage / "course"), str(workspace), "--json"],
                    case,
                    env,
                )
            )
            assert started["ok"] is True and started["course"]["id"] == COURSE_ID
            assert Path(started["workspace"]) == workspace.resolve()
            assert started["showcase"] == "showcase/welcome-skilling"
            nested = workspace / "notes" / "later"
            nested.mkdir(parents=True)
            courses = json.loads(commands.run(["skilling", "courses"], nested, env))
            assert [row["id"] for row in courses["courses"]] == [COURSE_ID]
            first = json.loads(
                commands.run(["skilling", "next", "--course", COURSE_ID], nested, env)
            )
            assert first["beat"]["name"] == "welcome", first
            commands.run(["skilling", "progress", "--course", COURSE_ID], nested, env)
            for host in ("agents", "claude"):
                commands.run(["skilling", "install", "--platform", host], nested, env)
            assert (workspace / ".agents/skills/learn/SKILL.md").is_file()
            assert (workspace / ".claude/skills/learn/SKILL.md").is_file()
            assert not (nested / ".agents").exists() and not (nested / ".claude").exists()
            commands.run(
                [
                    str(python),
                    str(stage / "package_smoke.py"),
                    "--probe",
                    "--manifest",
                    str(stage / "expected.json"),
                    "--workspace",
                    str(workspace),
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
            resumed = json.loads(
                commands.run(["skilling", "next", "--course", COURSE_ID], nested, env)
            )
            assert resumed["beat"]["name"] == "done", resumed
            commands.run(["skilling", "progress", "--course", COURSE_ID], nested, env)
            check_submission(commands, python, workspace, stage, tool_dir, checkout_sentinel, env)
            goal = workspace / "showcase/welcome-skilling/goal.md"
            goal.parent.mkdir(parents=True, exist_ok=True)
            goal.write_text(
                "# Learning goal\n\nGoal: practise careful explanations.\n\n"
                "Takeaway: questions reveal what to revisit.\n\n"
                "Next action: explain one idea tomorrow.\n",
                encoding="utf-8",
            )
            added = json.loads(
                commands.run(
                    [
                        "skilling",
                        "artifact",
                        "add",
                        str(goal),
                        "--title",
                        "Learning goal",
                        "--course",
                        COURSE_ID,
                    ],
                    nested,
                    env,
                )
            )
            assert added["artifact"]["coordinate"] == "1.2"
            shutil.copytree(workspace / ".skilling/state", evidence / f"{kind}-state")
        succeeded = True
    finally:
        (evidence / "result.json").write_text(
            json.dumps({"passed": succeeded, "commands": commands.count}), encoding="utf-8"
        )
        if succeeded:
            shutil.rmtree(root)
    print(f"Installed wheel and sdist passed; evidence: {evidence}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--dist", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--expected-resources", type=Path)
    parser.add_argument("--source-must-not-exist", type=Path)
    parser.add_argument(
        "--python-version", default=f"{sys.version_info.major}.{sys.version_info.minor}"
    )
    parser.add_argument("--probe", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--submission-probe", help=argparse.SUPPRESS)
    parser.add_argument("--manifest", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--workspace", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--tool-dir", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--checkout-sentinel", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.submission_probe:
        if args.workspace is None or args.tool_dir is None or args.checkout_sentinel is None:
            parser.error(
                "--submission-probe requires --workspace, --tool-dir, and --checkout-sentinel"
            )
        submission_probe(
            args.workspace.resolve(),
            args.submission_probe,
            args.tool_dir.resolve(),
            args.checkout_sentinel.resolve(),
        )
    elif args.probe:
        if (
            args.workspace is None
            or args.manifest is None
            or args.tool_dir is None
            or args.checkout_sentinel is None
        ):
            parser.error(
                "--probe requires --workspace, --manifest, --tool-dir, and --checkout-sentinel"
            )
        probe(
            args.manifest.resolve(),
            args.workspace.resolve(),
            args.tool_dir.resolve(),
            args.checkout_sentinel.resolve(),
            args.python_version,
        )
    else:
        if args.dist is None:
            parser.error("--dist is required")
        if args.expected_resources is None and args.source is None:
            parser.error("--source or --expected-resources is required")
        if args.expected_resources is not None and args.fixture is None:
            parser.error("--fixture is required with --expected-resources")
        evidence = args.evidence or Path(tempfile.gettempdir()) / (
            "skilling-package-evidence-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        )
        smoke(
            args.source.resolve() if args.source is not None else None,
            args.dist.resolve(),
            evidence.resolve(),
            args.python_version,
            fixture=args.fixture.resolve() if args.fixture is not None else None,
            expected_resources_path=(
                args.expected_resources.resolve() if args.expected_resources is not None else None
            ),
            source_must_not_exist=(
                args.source_must_not_exist.resolve()
                if args.source_must_not_exist is not None
                else None
            ),
        )


if __name__ == "__main__":
    main()
