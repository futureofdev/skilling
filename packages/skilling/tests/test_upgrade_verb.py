"""``skilling upgrade``: the explicit, fresh-fetching route to a newer course version.

Remotes are hermetic ``file://`` bare repositories, so every fetch, tag listing and cache
publication is real Git and the real cache; only the network is absent.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skilling.cli import app
from skilling.sources import UpdateKind, find_update

from . import fixtures as fx

runner = CliRunner()
COURSE = "clean-course"


class Remote:
    """An author's checkout of the clean course pushing to a bare remote."""

    def __init__(self, root: Path) -> None:
        self.checkout = fx.build(root / "author")
        self.bare = root / "remote.git"
        subprocess.run(["git", "init", "--bare", "-q", str(self.bare)], check=True)
        self.git("init", "-q")
        self.git("checkout", "-q", "-b", "main")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "1.0.0")
        self.git("remote", "add", "origin", str(self.bare))
        self.git("push", "-q", "origin", "main")
        subprocess.run(
            ["git", "symbolic-ref", "HEAD", "refs/heads/main"], cwd=self.bare, check=True
        )

    @property
    def url(self) -> str:
        return self.bare.as_uri()

    def git(self, *args: str) -> str:
        done = subprocess.run(
            ["git", *args], cwd=self.checkout, check=True, capture_output=True, text=True
        )
        return done.stdout.strip()

    def release(self, version: str, *, tag: str | None = None, edit: str = "") -> None:
        manifest = self.checkout / fx.MANIFEST_PATH
        manifest.write_text(
            re.sub(r"(?m)^version: .*$", f'version: "{version}"', manifest.read_text())
        )
        lesson = self.checkout / fx.LESSON_ONE_PATH
        lesson.write_text(lesson.read_text().replace("worth knowing", f"worth knowing{edit}"))
        self.git("commit", "-a", "-q", "-m", version)
        if tag:
            self.git("tag", tag)
        self.git("push", "-q", "--tags", "origin", "main")

    def tag(self, name: str) -> None:
        self.git("tag", name)
        self.git("push", "-q", "--tags", "origin", "main")


def cli(*args: str) -> tuple[int, dict]:
    result = runner.invoke(app, list(args), catch_exceptions=False)
    try:
        body = json.loads(result.stdout)
    except json.JSONDecodeError:
        body = {"raw": result.output}
    return result.exit_code, body


def started(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ref: str) -> Path:
    for name in ("SKILLING_STATE_ROOT", "SKILLING_WORKSPACE", "SKILLING_CACHE_DIR"):
        monkeypatch.delenv(name, raising=False)
    workspace = tmp_path / "ws"
    result = runner.invoke(app, ["start", ref, str(workspace), "--json"])
    assert result.exit_code == 0, result.output
    monkeypatch.chdir(workspace)
    code, body = cli("next", "--course", COURSE)
    assert code == 0, body
    return workspace


def learner_bytes(workspace: Path) -> dict[str, bytes]:
    skilling = workspace / ".skilling"
    files = [skilling / "workspace.yaml", *(skilling / "state").rglob("*")]
    return {
        p.relative_to(workspace).as_posix(): p.read_bytes()
        for p in files
        if p.is_file() and p.name != ".skilling.lock"
    }


def record_version(workspace: Path) -> str:
    text = (workspace / ".skilling" / "state" / COURSE / "record.yaml").read_text()
    match = re.search(r'(?m)^course_version: [\'"]?([^\'"\n]+)', text)
    assert match is not None
    return match[1]


# ------------------------------------------------------------------- check: fresh, read-only


def test_check_fetches_fresh_offers_same_major_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = Remote(tmp_path)
    remote.tag("v1.0.0")
    workspace = started(tmp_path, monkeypatch, remote.url)
    remote.release("1.0.1", tag="v1.0.1", edit=" indeed")
    remote.release("2.0.0", tag="v2.0.0", edit=" twice")

    # A repeated ref stays a snapshot for ordinary resolution: start never sees 1.0.1.
    again = runner.invoke(app, ["start", remote.url, str(workspace), "--json"])
    assert json.loads(again.stdout)["course"]["version"] == "1.0.0"
    before = learner_bytes(workspace)

    code, body = cli("upgrade", "--course", COURSE, "--json")

    assert code == 0, body
    assert body["status"] == "available"
    assert body["available"] == "1.0.1"
    assert body["source"]["kind"] == "tag"
    assert body["source"]["tag"] == "v1.0.1"
    assert body["source"]["newer_major"] == "v2.0.0"
    assert body["bump"]["declared"] == "patch"
    assert body["bump"]["satisfied"] is True
    assert body["progress"]["status"] == "carries-over"
    assert learner_bytes(workspace) == before  # manifest and record untouched
    assert (workspace / ".skilling" / "courses" / f"{COURSE}@1.0.1").is_dir()

    # The cached newer version becomes a cheap, offline hint on `next`.
    code, out = cli("next", "--course", COURSE)
    assert code == 0
    assert out["upgrade"] == {
        "available": "1.0.1",
        "level": "patch",
        "command": f"skilling upgrade --course {COURSE}",
    }


def test_yes_switches_the_workspace_and_rolls_progress_forward(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = Remote(tmp_path)
    remote.tag("v1.0.0")
    workspace = started(tmp_path, monkeypatch, remote.url)
    remote.release("1.1.0", tag="v1.1.0", edit=" more")

    code, body = cli("upgrade", "--course", COURSE, "--yes", "--json")

    assert code == 0, body
    assert body["status"] == "applied"
    assert body["progress"]["status"] == "rolled-forward"
    manifest = (workspace / ".skilling" / "workspace.yaml").read_text()
    assert "version: 1.1.0" in manifest or "version: '1.1.0'" in manifest
    assert remote.url in manifest  # an unpinned ref keeps its spelling
    assert record_version(workspace) == "1.1.0"
    code, out = cli("next", "--course", COURSE)
    assert code == 0 and "upgrade" not in out
    # The ref now follows the upgrade, so re-running start agrees with the workspace.
    again = runner.invoke(app, ["start", remote.url, str(workspace), "--json"])
    assert again.exit_code == 0, again.output
    assert json.loads(again.stdout)["course"]["version"] == "1.1.0"


def test_without_semver_tags_the_default_branch_head_is_offered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = Remote(tmp_path)
    workspace = started(tmp_path, monkeypatch, remote.url)
    remote.release("1.0.1", edit=" again")
    remote.tag("not-a-release")

    code, body = cli("upgrade", "--course", COURSE, "--json")

    assert code == 0, body
    assert body["source"]["kind"] == "head"
    assert body["available"] == "1.0.1"
    assert record_version(workspace) == "1.0.0"


def test_a_major_head_is_reported_and_yes_refuses_without_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = Remote(tmp_path)
    workspace = started(tmp_path, monkeypatch, remote.url)
    remote.release("2.0.0", edit=" rebuilt")
    before = learner_bytes(workspace)

    code, body = cli("upgrade", "--course", COURSE, "--json")
    assert code == 0
    assert body["progress"]["status"] == "not-resumable"
    assert body["progress"]["reason"] == "major"

    code, body = cli("upgrade", "--course", COURSE, "--yes", "--json")
    assert code == 5
    assert body["error"]["code"] == "version-mismatch"
    assert "major version change" in body["error"]["message"]
    assert learner_bytes(workspace) == before


def test_fresh_content_claiming_an_existing_version_still_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = Remote(tmp_path)
    workspace = started(tmp_path, monkeypatch, remote.url)
    remote.release("1.0.0", edit=" but different")  # same id@version, different payload
    before = learner_bytes(workspace)

    code, body = cli("upgrade", "--course", COURSE, "--json")

    assert code == 3
    assert body["error"]["code"] == "cache-conflict"
    assert learner_bytes(workspace) == before


def test_a_local_source_is_compared_on_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = fx.build(tmp_path / "src" / COURSE)
    workspace = started(tmp_path, monkeypatch, str(source))
    manifest = source / fx.MANIFEST_PATH
    manifest.write_text(manifest.read_text().replace('version: "1.0.0"', 'version: "1.0.1"'))

    code, body = cli("upgrade", "--course", COURSE, "--json")
    assert code == 0, body
    assert (body["status"], body["available"], body["source"]["kind"]) == (
        "available",
        "1.0.1",
        "local",
    )
    assert record_version(workspace) == "1.0.0"

    code, body = cli("upgrade", "--course", COURSE, "--yes", "--json")
    assert code == 0, body
    assert record_version(workspace) == "1.0.1"
    assert (workspace / ".skilling" / "courses" / f"{COURSE}@1.0.1").is_dir()


def test_a_mismatch_points_at_upgrade_instead_of_moving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = fx.build(tmp_path / "src" / COURSE)
    manifest = source / fx.MANIFEST_PATH
    manifest.write_text(manifest.read_text().replace('version: "1.0.0"', 'version: "1.0.1"'))
    workspace = started(tmp_path, monkeypatch, str(source))
    record = (workspace / ".skilling" / "state" / COURSE / "record.yaml").read_bytes()
    # A record behind its workspace content (an interrupted apply, or an older `start`).
    (workspace / ".skilling" / "state" / COURSE / "record.yaml").write_bytes(
        record.replace(b"course_version: 1.0.1", b"course_version: 1.0.0")
    )

    code, body = cli("next", "--course", COURSE)
    assert code == 5
    assert body["error"]["upgrade"]["resumable"] is True
    assert "skilling upgrade --course clean-course --yes" in body["error"]["message"]

    code, body = cli("upgrade", "--course", COURSE, "--yes", "--json")
    assert code == 0, body
    assert body["status"] == "applied"
    assert record_version(workspace) == "1.0.1"
    assert cli("next", "--course", COURSE)[0] == 0


# --------------------------------------------------------------------------- tag selection


def tags(monkeypatch: pytest.MonkeyPatch, names: tuple[str, ...]) -> None:
    from skilling.sources import _git

    monkeypatch.setattr(_git, "remote_tags", lambda url: names)


def test_tag_selection_keeps_the_major_and_reports_a_newer_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tags(monkeypatch, ("v1.0.0", "1.4.0", "v1.10.2", "v1.10.2-rc.1", "v2.1.0", "latest"))
    found = find_update("gh:acme/course", "1.2.0")
    assert (found.kind, found.tag, found.newer_major, found.fetch) == (
        UpdateKind.TAG,
        "v1.10.2",
        "v2.1.0",
        True,
    )
    assert found.ref == "gh:acme/course"  # unpinned refs keep their spelling


def test_a_tag_pinned_ref_moves_to_the_new_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    tags(monkeypatch, ("v1.0.0", "v1.1.0"))
    found = find_update("gh:acme/course@v1.0.0#courses/one", "1.0.0")
    assert found.ref == "gh:acme/course@v1.1.0#courses/one"
    assert find_update("gh:acme/course@v1.1.0", "1.1.0").fetch is False


def test_pins_and_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    tags(monkeypatch, ())
    sha = "0123456789abcdef0123456789abcdef01234567"
    assert find_update(f"gh:acme/course@{sha}", "1.0.0").kind is UpdateKind.PINNED
    branch = find_update("gh:acme/course@dev", "1.0.0")
    assert (branch.kind, branch.pin) == (UpdateKind.BRANCH, "dev")
    assert find_update("https://example.com/course.git", "1.0.0").kind is UpdateKind.HEAD


# ------------------------------------------------------------------- relative local refs


def test_a_relative_local_ref_is_recorded_absolute_and_upgrades_from_inside(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("SKILLING_STATE_ROOT", "SKILLING_WORKSPACE", "SKILLING_CACHE_DIR"):
        monkeypatch.delenv(name, raising=False)
    source = fx.build(tmp_path / "course")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["start", "./course", "ws", "--json"])
    assert result.exit_code == 0, result.output
    workspace = tmp_path / "ws"
    manifest = (workspace / ".skilling" / "workspace.yaml").read_text()
    assert str(source.resolve()) in manifest
    assert "ref: ./course" not in manifest

    monkeypatch.chdir(workspace)
    assert cli("next", "--course", COURSE)[0] == 0
    (source / fx.MANIFEST_PATH).write_text(
        (source / fx.MANIFEST_PATH).read_text().replace('version: "1.0.0"', 'version: "1.0.1"')
    )
    code, body = cli("upgrade", "--course", COURSE, "--check", "--json")
    assert code == 0, body
    assert (body["status"], body["available"]) == ("available", "1.0.1")


def test_a_legacy_relative_ref_gets_an_actionable_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = fx.build(tmp_path / "src" / COURSE)
    workspace = started(tmp_path, monkeypatch, str(source))
    path = workspace / ".skilling" / "workspace.yaml"
    path.write_text(path.read_text().replace(str(source), "./somewhere-else/clean-course"))

    code, body = cli("upgrade", "--course", COURSE, "--json")

    assert code == 1
    assert body["error"]["code"] == "source-unavailable"
    assert "relative path" in body["error"]["message"]
    assert "absolute path" in body["error"]["message"]
