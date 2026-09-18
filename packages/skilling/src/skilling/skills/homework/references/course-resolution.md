# Course resolution — homework

`skilling homework check`/`submit` accept `--course <course>` as either a course id resolved
through the enclosing workspace or an explicit filesystem directory. Begin in the current
workspace, or in the exact `workspace` returned by an earlier `skilling start --json`.
Retain that response's `course.id` and `showcase` facts. Do not search the filesystem for a
plausible course.

## Start with the enclosing workspace

In ordinary workspace use, omit `--state`:

```
skilling courses
# {"ok": true, "verb": "courses", "courses": [
#   {"id": "example", "title": "Example", "last_activity": "2026-08-05",
#    "path": "/workspace/.skilling/courses/example@1.0.0"}, ...
# ]}
```

This selects the workspace's `.skilling/state`. If the session already selected an explicit
state root, use `skilling courses --state <state>` and keep that state choice, plus the same
`--learner` on course-specific verbs, throughout.

Match a named course by exact id first; use a unique title only when it identifies one row.
With no name, choose the most-recently-active row unless two or more tie on
`last_activity`; list tied candidates and ask. An empty list is normal, so ask for a path or
ref rather than initializing a guessed course.

Inside a workspace, use the selected id directly, even when the row has an optional `path`:

```
skilling homework check --course example
```

The runtime resolves that id and the implicit workspace state together. The optional path
confirms usable matching workspace content; it is not a path the host must repeat for every
ordinary call.

## Fall back only when workspace resolution cannot work

If a selected workspace id returns `course-not-found`, its content is missing, stale, or
otherwise unusable. Do not choose another row, guess from the id, edit the manifest, or
search for a same-named directory. Only then reuse a still-usable explicit path already
resolved this conversation or ask for the actual path/ref.

Outside a workspace, or for a supplied path/ref that is not a usable workspace course, run:

```
skilling fetch <ref> --json
# {"id": "...", "version": "...", "path": "...", "ref": "...", "pinned": null}
```

Use the returned `path` as the explicit `--course` value. If it is not a recognised ref or
local directory, ask for the real path/ref; a title is not a registry lookup.

Keep the selected course and record stream unchanged. In ordinary workspace use, continue
omitting `--state` and use the default learner. If an explicit `--state` or `--learner` was
selected, pass the same value on every check, submit, and artifact call.
