---
title: Your workspace
description: What's in your learning folder, how to add courses, update, and move it.
---

# Your workspace

When you start a course, Skilling creates a learning folder (a *workspace*). Everything lives
there:

```text
my-learning/
├── CLAUDE.md          # instructions for Claude Code
├── AGENTS.md          # instructions for Codex
├── .claude/skills/    # /learn, /progress, /homework, /upgrade-skilling
├── .agents/skills/    # the same skills for Codex ($learn, ...)
├── showcase/          # your work, one folder per course
└── .skilling/         # the course copy and your progress
```

`showcase/` is yours. `.skilling/` is Skilling's machinery: please don't edit it by hand, and
don't delete it, because it holds your progress.

You can work from any folder inside the workspace, such as `showcase/welcome-skilling/`, and
Skilling still finds it.

## Adding another course

Run `start` again from inside your workspace, with the new course and `.` as the folder:

```bash
cd my-learning
skilling start 'gh:owner/repository@v1.0.0#path/to/course' . --json
```

This adds the course alongside your existing ones. It never replaces your other courses,
progress or showcase folders. See [finding courses](courses) for the kinds of source you can
use.

## Updating Skilling or a course

Type `/upgrade-skilling` in Claude Code or `$upgrade-skilling` in Codex. The tutor asks before
every check and every change. It can update Skilling and its skills, and check whether a
course you're taking has a newer version.

You can do the course check yourself too:

```bash
skilling upgrade --course welcome-skilling          # report only, changes nothing
skilling upgrade --course welcome-skilling --yes    # switch, keeping your progress
```

Small fixes and new lessons keep your place. A bigger restructure (a new major version) can't
carry your progress across automatically, so Skilling leaves you on your current version
rather than guess.

## Moving to another folder or machine

Move or copy the **whole** workspace, hidden files included. On another machine, install
Skilling first (`uv tool install skilling`), then open the moved folder. Copying only
`showcase/` keeps your files but not your progress.

Once a course is set up, the CLI, the course and your progress all work without fetching
anything again. That doesn't make a cloud-hosted model work offline, though. Your assistant
still needs its normal connection.
