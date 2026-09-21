# Learn with Skilling

Skilling turns a course into a folder you can open in Claude Code or Codex. That folder keeps
the course snapshot, tutor instructions, durable progress and your own work together.

## Before you start

Install [Git](https://git-scm.com/downloads),
[uv](https://docs.astral.sh/uv/getting-started/installation/) and either Claude Code or Codex.
The coding host supplies the model and its normal account/network access; the Skilling CLI
does not contain a model or require an API key.

Install Skilling persistently so the generated tutor instructions can call the same command
later:

```bash
uv tool install skilling
skilling --version
```

## Create your first workspace

```bash
skilling start 'gh:futureofdev/skilling@v0.6.0#examples/welcome-skilling' my-learning --json
```

`start` prints a JSON object containing an absolute `workspace` path. Open that exact folder
in your coding host. It contains both host entry files and folder-scoped learning skills:

- Claude Code: invoke `/learn`.
- Codex: invoke `$learn`.

If the host was already open when `start` installed the skills, reopen the returned workspace
before invoking them. The tutor should explain one idea, wait for your response, and only move
on after each real lesson gate or quiz answer.

## Stop and resume

You can close the host at any time. Later, open the same workspace and invoke `/learn` or
`$learn` again. Progress is stored under `.skilling/state/`, not inferred from chat history.
Do not edit `.skilling/` by hand.

From any directory inside the workspace, these read-only commands find its root automatically:

```bash
skilling courses --json
skilling progress --course welcome-skilling
```

The tutor's `/progress` or `$progress` skill presents the same durable record conversationally.

## Homework and confirmation

At a homework boundary the tutor shows the assignment, reviews what you did, and asks for a
separate confirmation before submission. Reviewing work is not permission to submit it. Reply
with a clear confirmation only when you are ready; the tutor handles the underlying CLI
submission and safe retry details.

## Keep your work visible

Each course receives a directory under `showcase/`. Put learner-authored notes, code or other
requested outcomes there. The hidden `.skilling/` directory is machinery; `showcase/` is yours.
The tutor may register pointers to existing showcase work after you create it, but registering
an artifact does not create or verify the work.

## Add another course

Run `start` again with the new source and the existing workspace:

```bash
cd my-learning
skilling start 'gh:owner/repository@v1.0.0#path/to/course' . --json
```

The command adds the validated course without replacing existing courses, records or showcase
folders. See [Course sources](course-sources.md) for every supported reference form.

## Work from nested folders

Learner commands discover the enclosing workspace by walking upward from your current folder.
You can work inside `showcase/welcome-skilling/` and still resume, inspect progress or add a
course. If you deliberately need a different workspace, open or run commands from that folder.

## Move the workspace

Move or copy the **whole** `my-learning` directory, including hidden files. Open its new
location and continue from there. Moving only `showcase/` preserves your visible files but not
the course snapshot, installed skills or durable learner record.

After initial setup, the installed CLI, workspace course content and state can be used without
fetching the course again. This does not make a cloud coding host or model operate offline.

If something does not look right, use [Troubleshooting](troubleshooting.md).
