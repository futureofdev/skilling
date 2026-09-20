"""Executable and textual contracts for the learner-first front door."""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
from pathlib import Path

from rich.text import Text
from typer.testing import CliRunner

from skilling.cli import app

from .conftest import REPO_ROOT

WELCOME = REPO_ROOT / "examples" / "welcome-skilling"
ROOT_README = REPO_ROOT / "README.md"
PACKAGE_README = REPO_ROOT / "packages" / "skilling" / "README.md"
INSTALL = "uv tool install 'skilling==0.5.0'"
START = (
    "skilling start 'gh:futureofdev/skilling@v0.5.0#examples/welcome-skilling' my-learning --json"
)
CANONICAL_PROMPT = (
    "Check that Git and uv are available. If either is missing, stop and show me the matching "
    "official installation instructions linked from the Skilling README. Install Skilling "
    "persistently with `uv tool install 'skilling==0.5.0'`, then run `skilling --version` in "
    "the same environment. Run `skilling start "
    "'gh:futureofdev/skilling@v0.5.0#examples/welcome-skilling' my-learning --json`. Use the "
    "returned workspace path, read its generated host instructions and installed learn skill "
    "and references, run learner commands from that workspace, and start teaching me. Wait "
    "for my real replies at every gate. If this host must be reopened to discover the "
    "installed skills, tell me the exact workspace to open and to invoke `/learn` in Claude "
    "Code or `$learn` in Codex."
)

runner = CliRunner()


def run(args: list[str], home: Path):
    return runner.invoke(app, args, env={"HOME": str(home)}, catch_exceptions=False)


def test_local_welcome_start_courses_next_is_offline_and_workspace_aware(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("SKILLING_STATE_ROOT", raising=False)
    monkeypatch.delenv("SKILLING_WORKSPACE", raising=False)
    workspace = tmp_path / "learning"
    home = tmp_path / "unused-home"

    started = run(["start", str(WELCOME), str(workspace), "--json"], home)
    assert started.exit_code == 0, started.output
    payload = json.loads(started.stdout)
    assert payload["course"]["id"] == "welcome-skilling"
    assert payload["workspace"] == str(workspace.resolve())

    monkeypatch.chdir(workspace / "showcase" / "welcome-skilling")
    listed = run(["courses", "--json"], home)
    assert listed.exit_code == 0, listed.output
    assert json.loads(listed.stdout)["courses"][0]["id"] == "welcome-skilling"

    resumed = run(["next", "--course", "welcome-skilling"], home)
    assert resumed.exit_code == 0, resumed.output
    assert json.loads(resumed.stdout)["beat"]["name"] == "welcome"
    assert not (home / ".skilling").exists()


def test_documented_pinned_github_route_executes_through_local_git_redirect(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repository = tmp_path / "redirected-skilling"
    course = repository / "examples" / "welcome-skilling"
    course.parent.mkdir(parents=True)
    shutil.copytree(WELCOME, course)
    for args in (
        ["init", "-q"],
        ["config", "user.name", "Test"],
        ["config", "user.email", "test@example.invalid"],
        ["add", "."],
        ["commit", "-qm", "candidate"],
        ["tag", "v0.5.0"],
    ):
        subprocess.run(["git", *args], cwd=repository, check=True, capture_output=True)

    replacement = repository.as_uri()
    monkeypatch.setenv("GIT_CONFIG_COUNT", "2")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", f"url.{replacement}.insteadOf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "https://github.com/futureofdev/skilling")
    monkeypatch.setenv("GIT_CONFIG_KEY_1", "protocol.file.allow")
    monkeypatch.setenv("GIT_CONFIG_VALUE_1", "always")
    monkeypatch.setenv("GIT_ALLOW_PROTOCOL", "file")
    monkeypatch.chdir(tmp_path)

    documented = shlex.split(START)
    assert documented[0] == "skilling"
    result = run(documented[1:], tmp_path / "unused-home")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["course"]["id"] == "welcome-skilling"
    assert payload["workspace"] == str((tmp_path / "my-learning").resolve())


def test_workspace_resume_survives_nested_execution_and_relocation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("SKILLING_STATE_ROOT", raising=False)
    monkeypatch.delenv("SKILLING_WORKSPACE", raising=False)
    original = tmp_path / "original" / "learning"
    home = tmp_path / "unused-home"
    assert run(["start", str(WELCOME), str(original), "--json"], home).exit_code == 0

    nested = original / "showcase" / "welcome-skilling" / "notes"
    nested.mkdir()
    monkeypatch.chdir(nested)
    assert run(["next", "--course", "welcome-skilling"], home).exit_code == 0

    destination = tmp_path / "moved" / "learning"
    destination.parent.mkdir()
    # Windows locks the process' current directory, so leave the workspace before
    # simulating its relocation.
    monkeypatch.chdir(tmp_path)
    shutil.move(original, destination)
    monkeypatch.chdir(destination / "showcase" / "welcome-skilling" / "notes")

    listed = run(["courses", "--json"], home)
    assert listed.exit_code == 0, listed.output
    course = json.loads(listed.stdout)["courses"][0]
    assert course["id"] == "welcome-skilling"
    assert course["path"].startswith(str(destination.resolve()))
    assert run(["next", "--course", "welcome-skilling"], home).exit_code == 0


def test_readmes_share_the_persistent_install_and_pinned_start_route() -> None:
    root = ROOT_README.read_text(encoding="utf-8")
    package = PACKAGE_README.read_text(encoding="utf-8")
    for text in (root, package):
        assert INSTALL in text
        assert "skilling --version" in text
        assert START in text
        assert "uvx" not in text
        assert "Claude Code" in text and "Codex" in text
        assert "/learn" in text and "$learn" in text

    lines = root.splitlines()
    first = next(index for index, line in enumerate(lines) if line.startswith("> Check that"))
    prompt_lines: list[str] = []
    for line in lines[first:]:
        if not line.startswith("> "):
            break
        prompt_lines.append(line.removeprefix("> ").strip())
    prompt = " ".join(prompt_lines)
    assert prompt == CANONICAL_PROMPT
    for command in (INSTALL, "skilling --version", START, "/learn", "$learn"):
        assert command in prompt
    assert root.index("## Start learning") < root.index("## Write a course")
    assert package.index("## Start learning") < package.index("## For course authors")


def test_guides_keep_required_learner_source_troubleshooting_and_author_topics() -> None:
    guides = {
        "docs/learning-a-course.md": (
            "## Create your first workspace",
            "## Stop and resume",
            "## Homework and confirmation",
            "## Keep your work visible",
            "## Add another course",
            "## Work from nested folders",
            "## Move the workspace",
            "separate confirmation",
        ),
        "docs/course-sources.md": (
            "## GitHub shorthand",
            "full commit",
            "## Generic Git URLs",
            "## Local directories and downloaded archives",
            "## Private repositories",
            "There is no automatic update service",
            "does not promise that a cloud-hosted tutor model works without network access",
        ),
        "docs/troubleshooting.md": (
            "## Git or uv is missing",
            "## `skilling` is not found",
            "## `/learn` or `$learn` is unavailable",
            "## The course cannot be fetched",
            "## Recovery refuses to continue",
        ),
        "docs/authoring-a-course.md": (
            "## 1. Install and scaffold",
            "Add a `README.md`\nfor learners",
            "licence",
            "## 4. Validate strictly",
            "## 5. Preview as a learner",
            "## 6. Publish a stable source",
            "Publish the tested command",
        ),
    }
    for relative, required in guides.items():
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        for phrase in required:
            assert phrase in text, f"{relative} does not cover {phrase!r}"


def test_learner_front_door_excludes_unsupported_hosts_and_claims() -> None:
    paths = (
        ROOT_README,
        PACKAGE_README,
        REPO_ROOT / "docs" / "learning-a-course.md",
        REPO_ROOT / "docs" / "course-sources.md",
        REPO_ROOT / "docs" / "troubleshooting.md",
    )
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    for unsupported in ("Cowork", "ChatGPT Work", "SCP-style refs are supported"):
        assert unsupported not in text
    assert "30 seconds" not in text
    assert "Skilling does not download ZIP archives directly" in text
    assert "does not make a cloud coding host or model operate offline" in text


def test_source_guide_pins_supported_grammar_identity_and_authentication() -> None:
    text = (REPO_ROOT / "docs" / "course-sources.md").read_text(encoding="utf-8")
    for supported in (
        "gh:owner/repository",
        "gh:owner/repository@v1.0.0",
        "gh:owner/repository@0123456789abcdef0123456789abcdef01234567",
        "gh:owner/repository@v1.0.0#courses/my-course",
        "https://example.com/team/course.git",
        "ssh://git@example.com/team/course.git",
        "git+ssh://git@example.com/team/course.git",
        "skilling start ../my-course my-learning --json",
    ):
        assert supported in text
    for required in (
        "Generic URLs do **not** support",
        "SCP-style `git@example.com:repo.git`",
        "is not a supported Skilling ref",
        "credentials already configured",
        "Skilling does not define a second login flow",
        "copies a portable snapshot",
        "Repeating the exact ref verifies and reuses that cached snapshot",
        "There is no automatic update service",
        "Move the whole workspace",
    ):
        assert required in text


def test_cli_help_and_start_output_put_the_learner_route_first(tmp_path: Path) -> None:
    help_result = runner.invoke(app, ["--help"])
    plain = Text.from_ansi(help_result.output).plain
    assert help_result.exit_code == 0
    assert plain.index("start") < plain.index("validate")

    workspace = tmp_path / "learning"
    started = run(["start", str(WELCOME), str(workspace)], tmp_path / "home")
    assert started.exit_code == 0, started.output
    assert f"open {workspace.resolve()}" in started.output
    assert "/learn" in started.output and "$learn" in started.output
