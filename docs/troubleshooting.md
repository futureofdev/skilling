# Troubleshooting learning setup

Start with the exact failing command and its output. Do not delete `.skilling/`: recovery may
need the files it contains.

## Git or uv is missing

Use the official setup instructions for your operating system:

- [Install Git](https://git-scm.com/downloads)
- [Install uv](https://docs.astral.sh/uv/getting-started/installation/)

Restart the terminal or coding host after installation, then verify `git --version` and
`uv --version` in the same environment that will run Skilling.

## `skilling` is not found

Install the persistent tool and verify the bare command:

```bash
uv tool install 'skilling==0.6.0'
skilling --version
```

If uv reports that its tool directory is not on `PATH`, follow uv's printed `uv tool
update-shell` guidance, then restart the host. A tool visible in one terminal is not
necessarily visible to an already-running coding host.

## `/learn` or `$learn` is unavailable

`skilling start` installs skills inside the returned workspace. Open that exact directory,
then restart or reopen the host so it scans the new files. Claude Code uses `/learn`; Codex
uses `$learn`. The generated `CLAUDE.md` and `AGENTS.md` in the workspace repeat these commands.

If files are missing, run the original `skilling start REF WORKSPACE --json` command again.
The operation is idempotent and refreshes the installed skills and entry instructions.

## The course cannot be fetched

Check the spelling of the source and run `git` against the same repository. Public GitHub
shorthand uses `gh:owner/repository`; a private repository uses your existing Git or `gh`
credentials. Skilling does not ask for or store a separate repository token.

A tag, full commit or subdirectory is supported only by GitHub shorthand. Generic Git URLs
name a repository root and do not accept Skilling-specific pin/subdirectory syntax. See
[Course sources](course-sources.md).

## Cached or workspace content is unavailable

Skilling refuses altered, missing or conflicting cached content instead of silently selecting
different bytes. Restore the workspace's course content, re-run `start` with the original ref,
or use a new workspace for a different revision. Preserve any import or staging files named by
an error so the next command can recover safely.

An already-installed workspace course can be selected by course id while offline. A remote ref
that was never fetched cannot be resolved offline.

## A command cannot find the workspace

Run it from the workspace or any nested directory. A workspace is identified by
`.skilling/workspace.yaml`; a loose `.skilling/` state directory from an older workflow is not
one. Move the entire workspace rather than only its visible showcase folder.

## Recovery refuses to continue

Read the error before changing files. Skilling refuses ambiguous or unsafe recovery rather
than guessing. Keep the workspace intact and retry the same command. For an older standalone
state directory, use the explicit `--state` option documented in the
[runtime reference](../README.md#reference-implementation-and-specification).

For a reproducible product defect, open an issue with the Skilling version, operating system,
command and redacted output. Never include repository credentials or private course content.
