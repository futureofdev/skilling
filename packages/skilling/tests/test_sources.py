"""Resolving a course ref to a validated, cached course directory.

Local paths and the refusal-on-findings rule are testable offline. A `file://` remote
exercises a real `git clone` against a hermetic bare repository, so the cache-hit contract
(re-resolving the same ref touches no network) is proven for real rather than assumed. The
`gh:` shorthand's URL expansion is proven against a monkeypatched `subprocess.run`, since a
real GitHub fetch has no place in this suite — a private-repo fetch against the learner's
own credentials is proven end-to-end in a later task.
"""

from __future__ import annotations

import contextlib
import subprocess
from pathlib import Path

import pytest

from skilling.sources import CourseInvalid, ResolveError, UnknownRef, resolve

FAKE_OK = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")


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
    # Pin the bare repo's default branch explicitly, so a clone with no --branch lands on
    # "main" regardless of the local git installation's init.defaultBranch.
    subprocess.run(
        ["git", "symbolic-ref", "HEAD", "refs/heads/main"],
        cwd=remote,
        check=True,
        capture_output=True,
        text=True,
    )


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

    resolved = resolve(f"file://{remote}", cache=tmp_path / "cache")
    assert resolved.path == tmp_path / "cache" / "clean-course@1.0.0"
    assert resolved.course.id == "clean-course"
    assert resolved.course.version == "1.0.0"
    mtime = resolved.path.stat().st_mtime

    again = resolve(f"file://{remote}", cache=tmp_path / "cache")  # cache hit: no re-clone
    assert again.path == resolved.path
    assert again.path.stat().st_mtime == mtime


def test_gh_ref_expands_to_github_https(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, list[str]] = {}
    monkeypatch.setattr(
        subprocess, "run", lambda argv, **kw: seen.setdefault("argv", argv) or FAKE_OK
    )
    with contextlib.suppress(Exception):
        resolve("gh:acme/course@v1.2.0", cache=Path("/nonexistent"))
    assert "https://github.com/acme/course" in seen["argv"]
    assert "v1.2.0" in seen["argv"]


def test_gh_ref_without_pin_omits_branch_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, list[str]] = {}
    monkeypatch.setattr(
        subprocess, "run", lambda argv, **kw: seen.setdefault("argv", argv) or FAKE_OK
    )
    with contextlib.suppress(Exception):
        resolve("gh:acme/course", cache=Path("/nonexistent"))
    assert "https://github.com/acme/course" in seen["argv"]
    assert "--branch" not in seen["argv"]


def test_resolve_error_hierarchy() -> None:
    assert issubclass(CourseInvalid, ResolveError)
    assert issubclass(UnknownRef, ResolveError)
