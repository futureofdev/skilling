"""Fail-closed release workflow, handoff, and tag rehearsals."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

from .conftest import REPO_ROOT

WORKFLOW_PATH = REPO_ROOT / ".github/workflows/release.yml"
RUNBOOK_PATH = REPO_ROOT / "docs/releasing.md"
HELPER_PATH = REPO_ROOT / "tools/release_candidate.py"
ACTION_PINS = {
    "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",
    "astral-sh/setup-uv": "c771a70e6277c0a99b617c7a806ffedaca235ff9",
    "go-task/setup-task": "01a4adf9db2d14c1de7a560f09170b6e0df736aa",
    "actions/upload-artifact": "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
    "actions/download-artifact": "37930b1c2abaa49bbe596cd826c3c89aef350131",
    "pypa/gh-action-pypi-publish": "dc37677b2e1c63e2034f94d8a5b11f265b73ba33",
}


def workflow() -> dict[Any, Any]:
    loaded = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def release_helper() -> ModuleType:
    spec = importlib.util.spec_from_file_location("release_candidate", HELPER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def step_runs(job: dict[str, Any]) -> str:
    steps = job["steps"]
    assert isinstance(steps, list)
    return "\n".join(str(step.get("run", "")) for step in steps)


def test_release_has_only_manual_trigger_and_deny_all_default_permissions() -> None:
    data = workflow()
    triggers = data.get("on", data.get(True))

    assert isinstance(triggers, dict)
    assert set(triggers) == {"workflow_dispatch"}
    assert triggers["workflow_dispatch"]["inputs"]["candidate_sha"]["required"] is True
    assert data["permissions"] == {}
    assert "pull_request" not in WORKFLOW_PATH.read_text(encoding="utf-8")


def test_runner_scoped_candidate_directory_is_only_in_step_environments() -> None:
    data = workflow()
    build = data["jobs"]["build"]
    candidate_directory = "${{ runner.temp }}/skilling-0.5.0-candidate"

    assert "runner." not in str(data.get("env", {}))
    assert "runner." not in str(build.get("env", {}))
    assert [
        step["env"]["CANDIDATE_DIR"]
        for step in build["steps"]
        if "CANDIDATE_DIR" in step.get("env", {})
    ] == [candidate_directory, candidate_directory]


def test_build_rejects_mutable_or_non_default_branch_input_and_runs_full_gates() -> None:
    data = workflow()
    build = data["jobs"]["build"]
    commands = step_runs(build)

    assert build["permissions"] == {"contents": "read"}
    assert "DEFAULT_BRANCH" in commands and 'test "$DEFAULT_BRANCH" = main' in commands
    assert 'test "$GITHUB_REF" = "refs/heads/$DEFAULT_BRANCH"' in commands
    assert 'test "$DISPATCH_SHA" = "$CANDIDATE_SHA"' in commands
    assert 'git rev-parse "origin/$DEFAULT_BRANCH"' in commands
    assert "git diff-index --quiet HEAD" in commands
    for gate in ("uv lock --check", "uv sync", "task check", "test_versioning.py"):
        assert gate in commands
    assert commands.count("uv build --package skilling") == 1
    assert '--out-dir "$RUNNER_TEMP/skilling-dist"' in commands
    assert "--out-dir dist" not in commands
    assert 'rm -f "$RUNNER_TEMP/skilling-dist/.gitignore"' in commands
    assert (
        commands.index("uv build --package skilling")
        < commands.index('rm -f "$RUNNER_TEMP/skilling-dist/.gitignore"')
        < commands.index("package_smoke.py")
    )
    assert 'package_smoke.py --source . --dist "$RUNNER_TEMP/skilling-dist"' in commands
    assert 'source_package_smoke.py --source . --dist "$RUNNER_TEMP/skilling-dist"' in commands
    assemble = next(
        step["run"]
        for step in build["steps"]
        if step.get("name") == "Assemble and verify retained candidate"
    )
    assert '--dist "$RUNNER_TEMP/skilling-dist"' in assemble
    assert "--dist dist" not in assemble
    assert "--evidence source-package-evidence" in commands
    assert "brand/build.py --zip-only" in commands
    assert "--with pillow brand/build.py" not in commands
    assert "--source-must-not-exist" in commands and 'rm -rf "$unavailable"' in commands
    assert 'cp tools/release_candidate.py "$release_helper"' in commands
    assert "export PYTHONDONTWRITEBYTECODE=1" in commands
    assert 'python -B "$controller"' in commands
    assert 'python -B "$release_helper" verify --candidate "$CANDIDATE_DIR"' in commands
    assert "trap 'mkdir -p \"$unavailable\"' EXIT" in commands
    assert commands.count('mkdir -p "$unavailable"') == 2
    assert commands.index('rm -rf "$unavailable"') < commands.index('python -B "$controller"')
    assert commands.index('python -B "$controller"') < commands.index(
        'python -B "$release_helper" verify'
    )
    assert commands.index('python -B "$release_helper" verify') < commands.index("trap - EXIT")


def test_build_upload_and_publish_download_one_named_immutable_handoff() -> None:
    data = workflow()
    build_steps = data["jobs"]["build"]["steps"]
    publish = data["jobs"]["publish"]
    publish_steps = publish["steps"]
    uploads = [
        step
        for step in build_steps
        if str(step.get("uses", "")).startswith("actions/upload-artifact@")
    ]
    downloads = [
        step
        for step in publish_steps
        if str(step.get("uses", "")).startswith("actions/download-artifact@")
    ]

    assert len(uploads) == len(downloads) == 1
    assert uploads[0]["with"]["name"] == downloads[0]["with"]["name"]
    assert uploads[0]["with"]["name"] == "skilling-0.5.0-candidate"
    assert uploads[0]["with"]["if-no-files-found"] == "error"
    assert publish["needs"] == "build"
    assert publish["environment"] == "pypi"
    assert publish["permissions"] == {"contents": "read", "id-token": "write"}
    assert "id-token" not in str(data["jobs"]["build"].get("permissions", {}))


def test_publish_verifies_complete_handoff_and_exposes_only_dist_to_pypi() -> None:
    data = workflow()
    publish = data["jobs"]["publish"]
    commands = step_runs(publish)
    pypi = next(
        step
        for step in publish["steps"]
        if str(step.get("uses", "")).startswith("pypa/gh-action-pypi-publish@")
    )

    assert "release_candidate.py verify" in commands
    assert "--require-tag 0.5.0" in commands
    assert "uv build" not in commands and "brand/build.py" not in commands
    assert "candidate/verification" not in commands
    assert pypi["with"] == {"packages-dir": "candidate/dist"}


def test_all_release_actions_are_bound_to_reviewed_commits() -> None:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    found = dict(re.findall(r"uses:\s+([^@\s]+)@([0-9a-f]{40})", text))

    assert found == ACTION_PINS
    assert (
        f"pypa/gh-action-pypi-publish@{ACTION_PINS['pypa/gh-action-pypi-publish']} # v1.14.2"
        in text
    )


def test_candidate_layout_and_checksum_contract_are_exact() -> None:
    helper = release_helper()

    assert helper.CANDIDATE_ARTIFACT == "skilling-0.5.0-candidate"
    assert helper.CHECKSUM_PATHS == (
        "dist/skilling-0.5.0-py3-none-any.whl",
        "dist/skilling-0.5.0.tar.gz",
        "github-release/skilling-brand-assets-v2.0.zip",
    )
    helper_text = HELPER_PATH.read_text(encoding="utf-8")
    for retained in (
        "candidate.json",
        "SHA256SUMS",
        "verification/resources.json",
        "package_smoke.py",
        "source_package_smoke.py",
        "import_package_probe.py",
        "welcome-skilling",
    ):
        assert retained in helper_text or retained in RUNBOOK_PATH.read_text(encoding="utf-8")
    assert '"\\n".join(sorted(checksum_lines))' in helper_text
    assert 'f"{sha256(output / relative)}  {relative}"' in helper_text


def test_verifier_rejects_an_unexpected_directory(tmp_path: Path) -> None:
    helper = release_helper()
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "unexpected").mkdir()

    with pytest.raises(SystemExit, match="candidate layout mismatch"):
        helper.verify(candidate, source=None, require_tag=None)


def test_verifier_rejects_a_symlinked_wheel(tmp_path: Path) -> None:
    helper = release_helper()
    candidate = tmp_path / "candidate"
    dist = candidate / "dist"
    dist.mkdir(parents=True)
    outside = tmp_path / "outside.whl"
    outside.write_bytes(b"not a wheel")
    wheel = dist / "skilling-0.5.0-py3-none-any.whl"
    try:
        wheel.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")

    with pytest.raises(SystemExit, match="candidate contains a symlink"):
        helper.verify(candidate, source=None, require_tag=None)


@pytest.mark.parametrize("unsafe", ["../escape", "/absolute", "nested//file", "nested\\file"])
def test_manifest_paths_cannot_traverse_the_candidate(unsafe: str) -> None:
    helper = release_helper()

    with pytest.raises(SystemExit, match="unsafe fixture path"):
        helper.manifest_relative_path(unsafe, "fixture")


def git(repo: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=check,
    )


def tag_check(repo: Path, sha: str, version: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(HELPER_PATH),
            "check-tag",
            "--source",
            str(repo),
            "--candidate-sha",
            sha,
            "--version",
            version,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_disposable_tag_rehearsals_reject_wrong_version_and_history(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "release-test@example.invalid")
    git(repo, "config", "user.name", "Release test")
    tracked = repo / "tracked.txt"
    tracked.write_text("first\n", encoding="utf-8")
    git(repo, "add", "tracked.txt")
    git(repo, "commit", "-qm", "first")
    previous = git(repo, "rev-parse", "HEAD").stdout.strip()
    tracked.write_text("second\n", encoding="utf-8")
    git(repo, "commit", "-qam", "second")
    candidate = git(repo, "rev-parse", "HEAD").stdout.strip()

    git(repo, "tag", "v0.5.0", candidate)
    assert tag_check(repo, candidate, "0.5.0").returncode == 0

    wrong_version = tag_check(repo, candidate, "0.5.1")
    assert wrong_version.returncode != 0
    assert "expected '0.5.0'" in wrong_version.stderr

    git(repo, "tag", "-f", "v0.5.0", previous)
    wrong_history = tag_check(repo, candidate, "0.5.0")
    assert wrong_history.returncode != 0
    assert f"points to {previous}" in wrong_history.stderr


def test_runbook_retains_brand_bytes_and_names_all_blockers() -> None:
    text = RUNBOOK_PATH.read_text(encoding="utf-8")

    for required in (
        "protect `main`",
        "immutable GitHub releases",
        "protected `pypi` environment",
        "reviewer other than the dispatcher",
        "PyPI `skilling` project and owner roles",
        "trusted publishing",
        "futureofdev",
        "release.yml",
        "skilling-brand-assets-v2.0.zip",
        "do not run the brand generator again",
        "read the setting back",
        "same retained artifact",
    ):
        assert required in text
    assert "candidate/dist/" in text
    assert "never package inputs" in text
