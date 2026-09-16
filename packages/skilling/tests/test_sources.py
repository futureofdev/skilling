"""Resolving a course ref to a validated, cached course directory.

Local paths and the refusal-on-findings rule are testable offline. A `file://` remote
exercises a real `git` fetch against a hermetic bare repository, so the cache-hit contract
(re-resolving the same ref touches no network) is proven for real rather than assumed. The
`gh:` shorthand's pin grammar — tag, branch, full sha, and the full-history fallback for
servers that refuse sha-in-want — is proven against the same hermetic remotes by rewriting
only the expanded github.com URL at the subprocess boundary, since a real GitHub fetch has
no place in this suite — a private-repo fetch against the learner's own credentials is
proven end-to-end in a later task.
"""

from __future__ import annotations

import contextlib
import re
import subprocess
from pathlib import Path

import pytest

from skilling.sources import CourseInvalid, GitFailed, ResolveError, UnknownRef, resolve

FAKE_OK = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
GH_URL = "https://github.com/acme/course"


def _push_to_bare(course_root: Path, remote: Path) -> None:
    """Turn a plain course directory into a git repo, commit it, and push it to a bare
    remote — a hermetic stand-in for "a course lives in a git repository somewhere"."""

    def run(*args: str) -> None:
        subprocess.run(["git", *args], cwd=course_root, check=True, capture_output=True, text=True)

    run("init", "-q")
    run("checkout", "-q", "-b", "main")
    run("config", "user.email", "test@example.com")
    run("config", "user.name", "Test")
    run("add", "-A")
    run("commit", "-q", "-m", "clean course")
    run("remote", "add", "origin", str(remote))
    run("push", "-q", "origin", "main")
    # Pin the bare repo's default branch explicitly, so a fetch of HEAD lands on "main"
    # regardless of the local git installation's init.defaultBranch.
    subprocess.run(
        ["git", "symbolic-ref", "HEAD", "refs/heads/main"],
        cwd=remote,
        check=True,
        capture_output=True,
        text=True,
    )


def _push_history_to_bare(course_root: Path, remote: Path) -> str:
    """A remote exercising every pin form: main carries 1.0.0 (tagged v1.0.0), then 1.1.0,
    then 2.0.0 at the tip; a dev branch carries 1.5.0. Returns the full sha of the 1.1.0
    commit, which no branch or tag points at — reachable but unadvertised, exactly the
    commit a sha pin needs sha-in-want (or the full-history fallback) to reach."""
    subprocess.run(
        ["git", "init", "--bare", "-q", str(remote)], check=True, capture_output=True, text=True
    )

    def run(*args: str) -> str:
        done = subprocess.run(
            ["git", *args], cwd=course_root, check=True, capture_output=True, text=True
        )
        return done.stdout.strip()

    def commit_version(version: str) -> None:
        manifest = course_root / "course.yaml"
        bumped = re.sub(r"(?m)^version: .*$", f'version: "{version}"', manifest.read_text())
        manifest.write_text(bumped)
        run("commit", "-a", "-q", "-m", version)

    run("init", "-q")
    run("checkout", "-q", "-b", "main")
    run("config", "user.email", "test@example.com")
    run("config", "user.name", "Test")
    run("add", "-A")
    run("commit", "-q", "-m", "1.0.0")
    run("tag", "v1.0.0")
    commit_version("1.1.0")
    unadvertised = run("rev-parse", "HEAD")
    run("checkout", "-q", "-b", "dev")
    commit_version("1.5.0")
    run("checkout", "-q", "main")
    commit_version("2.0.0")
    run("remote", "add", "origin", str(remote))
    run("push", "-q", "--tags", "origin", "main", "dev")
    subprocess.run(
        ["git", "symbolic-ref", "HEAD", "refs/heads/main"],
        cwd=remote,
        check=True,
        capture_output=True,
        text=True,
    )
    return unadvertised


def _redirect_github(monkeypatch: pytest.MonkeyPatch, remote: Path) -> list[list[str]]:
    """Rewrite the gh: shorthand's expanded URL to a local bare repo at the subprocess
    boundary — everything else, pin included, is real git. Returns every git argv run."""
    real_run = subprocess.run
    calls: list[list[str]] = []

    def run(argv, **kwargs):
        argv = [remote.as_uri() if arg == GH_URL else arg for arg in argv]
        calls.append(argv)
        return real_run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", run)
    return calls


def _allow_sha_in_want(remote: Path) -> None:
    """GitHub serves any reachable sha to a fetch request; a plain `git init --bare` remote
    refuses. Opt the fixture remote in so the depth-1 sha fetch runs as it would on GitHub."""
    subprocess.run(
        ["git", "-C", str(remote), "config", "uploadpack.allowAnySHA1InWant", "true"],
        check=True,
        capture_output=True,
        text=True,
    )


def _force_protocol_v0(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wire protocol v2 serves any reachable sha regardless of server config; v0 enforces
    `uploadpack.allowAnySHA1InWant` (default off). Forcing v0 makes the fixture remote
    behave like a real server that refuses sha-in-want."""
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "protocol.version")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "0")


def test_local_path_resolves_without_cache(tmp_path: Path, clean_dir: Path) -> None:
    resolved = resolve(str(clean_dir), cache=tmp_path / "cache")
    assert resolved.path == clean_dir
    assert resolved.ref == str(clean_dir)
    assert resolved.pinned is None
    assert not (tmp_path / "cache").exists()


def test_invalid_course_is_refused_and_never_cached(tmp_path: Path, clean_dir: Path) -> None:
    (clean_dir / "course.yaml").unlink()
    with pytest.raises(CourseInvalid) as exc:
        resolve(str(clean_dir), cache=tmp_path / "cache")
    assert exc.value.findings
    assert not (tmp_path / "cache").exists()


def test_unknown_ref_is_refused(tmp_path: Path) -> None:
    with pytest.raises(UnknownRef):
        resolve(str(tmp_path / "does-not-exist"), cache=tmp_path / "cache")


def test_git_file_remote_fetches_validates_and_caches(tmp_path: Path, clean_dir: Path) -> None:
    remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", "-q", str(remote)], check=True, capture_output=True, text=True
    )
    _push_to_bare(clean_dir, remote)

    resolved = resolve(remote.as_uri(), cache=tmp_path / "cache")
    assert resolved.path == tmp_path / "cache" / "clean-course@1.0.0"
    assert resolved.course.id == "clean-course"
    assert resolved.course.version == "1.0.0"
    mtime = resolved.path.stat().st_mtime

    again = resolve(remote.as_uri(), cache=tmp_path / "cache")  # cache hit: no re-clone
    assert again.path == resolved.path
    assert again.path.stat().st_mtime == mtime


def test_gh_pin_by_tag_resolves_and_caches(
    tmp_path: Path, clean_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = tmp_path / "remote.git"
    _push_history_to_bare(clean_dir, remote)
    _redirect_github(monkeypatch, remote)

    resolved = resolve("gh:acme/course@v1.0.0", cache=tmp_path / "cache")
    assert resolved.course.version == "1.0.0"
    assert resolved.path == tmp_path / "cache" / "clean-course@1.0.0"
    assert resolved.pinned == "v1.0.0"


def test_gh_pin_by_branch_resolves_and_caches(
    tmp_path: Path, clean_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = tmp_path / "remote.git"
    _push_history_to_bare(clean_dir, remote)
    _redirect_github(monkeypatch, remote)

    resolved = resolve("gh:acme/course@dev", cache=tmp_path / "cache")
    assert resolved.course.version == "1.5.0"
    assert resolved.path == tmp_path / "cache" / "clean-course@1.5.0"
    assert resolved.pinned == "dev"


def test_gh_pin_by_full_sha_resolves_and_caches(
    tmp_path: Path, clean_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = tmp_path / "remote.git"
    sha = _push_history_to_bare(clean_dir, remote)
    _allow_sha_in_want(remote)
    calls = _redirect_github(monkeypatch, remote)

    resolved = resolve(f"gh:acme/course@{sha}", cache=tmp_path / "cache")
    assert resolved.course.version == "1.1.0"
    assert resolved.path == tmp_path / "cache" / "clean-course@1.1.0"
    assert resolved.pinned == sha
    fetches = [argv for argv in calls if "fetch" in argv]
    assert fetches and all("--depth" in argv for argv in fetches)  # served directly, no fallback


def test_gh_sha_pin_falls_back_when_server_refuses_sha_in_want(
    tmp_path: Path, clean_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = tmp_path / "remote.git"
    sha = _push_history_to_bare(clean_dir, remote)  # default config: sha-in-want refused
    _force_protocol_v0(monkeypatch)
    calls = _redirect_github(monkeypatch, remote)

    resolved = resolve(f"gh:acme/course@{sha}", cache=tmp_path / "cache")
    assert resolved.course.version == "1.1.0"
    assert resolved.path == tmp_path / "cache" / "clean-course@1.1.0"
    fetches = [argv for argv in calls if "fetch" in argv]
    assert any("--depth" not in argv for argv in fetches)  # the full-history fallback ran


def test_gh_bad_pin_fails_as_git_failed_and_never_caches(
    tmp_path: Path, clean_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = tmp_path / "remote.git"
    _push_history_to_bare(clean_dir, remote)
    _redirect_github(monkeypatch, remote)

    with pytest.raises(GitFailed):
        resolve("gh:acme/course@no-such-pin", cache=tmp_path / "cache")
    with pytest.raises(GitFailed):  # sha-shaped but absent: the fallback fails too
        resolve(f"gh:acme/course@{'f' * 40}", cache=tmp_path / "cache")
    assert not (tmp_path / "cache").exists()


def test_gh_ref_expands_to_github_https(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: calls.append(argv) or FAKE_OK)
    with contextlib.suppress(Exception):
        resolve("gh:acme/course@v1.2.0", cache=Path("/nonexistent"))
    flattened = [arg for argv in calls for arg in argv]
    assert GH_URL in flattened
    assert "v1.2.0" in flattened


def test_gh_ref_without_pin_fetches_remote_head(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: calls.append(argv) or FAKE_OK)
    with contextlib.suppress(Exception):
        resolve("gh:acme/course", cache=Path("/nonexistent"))
    flattened = [arg for argv in calls for arg in argv]
    assert GH_URL in flattened
    assert "HEAD" in flattened


def test_every_git_invocation_disables_terminal_prompts(monkeypatch: pytest.MonkeyPatch) -> None:
    envs: list[dict[str, str] | None] = []
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: envs.append(kw.get("env")) or FAKE_OK)
    with contextlib.suppress(Exception):
        resolve("gh:acme/course@v1.2.0", cache=Path("/nonexistent"))
    assert len(envs) >= 3  # at minimum: init, remote add, fetch
    assert all(env is not None and env["GIT_TERMINAL_PROMPT"] == "0" for env in envs)


def test_resolve_error_hierarchy() -> None:
    assert issubclass(CourseInvalid, ResolveError)
    assert issubclass(UnknownRef, ResolveError)
    assert issubclass(GitFailed, ResolveError)
