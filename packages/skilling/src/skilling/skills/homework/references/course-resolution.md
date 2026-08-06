# Course resolution — homework

`skilling homework check`/`submit` need `--course <path>`, exactly like every other verb.
Resolving that path works the same way it does for `learn` — restated here in full, since
skills share no code, only prose, and this one should stand on its own.

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
#   {"id": "...", "title": "...", "last_activity": "2026-08-05"}, ...
# ]}
```

Default to the first entry (most recently active). List and ask when two or more tie on
`last_activity`, or when the learner asks what they are even taking. An empty list is a
normal empty state — nothing has been delivered to this learner yet — not a failure.

## The gap this leaves you with

`courses` reports `id`, `title`, and `last_activity` only — never a path, never a version.
It tells you *which* course to resume, never *where* its content lives; `skilling` tracks
progress across many courses from one state root, but keeps no registry from a course id
back to a filesystem location.

So once you know which id to use, you still need a path: reuse one you already resolved
earlier this same conversation, or ask the learner for the path or ref again. Do not guess a
location by searching the filesystem for a directory that happens to match the id — a course
loaded from a bare local path was never cached under its id at all.
