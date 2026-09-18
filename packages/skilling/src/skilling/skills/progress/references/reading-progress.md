# Reading progress

Two verbs, two shapes. Both are read-only — call either as often as you like.

## `skilling courses [--state <state>]`

Every course this learner has local progress for, from one state root, most-recently-active
first. The `--json` flag is present only for compatibility with the documented invocation;
there is no other rendering to opt into or out of.

```json
{"ok": true, "verb": "courses", "courses": [
  {"id": "hello-skilling", "title": "Hello, Skilling", "last_activity": "2026-08-05",
   "path": "/workspace/.skilling/courses/hello-skilling@1.0.0"},
  {"id": "coding-bootcamp", "title": "coding-bootcamp", "last_activity": "2026-08-03"}
]}
```

- `id` — the course id.
- `title` — the manifest's title, when `skilling` can resolve it (the course was fetched and
  is still in the fetch cache under this learner's id+version). Otherwise it falls back to
  the id itself — `"coding-bootcamp"` above is standing in for a title `skilling` could not
  resolve, not a course whose real title happens to be its id. Do not treat a bare-looking
  title as license to invent a nicer one; show what you were given.
- `last_activity` — a calendar date (not a timestamp), the day the streak algorithm itself
  keys off. Two courses can tie on the same day; that is a genuine tie, not a rounding
  artifact, and it is exactly the case where you should list and ask rather than default.
- `path` — optional. It appears when the current workspace has a usable course entry whose
  manifest id and version match this record. Use the row's `id` directly for ordinary
  workspace calls; the path is evidence that the id can resolve, not a value the host must
  repeat. If the id later returns `course-not-found`, only then fall back to a still-usable
  explicit path or ask for the actual path/ref instead of searching or substituting a course.
- There is no `version` field in this summary. Read the version from a course-specific
  envelope after resolving its id or explicit path.

An empty `courses` array is a normal empty state — nothing has ever been delivered to this
learner — not a failure to report as one.

## `skilling progress --course <course> [--state <state>]`

Today's full detail for one course. Inside a workspace, `<course>` is the selected course id
and `--state` is normally omitted. Outside a workspace or after an unusable workspace entry,
`<course>` can be an explicit course directory.

```json
{"ok": true, "verb": "progress",
 "course": {"id": "hello-skilling", "version": "1.0.0"},
 "position": {"phase": 0, "lesson": 2, "beat": "concept", "question_index": null},
 "completed": ["0.1"],
 "completed_count": 1, "lesson_count": 3, "percent_complete": 33,
 "skills_unlocked": ["course-basics"],
 "streak_days": 1,
 "started_at": "2026-08-05", "last_activity": "2026-08-05",
 "revision": "..."}
```

Notes worth not missing:

- `course` here is `{id, version}` only — **no `title`**, unlike `skilling next`'s envelope.
  If you need a title to display and this course also appears in `skilling courses`' output,
  take it from there; otherwise fall back to the id, exactly as `courses` itself does.
- `percent_complete` and `completed_count`/`lesson_count` are computed from the manifest and
  `completed` at the moment you call this — never cache one across turns.
- There is no phase-level breakdown anywhere in this envelope. `position.phase` names which
  phase the learner is currently in, not how many phases exist or how far through the current
  one they are — do not compute a phase percentage from fields that are not here.
- `position` is reported even when the course is fully complete (`completed_count ==
  lesson_count`); it still names the last lesson's coordinate, not a sentinel value.
- Reports regardless of where the learner stands, so it is safe to call even for a learner
  who has not started (`completed_count: 0`) or has finished the whole course.
