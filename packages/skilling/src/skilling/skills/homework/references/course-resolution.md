# Course resolution — homework

`skilling homework check`/`submit` need `--course <path>`, exactly like every other verb.
Resolving that path works the same way it does for `learn` — restated here in full, since
skills share no code, only prose, and this one should stand on its own. Begin in the current
workspace, or in the exact `workspace` returned by an earlier `skilling start --json`. Retain
its `showcase` fact when present. Do not search the filesystem for a plausible course.

## The learner names a course

Treat what they said as a ref and call `skilling fetch <ref> --json`. A ref is a local path,
`gh:owner/repo[@tag-or-sha][#subdir]`, or a `https://`/`git+ssh://` URL:

```
skilling fetch <ref> --json
# {"id": "...", "version": "...", "path": "...", "ref": "...", "pinned": null}
```

Use the printed `path` for the rest of the session.

If `fetch` refuses with "not a recognised ref, and no local directory" (exit 1), the name
given is neither a path nor a fetchable ref. Ask the learner for the actual path or ref they
used before, rather than guessing one.

## The learner does not name one

Call `skilling courses --state <path>` (always JSON):

```
# {"ok": true, "verb": "courses", "courses": [
#   {"id": "...", "title": "...", "last_activity": "2026-08-05",
#    "path": "/workspace/.skilling/courses/example@1.0.0"}, ...
# ]}
```

Default to the first entry (most recently active). List and ask when two or more tie on
`last_activity`, or when the learner asks what they are even taking. An empty list is a
normal empty state — nothing has been delivered to this learner yet — not a failure. Ask
for a path or ref; do not initialize a guessed course.

## Use `path` only when it is usable

Inside a workspace, a row may also carry `path` when the workspace entry, course manifest,
id, and version all agree. Use that emitted path for the selected course. The key is
optional, and a path retained from an older response can become stale.

For a row without `path`, or whose emitted path is no longer usable, reuse a still-usable
path already resolved this conversation or ask the learner for the actual path or ref. Run a
ref through `skilling fetch <ref> --json` and use its returned `path`. Do not substitute
another row, guess a location from the id, or search for a same-named directory. Keep the
same state root and learner id after resolving the path.
