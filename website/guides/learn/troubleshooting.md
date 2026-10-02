---
title: Troubleshooting
description: Fixes for the most common setup and resume problems.
---

# Troubleshooting

Start with the exact command that failed and what it printed. Whatever happens, **don't delete
`.skilling/`**. Recovery may need the files in it.

## Git or uv isn't installed

Follow the official instructions: [install Git](https://git-scm.com/downloads) and
[install uv](https://docs.astral.sh/uv/getting-started/installation/). Then restart your
terminal or assistant and check both work:

```bash
git --version
uv --version
```

## `skilling` isn't found

Install it as a tool and check it runs:

```bash
uv tool install skilling
skilling --version
```

If uv says its tool folder isn't on your `PATH`, run the `uv tool update-shell` command it
suggests and restart your assistant. A command that works in one terminal isn't always visible
to an assistant that was already running.

## `/learn` or `$learn` doesn't exist

The skills are installed inside your learning folder, so open that exact folder, then restart
or reopen your assistant so it notices them. Claude Code uses `/learn` and Codex uses `$learn`.
The `CLAUDE.md` and `AGENTS.md` files in the workspace say the same.

If files are missing, run your original `skilling start` command again. It's safe to repeat and
puts the skills back.

## The course can't be fetched

Check the spelling, and try `git` against the same repository. Private repositories use your
existing Git or `gh` login. Remember that only the GitHub shorthand supports a tag, commit or
subfolder. See [finding courses](courses).

## A command can't find your workspace

Run it from the workspace or any folder inside it. If you moved it, make sure you moved the
whole folder, not just `showcase/`.

## `version-mismatch`

Your progress belongs to a different version of the course than the one in your workspace.
Nothing has been changed. Run `skilling upgrade --course <course-id>`, or type
`/upgrade-skilling`, to see whether your progress can carry over.

## Still stuck?

[Open an issue](https://github.com/futureofdev/skilling/issues) with your Skilling version,
operating system, the command and its output. Leave out any passwords, tokens or private
course content. The
[full troubleshooting reference](https://github.com/futureofdev/skilling/blob/main/docs/troubleshooting.md)
covers rarer cases.
