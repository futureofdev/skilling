#!/usr/bin/env python3
"""Assemble and verify the immutable Skilling release-candidate handoff.

The build job is the only caller of ``assemble``. Later jobs download those exact bytes and
call ``verify``; they never rebuild a distribution or the GitHub release attachment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tomllib
import zipfile
from email import policy
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import NoReturn

VERSION = "0.5.0"
SPEC_VERSION = "1.4.0-draft"
CANDIDATE_ARTIFACT = "skilling-0.5.0-candidate"
BRAND_ARCHIVE = "skilling-brand-assets-v2.0.zip"
CHECKSUM_PATHS = (
    f"dist/skilling-{VERSION}-py3-none-any.whl",
    f"dist/skilling-{VERSION}.tar.gz",
    f"github-release/{BRAND_ARCHIVE}",
)
CONTROLLERS = ("package_smoke.py", "source_package_smoke.py", "import_package_probe.py")


def fail(message: str) -> NoReturn:
    raise SystemExit(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_relative_path(value: object, context: str) -> str:
    """Return one canonical candidate-relative POSIX path or fail closed."""
    if not isinstance(value, str) or not value or "\\" in value:
        fail(f"unsafe {context} path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        fail(f"unsafe {context} path: {value!r}")
    return value


def regular_file_hashes(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in [*directories, *files]:
            path = current_path / name
            if path.is_symlink():
                fail(f"source input contains a symlink: {path}")
        for name in files:
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            manifest_relative_path(relative, "source resource")
            hashes[relative] = sha256(path)
    return dict(sorted(hashes.items()))


def reject_candidate_symlinks(root: Path) -> None:
    if root.is_symlink():
        fail(f"candidate contains a symlink: {root}")
    if not root.is_dir():
        fail(f"candidate is not a directory: {root}")
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in [*directories, *files]:
            path = current_path / name
            if path.is_symlink():
                fail(f"candidate contains a symlink: {path.relative_to(root).as_posix()}")


def git(source: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=source,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode:
        fail(result.stderr.strip() or f"git {' '.join(arguments)} failed")
    return result.stdout.strip()


def package_files(source: Path) -> list[Path]:
    root = source / "packages/skilling/src/skilling"
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and (path.suffix in {".py", ".md"} or path.name == "py.typed")
    )


def project_metadata(source: Path) -> dict[str, object]:
    project = tomllib.loads(
        (source / "packages/skilling/pyproject.toml").read_text(encoding="utf-8")
    )["project"]
    dependencies = sorted(
        requirement.split(">=", 1)[0].lower().replace("_", "-")
        for requirement in project["dependencies"]
    )
    return {
        "name": project["name"],
        "version": project["version"],
        "summary": project["description"],
        "requires_python": project["requires-python"],
        "license_expression": project["license"],
        "project_urls": project["urls"],
        "classifiers": project["classifiers"],
        "dependencies": dependencies,
        "entry_point": "skilling = skilling.cli:main",
    }


def archive_metadata(artifact: Path) -> bytes:
    if artifact.suffix == ".whl":
        with zipfile.ZipFile(artifact) as archive:
            name = next(item for item in archive.namelist() if item.endswith(".dist-info/METADATA"))
            return archive.read(name)
    with tarfile.open(artifact) as archive:
        name = next(item for item in archive.getnames() if item.endswith("/PKG-INFO"))
        member = archive.extractfile(name)
        assert member is not None
        return member.read()


def assert_built_metadata(artifact: Path, expected: dict[str, object]) -> str:
    raw = archive_metadata(artifact)
    message = BytesParser(policy=policy.default).parsebytes(raw)
    actual = {
        "name": message["Name"],
        "version": message["Version"],
        "summary": message["Summary"],
        "requires_python": message["Requires-Python"],
        "license_expression": message["License-Expression"],
    }
    for name, value in actual.items():
        if value != expected[name]:
            fail(f"{artifact.name}: metadata {name} is {value!r}, expected {expected[name]!r}")
    separator = b"\r\n\r\n" if b"\r\n\r\n" in raw else b"\n\n"
    return hashlib.sha256(raw.split(separator, 1)[1]).hexdigest()


def source_identity(source: Path) -> dict[str, object]:
    status = git(source, "status", "--porcelain", "--untracked-files=no")
    if status:
        fail("tracked source changed while assembling the candidate")
    return {
        "commit": git(source, "rev-parse", "HEAD"),
        "tree": git(source, "rev-parse", "HEAD^{tree}"),
        "tracked_clean": True,
    }


def expected_resources(source: Path, artifacts: list[Path]) -> dict[str, object]:
    metadata = project_metadata(source)
    if metadata["version"] != VERSION:
        fail(f"package version is {metadata['version']!r}, expected {VERSION!r}")
    files = {
        path.relative_to(source / "packages/skilling/src").as_posix(): sha256(path)
        for path in package_files(source)
    }
    skills = sorted(
        name for name in files if name.startswith("skilling/skills/") and name.endswith(".md")
    )
    readme_hashes = {assert_built_metadata(artifact, metadata) for artifact in artifacts}
    expected_readme = sha256(source / "packages/skilling/README.md")
    if readme_hashes != {expected_readme}:
        fail("built long description does not match packages/skilling/README.md")
    fixture = regular_file_hashes(source / "examples/welcome-skilling")
    controllers = {name: sha256(source / "packages/skilling/tests" / name) for name in CONTROLLERS}
    return {
        "format_version": 1,
        "source": source_identity(source),
        "package": {
            **metadata,
            "license_sha256": sha256(source / "LICENSE"),
            "readme_sha256": expected_readme,
            "files": files,
            "skill_resources": skills,
        },
        "artifacts": [
            {"file": artifact.name, "size": artifact.stat().st_size, "sha256": sha256(artifact)}
            for artifact in artifacts
        ],
        "controllers": controllers,
        "fixture": fixture,
    }


def assert_expected_inputs(source: Path, dist: Path, brand_zip: Path) -> list[Path]:
    if not (source / "brand/build.py").is_file():
        fail("reviewed brand/build.py is absent; merge the learner front-door work first")
    git(source, "ls-files", "--error-unmatch", "brand/build.py")
    if brand_zip.name != BRAND_ARCHIVE or not brand_zip.is_file():
        fail(f"expected generated brand archive {BRAND_ARCHIVE}")
    artifacts = [
        dist / f"skilling-{VERSION}-py3-none-any.whl",
        dist / f"skilling-{VERSION}.tar.gz",
    ]
    actual = sorted(path.name for path in dist.iterdir() if path.is_file())
    if actual != sorted(path.name for path in artifacts) or not all(
        path.is_file() for path in artifacts
    ):
        fail(f"dist must contain exactly the 0.5.0 wheel and sdist; found {actual}")
    return artifacts


def assemble(source: Path, dist: Path, brand_zip: Path, output: Path) -> None:
    if output.exists():
        fail(f"candidate output already exists: {output}")
    artifacts = assert_expected_inputs(source, dist, brand_zip)
    resources = expected_resources(source, artifacts)

    (output / "dist").mkdir(parents=True)
    (output / "github-release").mkdir()
    verification = output / "verification"
    verification.mkdir()
    for artifact in artifacts:
        shutil.copy2(artifact, output / "dist" / artifact.name)
    shutil.copy2(brand_zip, output / "github-release" / BRAND_ARCHIVE)
    for controller in CONTROLLERS:
        shutil.copy2(source / "packages/skilling/tests" / controller, verification / controller)
    shutil.copytree(source / "examples/welcome-skilling", verification / "welcome-skilling")
    (verification / "resources.json").write_text(
        json.dumps(resources, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    checksum_lines = [f"{sha256(output / relative)}  {relative}" for relative in CHECKSUM_PATHS]
    (output / "SHA256SUMS").write_text("\n".join(sorted(checksum_lines)) + "\n", encoding="utf-8")
    identity = resources["source"]
    candidate = {
        "format_version": 1,
        "artifact_name": CANDIDATE_ARTIFACT,
        "package_version": VERSION,
        "specification_version": SPEC_VERSION,
        "commit": identity["commit"],
        "tree": identity["tree"],
        "checksums": list(CHECKSUM_PATHS),
    }
    (output / "candidate.json").write_text(
        json.dumps(candidate, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    verify(output, source=None, require_tag=None)


def parse_checksums(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if lines != sorted(lines):
        fail("SHA256SUMS is not sorted")
    parsed: dict[str, str] = {}
    for line in lines:
        digest, separator, relative = line.partition("  ")
        if separator != "  " or len(digest) != 64 or digest != digest.lower():
            fail(f"invalid SHA256SUMS row: {line!r}")
        manifest_relative_path(relative, "checksum")
        if relative in parsed:
            fail(f"duplicate SHA256SUMS path: {relative}")
        parsed[relative] = digest
    if tuple(sorted(parsed)) != tuple(sorted(CHECKSUM_PATHS)):
        fail(f"checksum paths are incomplete: {sorted(parsed)}")
    return parsed


def check_tag(source: Path, candidate_sha: str, version: str) -> None:
    if version != VERSION:
        fail(f"release version is {version!r}, expected {VERSION!r}")
    tag = f"v{version}"
    tag_sha = git(source, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}")
    if tag_sha != candidate_sha:
        fail(f"{tag} points to {tag_sha}, expected candidate {candidate_sha}")


def verify(candidate_root: Path, source: Path | None, require_tag: str | None) -> None:
    reject_candidate_symlinks(candidate_root)
    expected_top = {"SHA256SUMS", "candidate.json", "dist", "github-release", "verification"}
    actual_top = {path.name for path in candidate_root.iterdir()}
    if actual_top != expected_top:
        fail(f"candidate layout mismatch: {sorted(actual_top)}")
    checksums = parse_checksums(candidate_root / "SHA256SUMS")
    expected_dist = {
        Path(relative).name for relative in CHECKSUM_PATHS if relative.startswith("dist/")
    }
    actual_dist = {path.name for path in (candidate_root / "dist").iterdir() if path.is_file()}
    if actual_dist != expected_dist:
        fail(f"candidate dist layout mismatch: {sorted(actual_dist)}")
    actual_github = {
        path.name for path in (candidate_root / "github-release").iterdir() if path.is_file()
    }
    if actual_github != {BRAND_ARCHIVE}:
        fail(f"candidate GitHub release layout mismatch: {sorted(actual_github)}")
    for relative, expected in checksums.items():
        path = candidate_root / relative
        if not path.is_file() or sha256(path) != expected:
            fail(f"checksum mismatch: {relative}")

    candidate = json.loads((candidate_root / "candidate.json").read_text(encoding="utf-8"))
    resources = json.loads(
        (candidate_root / "verification/resources.json").read_text(encoding="utf-8")
    )
    package_files = resources["package"]["files"]
    if not isinstance(package_files, dict):
        fail("package resource manifest is not an object")
    for relative in package_files:
        safe = manifest_relative_path(relative, "package resource")
        if not safe.startswith("skilling/"):
            fail(f"package resource is outside skilling/: {safe}")
    fixture = resources.get("fixture")
    controllers = resources.get("controllers")
    if not isinstance(fixture, dict) or not isinstance(controllers, dict):
        fail("retained verification manifests are missing")
    fixture_paths = {manifest_relative_path(relative, "fixture") for relative in fixture}
    if set(controllers) != set(CONTROLLERS):
        fail("retained controller manifest mismatch")
    if candidate["artifact_name"] != CANDIDATE_ARTIFACT:
        fail("candidate artifact name mismatch")
    if (
        candidate["package_version"] != VERSION
        or candidate["specification_version"] != SPEC_VERSION
    ):
        fail("candidate version identity mismatch")
    if candidate["checksums"] != list(CHECKSUM_PATHS):
        fail("candidate checksum manifest mismatch")
    if candidate["commit"] != resources["source"]["commit"]:
        fail("candidate/resources commit mismatch")
    if candidate["tree"] != resources["source"]["tree"]:
        fail("candidate/resources tree mismatch")
    artifact_rows = {row["file"]: row for row in resources["artifacts"]}
    if set(artifact_rows) != expected_dist or len(resources["artifacts"]) != len(expected_dist):
        fail("resource artifact manifest mismatch")
    for relative in CHECKSUM_PATHS[:2]:
        path = candidate_root / relative
        row = artifact_rows.get(path.name)
        if row is None or row["sha256"] != sha256(path) or row["size"] != path.stat().st_size:
            fail(f"resource manifest mismatch: {relative}")
    verification = candidate_root / "verification"
    expected_verification = {*CONTROLLERS, "resources.json", "welcome-skilling"}
    if {path.name for path in verification.iterdir()} != expected_verification:
        fail("candidate verification layout mismatch")
    for controller in CONTROLLERS:
        controller_path = verification / controller
        if not controller_path.is_file():
            fail(f"missing retained controller: {controller}")
        if sha256(controller_path) != controllers[controller]:
            fail(f"retained controller hash mismatch: {controller}")
    fixture_root = verification / "welcome-skilling"
    for relative, digest in fixture.items():
        path = fixture_root / manifest_relative_path(relative, "fixture")
        if not path.is_file() or sha256(path) != digest:
            fail(f"retained fixture hash mismatch: {relative}")

    expected_files = {
        "SHA256SUMS",
        "candidate.json",
        *CHECKSUM_PATHS,
        "verification/resources.json",
        *(f"verification/{name}" for name in CONTROLLERS),
        *(f"verification/welcome-skilling/{name}" for name in fixture_paths),
    }
    expected_directories = {
        "dist",
        "github-release",
        "verification",
        "verification/welcome-skilling",
    }
    for relative in fixture_paths:
        parent = PurePosixPath("verification/welcome-skilling") / PurePosixPath(relative).parent
        while parent.as_posix() != ".":
            expected_directories.add(parent.as_posix())
            parent = parent.parent
    actual_files: set[str] = set()
    actual_directories: set[str] = set()
    for path in candidate_root.rglob("*"):
        relative = path.relative_to(candidate_root).as_posix()
        (actual_directories if path.is_dir() else actual_files).add(relative)
    if actual_files != expected_files or actual_directories != expected_directories:
        fail("candidate recursive layout mismatch")
    if source is not None:
        commit = git(source, "rev-parse", "HEAD")
        tree = git(source, "rev-parse", "HEAD^{tree}")
        if (commit, tree) != (candidate["commit"], candidate["tree"]):
            fail("checked-out source does not match retained candidate")
        if require_tag is not None:
            check_tag(source, commit, require_tag)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    assemble_parser = subparsers.add_parser("assemble")
    assemble_parser.add_argument("--source", type=Path, required=True)
    assemble_parser.add_argument("--dist", type=Path, required=True)
    assemble_parser.add_argument("--brand-zip", type=Path, required=True)
    assemble_parser.add_argument("--output", type=Path, required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--candidate", type=Path, required=True)
    verify_parser.add_argument("--source", type=Path)
    verify_parser.add_argument("--require-tag")
    tag_parser = subparsers.add_parser("check-tag")
    tag_parser.add_argument("--source", type=Path, required=True)
    tag_parser.add_argument("--candidate-sha", required=True)
    tag_parser.add_argument("--version", required=True)
    args = parser.parse_args()

    if args.command == "assemble":
        assemble(
            args.source.resolve(),
            args.dist.resolve(),
            args.brand_zip.resolve(),
            args.output.resolve(),
        )
    elif args.command == "verify":
        if args.require_tag and args.source is None:
            parser.error("--require-tag requires --source")
        verify(
            args.candidate.absolute(),
            args.source.resolve() if args.source is not None else None,
            args.require_tag,
        )
    else:
        check_tag(args.source.resolve(), args.candidate_sha, args.version)


if __name__ == "__main__":
    main()
