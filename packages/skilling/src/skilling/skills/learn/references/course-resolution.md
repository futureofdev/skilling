# Course resolution — learn

Every verb below needs `--course <path>`: a filesystem directory `skilling` can load a
manifest and lessons from. Working out that path, for whichever course the learner means,
happens before you call `next` for the first time.

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
#   {"id": "...", "title": "...", "last_activity": "2026-08-05"}, ...
# ]}
```

Courses are sorted most-recently-active first. Default to the first entry. When two or more
entries tie on `last_activity`, or when the learner explicitly asks what they are taking,
list the candidates by title and ask rather than picking for them.

An empty `courses` list is a normal empty state, not a failure: nothing has ever been
delivered to this learner. Tell them to name a course or a ref to start.

## The gap this leaves you with

`skilling courses` reports `id`, `title`, and `last_activity` only — deliberately not a
path, and not a version. It answers "which course, of the ones I've touched before, is most
recent," never "where does that course's content live." `skilling` tracks a learner's
*progress* across many courses from one state root; it does not maintain a registry from a
course id back to wherever its files are.

So once `courses` tells you *which* id to resume, you still need a path for it:

- If you already resolved that id to a path earlier in this same conversation (through
  `fetch`), reuse it — no need to ask again.
- Otherwise, ask the learner where that course lives, or which ref they fetched it from.
  Do not guess a location, and do not search the filesystem for a directory that happens to
  share the id's name — a course loaded from a bare local path is never cached under its id
  at all, so there is nothing reliable to search for.

This is a real limitation of `skilling courses` as it stands, not an oversight in this
skill: naming a course is currently the only durable way back to it across a fresh
conversation with no memory of the earlier `fetch`.
