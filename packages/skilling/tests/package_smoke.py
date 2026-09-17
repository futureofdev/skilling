"""Install both distributions outside checkout and exercise real-calendar learner state.

Run with Python, not pytest: the controller uses only the standard library. Its probe runs
in each isolated installed environment. This is mechanical CLI/API evidence, not host proof.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from datetime import UTC, datetime
from pathlib import Path


def clean_environment() -> dict[str, str]:
    env = dict(os.environ)
    for name in (
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
    ):
        env.pop(name, None)
    env.update({"PYTHONTZPATH": "", "NO_COLOR": "1", "PYTHONIOENCODING": "utf-8"})
    return env


class Commands:
    def __init__(self, evidence: Path) -> None:
        self.evidence = evidence
        self.count = 0

    def run(self, argv: list[str], cwd: Path) -> str:
        self.count += 1
        stem = self.evidence / f"{self.count:02d}"
        started = datetime.now(UTC).isoformat()
        result = subprocess.run(
            argv,
            cwd=cwd,
            env=clean_environment(),
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
                    "PYTHONTZPATH": "",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        if result.returncode:
            raise RuntimeError(f"Command failed ({result.returncode}): {argv}\n{result.stderr}")
        return result.stdout


def inspect_artifact(artifact: Path, source: Path) -> dict[str, object]:
    files = [
        p
        for p in (source / "packages/skilling/src/skilling").rglob("*")
        if p.is_file() and (p.suffix in {".py", ".md"} or p.name == "py.typed")
    ]
    assert files
    expected = {
        p.relative_to(source / "packages/skilling/src").as_posix(): p.read_bytes() for p in files
    }
    if artifact.suffix == ".whl":
        with zipfile.ZipFile(artifact) as archive:
            for relative, content in expected.items():
                assert archive.read(relative) == content, (artifact, relative)
    else:
        with tarfile.open(artifact) as archive:
            prefix = artifact.name.removesuffix(".tar.gz") + "/src/"
            for relative, content in expected.items():
                member = archive.extractfile(prefix + relative)
                assert member is not None, relative
                assert member.read() == content, (artifact, relative)
    return {
        "file": artifact.name,
        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "matched_package_files": len(expected),
    }


def probe(source: Path, workspace: Path, python_version: str) -> None:
    """Only called by the installed interpreter, after start has made its workspace."""
    from datetime import date, timedelta
    from importlib import metadata
    from zoneinfo import TZPATH

    import skilling
    from skilling.course import Course, today_in
    from skilling.delivery import complete_lesson, load_or_create
    from skilling.skills import SKILL_NAMES, skill_files
    from skilling.store import FileProgressStore

    assert f"{sys.version_info.major}.{sys.version_info.minor}" == python_version, sys.version
    imported = Path(skilling.__file__).resolve()
    assert imported.is_relative_to(Path(sys.prefix).resolve()), imported
    assert not imported.is_relative_to(source), imported
    declared = tomllib.loads((source / "packages/skilling/pyproject.toml").read_text())
    assert skilling.__version__ == metadata.version("skilling") == declared["project"]["version"]
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
    assert today_in("Mars/Olympus", datetime(2026, 8, 3, 23, 30, tzinfo=UTC)) == date(2026, 8, 3)

    bundled_count = 0
    for name in SKILL_NAMES:
        for bundled in skill_files(name):
            relative = bundled.relative_to(
                bundled.parents[1] if bundled.parent.name == "references" else bundled.parent
            )
            for host in (".agents", ".claude"):
                installed = workspace / host / "skills" / name / relative
                assert installed.read_bytes() == bundled.read_bytes(), installed
            bundled_count += 1
    assert bundled_count >= 10

    course = Course.load(workspace / ".skilling/courses/hello-skilling@1.0.0")
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
    assert last is not None
    retried = complete_lesson(store, course, record, revision, last, now=moment + timedelta(days=1))
    assert retried.already_completed and retried.revision == revision
    assert len(store.get_log("local", course.id)) == course.lesson_count
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
                "last_activity": str(record.last_activity),
                "streak_days": record.streak_days,
                "receipt": receipt.coordinate,
            },
            indent=2,
        )
    )


def state_hashes(workspace: Path) -> dict[str, str]:
    root = workspace / ".skilling/state"
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file() and p.name != ".skilling.lock"
    }


def submission_probe(workspace: Path, token: str) -> None:
    """Check the installed public API against the CLI's already accepted token."""
    from datetime import timedelta

    import skilling
    from skilling.delivery import submit_homework
    from skilling.store import (
        FileProgressStore,
        ProgressStore,
        SubmissionCommit,
        SubmissionCommitResult,
        SubmissionReceipt,
        SubmissionToken,
    )

    assert Path(skilling.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    store = FileProgressStore(workspace / ".skilling/state")
    assert isinstance(store, ProgressStore)
    identity = SubmissionToken.parse(token)
    receipt = store.get_submission_receipt("local", "hello-skilling", token)
    assert isinstance(receipt, SubmissionReceipt)
    before = state_hashes(workspace)
    retry = submit_homework(
        store,
        "local",
        "hello-skilling",
        identity.coordinate,
        token=token,
        now=receipt.archive.submitted_at + timedelta(days=1),
    )
    assert retry == receipt.archive
    committed = store.commit_submission(SubmissionCommit(receipt, identity.slot_revision, None))
    assert isinstance(committed, SubmissionCommitResult)
    assert committed.replayed and committed.receipt == receipt
    assert store.get_homework("local", "hello-skilling") == (None, None)
    assert store.get_homework_archive("local", "hello-skilling") == [receipt.archive]
    assert state_hashes(workspace) == before
    print(
        json.dumps(
            {
                "public_submission_api": "passed",
                "archive_count": 1,
                "original_submitted_at": receipt.archive.submitted_at.isoformat(),
                "next_day_replay": True,
                "replay_state_unchanged": True,
            },
            indent=2,
        )
    )


def check_submission(
    commands: Commands, python: Path, cli: Path, source: Path, workspace: Path
) -> None:
    """Synthetic confirmation mechanics; no claim of a real learner interaction."""
    before = state_hashes(workspace)
    checked = json.loads(
        commands.run([str(cli), "homework", "check", "--course", "hello-skilling"], workspace)
    )
    assert state_hashes(workspace) == before
    token = checked["submission_token"]
    assert isinstance(token, str) and token
    assert checked["active"] is not None
    argv = [str(cli), "homework", "submit", "--course", "hello-skilling", "--token", token]
    submitted = json.loads(commands.run(argv, workspace))
    after = state_hashes(workspace)
    replayed = json.loads(commands.run(argv, workspace))
    assert replayed["archived"] == submitted["archived"]
    assert state_hashes(workspace) == after
    empty = json.loads(
        commands.run([str(cli), "homework", "check", "--course", "hello-skilling"], workspace)
    )
    assert empty["active"] is None and empty["submission_token"] is None
    assert state_hashes(workspace) == after
    commands.run(
        [
            str(python),
            str(Path(__file__).resolve()),
            "--submission-probe",
            token,
            "--source",
            str(source),
            "--workspace",
            str(workspace),
        ],
        workspace,
    )


def smoke(source: Path, dist: Path, evidence: Path, python_version: str) -> None:
    assert f"{sys.version_info.major}.{sys.version_info.minor}" == python_version, sys.version
    evidence.mkdir(parents=True, exist_ok=False)
    version = tomllib.loads((source / "packages/skilling/pyproject.toml").read_text())["project"][
        "version"
    ]
    artifacts = [dist / f"skilling-{version}-py3-none-any.whl", dist / f"skilling-{version}.tar.gz"]
    inspections = [inspect_artifact(artifact, source) for artifact in artifacts]
    (evidence / "artifacts.json").write_text(json.dumps(inspections, indent=2), encoding="utf-8")
    commands = Commands(evidence)
    root = Path(tempfile.mkdtemp(prefix="skilling-package-smoke-"))
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
            bin_dir = env / ("Scripts" if os.name == "nt" else "bin")
            python = bin_dir / ("python.exe" if os.name == "nt" else "python")
            cli = bin_dir / ("skilling.exe" if os.name == "nt" else "skilling")
            commands.run(["uv", "pip", "install", "--python", str(python), str(artifact)], case)
            commands.run([str(cli), "--version"], case)
            course = case / "course"
            shutil.copytree(source / "examples/hello-skilling", course)
            workspace = case / "workspace"
            commands.run([str(cli), "start", str(course), str(workspace), "--json"], case)
            first = json.loads(
                commands.run([str(cli), "next", "--course", "hello-skilling"], workspace)
            )
            assert first["beat"]["name"] == "welcome", first
            commands.run([str(cli), "progress", "--course", "hello-skilling"], workspace)
            for host in ("agents", "claude"):
                commands.run([str(cli), "install", "--platform", host], workspace)
            commands.run(
                [
                    str(python),
                    str(Path(__file__).resolve()),
                    "--probe",
                    "--source",
                    str(source),
                    "--workspace",
                    str(workspace),
                    "--python-version",
                    python_version,
                ],
                workspace,
            )
            resumed = json.loads(
                commands.run([str(cli), "next", "--course", "hello-skilling"], workspace)
            )
            assert resumed["beat"]["name"] == "done", resumed
            commands.run([str(cli), "progress", "--course", "hello-skilling"], workspace)
            check_submission(commands, python, cli, source, workspace)
            shutil.copytree(workspace / ".skilling/state", evidence / f"{kind}-state")
        succeeded = True
    finally:
        (evidence / "result.json").write_text(json.dumps({"passed": succeeded}), encoding="utf-8")
        if succeeded:
            shutil.rmtree(root)
    print(f"Installed wheel and sdist passed; evidence: {evidence}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--dist", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument(
        "--python-version", default=f"{sys.version_info.major}.{sys.version_info.minor}"
    )
    parser.add_argument("--probe", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--submission-probe", help=argparse.SUPPRESS)
    parser.add_argument("--workspace", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.submission_probe:
        if args.workspace is None:
            parser.error("--submission-probe needs --workspace")
        submission_probe(args.workspace.resolve(), args.submission_probe)
    elif args.probe:
        if args.workspace is None:
            parser.error("--probe needs --workspace")
        probe(args.source.resolve(), args.workspace.resolve(), args.python_version)
    else:
        if args.dist is None:
            parser.error("--dist is required")
        evidence = args.evidence or Path(tempfile.gettempdir()) / (
            "skilling-package-evidence-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        )
        smoke(args.source.resolve(), args.dist.resolve(), evidence.resolve(), args.python_version)


if __name__ == "__main__":
    main()
