# Course resolution — learn

Every teaching verb needs `--course <course>`: either a course id resolved through the
enclosing workspace or an explicit filesystem directory. Begin in the learner's current
directory. When an earlier `skilling start --json` response supplied `workspace`, use that
exact directory as the working directory and retain its `course.id` and `showcase` facts.
Do not search the filesystem for a plausible course directory.

## Start with the enclosing workspace

In ordinary workspace use, call `courses` without `--state`:

```
skilling courses
# {"ok": true, "verb": "courses", "courses": [
#   {"id": "example", "title": "Example", "last_activity": "2026-08-05",
#    "path": "/workspace/.skilling/courses/example@1.0.0"}, ...
# ]}
```

Omitting `--state` deliberately selects the enclosing workspace's `.skilling/state`. If the
session already selected an explicit state root, call `skilling courses --state <state>` and
keep that state choice, plus the same `--learner` on course-specific verbs, throughout.

Courses are sorted most-recently-active first. If the learner named a course, match an exact
id first; a unique title can identify a candidate, but ambiguous titles require a question.
With no named course, default to the first entry unless two or more entries tie on
`last_activity`; list tied candidates by title and ask rather than choosing silently. An
empty list is normal: ask for a course path or ref instead of initializing a guessed course.

Inside a workspace, use the selected row's `id` directly:

```
skilling next --course example
```

Do this even when the row also contains `path`. The optional path confirms that the current
workspace entry, manifest id, and version agree, but ordinary workspace calls do not need to
repeat an internal content path. The runtime resolves the id and the implicit workspace state
together, which keeps course content and learner progress in the same workspace.

## Fall back only when workspace resolution cannot work

If the selected workspace id returns `course-not-found`, its content is missing, stale, or
otherwise unusable. Do not substitute another row, guess from the id, edit the workspace
manifest, or search for a same-named directory. Only then use a still-usable explicit path
already returned or resolved in this conversation, or ask the learner for the actual path or
ref.

Outside a workspace, or when the learner provides a path/ref that is not a usable workspace
course, pass it through `skilling fetch <ref> --json`:

```
skilling fetch <ref> --json
# {"id": "...", "version": "...", "path": "...", "ref": "...", "pinned": null}
```

A ref is a local path, `gh:owner/repo[@tag-or-sha][#subdir]`, or an
`https://`/`git+ssh://` URL. Use the returned `path` as the explicit `--course` value. If
`fetch` says the value is not a recognised ref or local directory, ask for the real path or
ref. A bare title is not a registry lookup.

Once selected, keep one course selector and one record stream for the session. In ordinary
workspace use, continue omitting `--state` and use the default learner. If an explicit
`--state` or `--learner` was selected, pass the same value to every course-specific call.
