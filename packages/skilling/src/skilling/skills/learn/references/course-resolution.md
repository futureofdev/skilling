# Course resolution — learn

Every verb below needs `--course <path>`: a filesystem directory `skilling` can load a
manifest and lessons from. Work out that path before calling `next` for the first time. Begin
in the learner's current directory. When an earlier `skilling start --json` response supplied
`workspace`, use that exact directory as the working directory for discovery and retain its
`showcase` fact. Otherwise use the current workspace, if there is one. Do not search the
filesystem for a plausible course directory.

## The learner names a course

Treat whatever they said as a ref and hand it to `skilling fetch <ref>` (add `--json` to get
a machine-readable result). A ref is a local path, `gh:owner/repo[@tag-or-sha][#subdir]`, or a
`https://`/`git+ssh://` URL. `fetch` resolves it, validates it, caches it if it was remote,
and prints where it landed:

```
skilling fetch <ref> --json
# {"id": "...", "version": "...", "path": "...", "ref": "...", "pinned": null}
```

Use the printed `path` for every verb for the rest of the session. Re-running `fetch` with
the exact same ref later in the same session is cheap — a cache hit, no network — so there is
no need to remember the path yourself once you have it, but doing so saves a call.

If `fetch` refuses with "not a recognised ref, and no local directory" (exit 1), the learner
named something that is neither a path nor a fetchable ref — a bare id or title you have not
already resolved this session. Ask them for the actual path or the ref they used before;
`skilling` has no registry mapping a name back to a location (see the gap below).

## The learner does not name one

Call `skilling courses`, which is always `--json` (the flag exists only for compatibility
with the documented invocation — there is no other rendering):

```
skilling courses --state <path>
# {"ok": true, "verb": "courses", "courses": [
#   {"id": "...", "title": "...", "last_activity": "2026-08-05",
#    "path": "/workspace/.skilling/courses/example@1.0.0"}, ...
# ]}
```

Courses are sorted most-recently-active first. Default to the first entry. When two or more
entries tie on `last_activity`, or when the learner explicitly asks what they are taking,
list the candidates by title and ask rather than picking for them.

An empty `courses` list is a normal empty state, not a failure: nothing has ever been
delivered to this learner in this state root. Tell them to name a course path or ref to
start. Do not initialize a guessed course merely to make the list non-empty.

## Use `path` only when it is usable

Inside a workspace, a row may also contain `path`. It appears only when the workspace entry,
course manifest, id, and version agree. Use that emitted path directly for the selected
course. The key is optional: fetched-cache and bare local courses can still appear without
it, and a path retained from an older response can later become stale.

For a selected row with no `path`, or when its emitted path is no longer usable:

- If you already resolved that id to a path earlier in this same conversation (through
  `fetch`) and it is still usable, reuse it.
- Otherwise, ask the learner for the actual course path or ref. Pass a ref through
  `skilling fetch <ref> --json` and use its returned `path`.

Never substitute another row, guess a location from the id, or search for a same-named
directory. A missing or stale path is a request for a path/ref, not permission to change
courses. Keep the same `--state` and `--learner` selection after resolving the course so the
chosen path resumes the intended record stream.
