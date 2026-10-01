# Reading `skilling upgrade`

`skilling upgrade --course <id> --check --json` prints one object. It looks and reports only:
it may fetch the course source, but it never switches the workspace or changes progress.

```
{"ok": true, "verb": "upgrade", "mode": "check", "status": "available",
 "course": {"id": "example", "installed": "1.0.0", "record": "1.0.0"},
 "available": "1.1.0",
 "source": {"kind": "tag", "ref": "gh:acme/example", "tag": "v1.1.0", "newer_major": "v2.0.0"},
 "bump": {"declared": "minor", "required": "minor", "satisfied": true, "reasons": ["..."]},
 "progress": {"status": "carries-over", "from": "1.0.0", "to": "1.1.0", "level": "minor",
              "reason": null, "dropped_objectives": [], "lesson_restarted": false,
              "message": "Progress carries over (...)"}}
```

## `status`

| Value | Say |
|---|---|
| `available` | A newer version (`available`) can be installed. |
| `pending` | The newer version is already in the workspace, but their progress hasn't moved to it yet. Upgrading finishes the job. |
| `up-to-date` | They already have the newest version this course offers. |
| `pinned` | The course is pinned to an exact commit on purpose, so there are no automatic upgrades. |
| `no-same-major` | Only a new major release exists (see `source.newer_major`). |
| `applied` | The `--yes` run finished. |

## `bump.declared`: what kind of change

| Value | Plain words |
|---|---|
| `patch` | A small fix: wording, examples, typos. Same lessons. |
| `minor` | New lessons were added. Everything they've done stays where it was. |
| `major` | A restructure: lessons may have moved or gone. |

`bump.reasons` lists what actually changed. Summarise it; don't paste it.

## `progress`

| `status` | Meaning |
|---|---|
| `carries-over` | Their place, completed lessons, objectives and homework will all come along. |
| `rolled-forward` | Done: progress moved to the new version. |
| `not-resumable` | Progress can't carry over automatically. `reason` says why: `major`, `downgrade`, `missing-coordinates` (a lesson they've touched is gone), or `unordered`. Their progress stays exactly as it is. |
| `none` | There's no progress yet, so there's nothing to carry over. |

`dropped_objectives` lists objectives the new version no longer has, which stop being
recorded as met. `lesson_restarted: true` means the lesson they're on changed shape, so it
starts again from its beginning; their place in the course doesn't move.

## Refusals

On failure the object is `{"ok": false, "error": {"code": ..., "message": ...}}`:

- `version-mismatch` (exit 5): progress can't carry over to that version. Nothing changed.
  Offer to stay on the current version.
- `cache-conflict` (exit 3): the source offers different content under a version number the
  workspace already has. The course author needs to bump the version. Nothing changed.
- `source-unavailable`: the course source couldn't be reached (network, Git sign-in, or a
  local folder that moved). Relay the message. Don't work around it.
- `course-not-found`: see `course-resolution.md`.
