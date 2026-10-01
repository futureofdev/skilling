# Course resolution: upgrade

`skilling upgrade --course <course>` takes a course id resolved through the enclosing
workspace, or an explicit course directory. Begin in the current workspace, or in the exact
`workspace` returned by an earlier `skilling start --json`. Do not search the filesystem for a
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

Match a named course by exact id first, and use a unique title only when it identifies a
single row. With no name and one row, use it. With several rows, ask which course to check,
listing the rows as choices, one question at a time. An empty list means no course has been
started here yet, so there is nothing to upgrade.

Use the selected course id directly, even when the row has an optional `path`:

```
skilling upgrade --course example --check --json
```

If the learn skill handed you an envelope with an `upgrade.command`, it already names the
course. Use that id.

## When the id doesn't resolve

If the id returns `course-not-found`, the workspace content is missing or unusable. Don't
choose another row, edit the manifest, or look for a same-named directory. Ask the learner
where the course lives.

Keep the same record stream throughout. In ordinary workspace use, continue omitting
`--state` and use the default learner. If an explicit `--state` or `--learner` was selected,
pass the same value on every call.
