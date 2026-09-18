"""Installed import-recovery proof, called with staged inputs by each artifact endpoint."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch


def probe(
    fixture: Path,
    case: Path,
    tool_dir: Path,
    checkout_sentinel: Path,
    python_version: str,
    interrupt: bool,
) -> None:
    import skilling
    from skilling.cli.packaging._start import start
    from skilling.workspace import load_manifest

    assert not checkout_sentinel.exists(), checkout_sentinel
    imported = Path(skilling.__file__).resolve()
    assert imported.is_relative_to(Path(sys.prefix).resolve()), imported
    assert Path(sys.prefix).resolve().is_relative_to(tool_dir.resolve()), sys.prefix
    assert f"{sys.version_info.major}.{sys.version_info.minor}" == python_version
    workspace = case / "workspace"
    local = case / "local"
    if interrupt:
        original = Path.rename

        def stopped(path: Path, target: Path) -> Path:
            result = original(path, target)
            if target.name == "previous":
                os._exit(81)
            return result

        patch.object(Path, "rename", stopped).start()
        start(str(local), workspace, True)
        raise AssertionError("backup boundary not reached")

    case.mkdir()
    shutil.copytree(fixture, local)
    workspace.mkdir()
    (workspace / "AGENTS.md").write_bytes(b"# Foreign notes\r\nKeep these.\r\n")
    commands: list[list[str]] = []

    def run(arguments: list[str], cwd: Path) -> str:
        commands.append(arguments)
        result = subprocess.run(
            arguments,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=45,
        )
        assert result.returncode == 0, (arguments, result.stdout, result.stderr)
        return result.stdout

    run(["skilling", "start", str(local), str(workspace), "--json"], case)
    before = load_manifest(workspace).courses[0]
    state = workspace / ".skilling/state/welcome-skilling/record.yaml"
    state_bytes = state.read_bytes()
    (local / "new.txt").write_text("installed replacement", encoding="utf-8")
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--fixture",
        str(fixture),
        "--case",
        str(case),
        "--tool-dir",
        str(tool_dir),
        "--checkout-sentinel",
        str(checkout_sentinel),
        "--python-version",
        python_version,
        "--interrupt",
    ]
    commands.append(command)
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=45)
    assert result.returncode == 81, (result.stdout, result.stderr)
    assert not (workspace / ".skilling/courses/welcome-skilling@1.0.0").exists()
    relocated = case / "relocated"
    workspace.rename(relocated)
    content = relocated / ".skilling/courses/welcome-skilling@1.0.0"
    run(["skilling", "next", "--course", str(content)], relocated)
    run(["skilling", "progress", "--course", "welcome-skilling"], relocated)
    run(["skilling", "artifact", "list", "--course", "welcome-skilling"], relocated)
    assert (content / "new.txt").read_text(encoding="utf-8") == "installed replacement"
    assert load_manifest(relocated).courses[0].added_at == before.added_at
    assert (relocated / ".skilling/state/welcome-skilling/record.yaml").read_bytes() == state_bytes
    assert (relocated / "AGENTS.md").read_bytes().startswith(b"# Foreign notes\r\nKeep these.\r\n")
    assert not (relocated / ".skilling/import.yaml").exists()
    print(
        json.dumps(
            {
                "import": str(imported),
                "python": sys.version,
                "commands": commands,
                "backup_process_exit": True,
                "relocated_recovery": True,
                "state_preserved": True,
            }
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--case", required=True, type=Path)
    parser.add_argument("--tool-dir", required=True, type=Path)
    parser.add_argument("--checkout-sentinel", required=True, type=Path)
    parser.add_argument("--python-version", required=True)
    parser.add_argument("--interrupt", action="store_true")
    args = parser.parse_args()
    probe(
        args.fixture.resolve(),
        args.case.resolve(),
        args.tool_dir.resolve(),
        args.checkout_sentinel.resolve(),
        args.python_version,
        args.interrupt,
    )


if __name__ == "__main__":
    main()
