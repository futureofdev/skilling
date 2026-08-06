# Troubleshooting — learn

Every verb prints exactly one JSON object and exits non-zero on failure. Check `ok` first.
On `false` the body is always `{"ok": false, "error": {"code": "...", "message": "..."}}` —
read the message and relay it to the learner in your own words. Never retry the identical
call expecting a different result, and never work around a refusal by reading or writing
files under the state root yourself; `skilling` is the only write authority, and a refusal
means something the format cares about, not a glitch to route around.

## What each exit code means for you

| Exit | Name | What it means | What to do |
|---|---|---|---|
| 0 | — | Succeeded | Proceed as normal |
| 1 | `ERROR` | Something went wrong inside `skilling` itself, not a rule the learner tripped | Tell the learner plainly that the tool hit an error, show them the message, stop |
| 2 | `INVALID` | An argument was malformed — a bad `--input`, an unknown option label, an unrecognised evidence or capability value | This is almost always your own call being wrong, not the learner's fault — fix the argument, don't ask the learner to retry |
| 3 | `CONFLICT` | Someone else's write landed between your last read and this write (optimistic concurrency) | Call `next` again to see where things actually stand now, then retry the learner's *intent* — not necessarily the identical call, since state moved under you |
| 4 | `ILLEGAL` | The action is not legal from here, regardless of arguments — wrong beat, wrong stage, a rule the format itself enforces | Never retry as-is. Call `next` to see the real state, and explain to the learner what actually needs to happen first |
| 5 | `VERSION_MISMATCH` | The learner's record was started against one version of this course; the manifest on disk is now a different version | Stop and say so plainly. This reference implementation has no automatic migration path across a version change — it needs a deliberate decision, not a guess |

## Refusals you will actually see in this loop

- `illegal-transition` — the `--input` you gave `advance` is not legal at the current beat
  (including trying to `advance` past `complete`/`ceremony`, which are finished by their own
  verbs). Re-read `legal_inputs` from the last envelope; do not guess a different input and
  do not assume the beat moved.
- `course-complete` — every lesson is already done; there is nothing left to `advance`.
- `unknown-input` — the input string itself is not one the machine recognises at all, not
  merely illegal here. A bug in your own call, not the learner's.
- `quiz-finished` — `quiz next` was called with no open question. The quiz already moved on
  (probably to `complete`); call `next` to see where.
- `unknown-option` — the label given to `answer` was not one of the current question's
  options. Ask the learner again rather than guessing which one they meant.
- `not-a-phase-boundary` — `ceremony` was called but the most recently completed lesson was
  not the last one in its phase. Only call `ceremony` when `complete`'s envelope reported
  `phase_completed: true`.
- `capability-missing`, `no-verify`, `missing-provenance`, `objective-unknown` — see
  `objectives.md`; none are worth retrying with the same arguments.
- `course-invalid` / `position-invalid` — the `--course` path does not resolve to a valid
  course, or the learner's record points at a lesson that no longer exists in it (a course
  edited out from under an in-progress learner). Neither is something to paper over; tell the
  learner plainly and stop rather than guessing a substitute position.

## A verb exits non-zero with no JSON at all

That is a bug in the tooling itself, not a rule anyone tripped. Tell the learner plainly that
`skilling` failed unexpectedly, show them what it printed, and stop — do not narrate as if
the call had actually succeeded.

## When in doubt

Call `skilling next --course <path>` again. It never writes anything, so there is no cost to
checking reality before calling anything that does.
