# Troubleshooting — learn

Every verb prints exactly one JSON object and exits non-zero on failure. Check `ok` first.
On `false` the body is always `{"ok": false, "error": {"code": "...", "message": "..."}}` —
read the message and relay it to the learner in your own words. An uncertain keyed advance
may be retried with its original key and input; a typed refusal needs the action below.
Never work around a refusal by reading or writing
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
- `idempotency-key-conflict` — the key belongs to another input, or legacy state cannot prove
  its original input. Read `next`; do not bypass the refusal with another key for the same
  uncertain action. A distinct, newly authorized action gets its own fresh key.
- `recovery-required` — preserve the state and recovery metadata for inspection. Do not edit
  or delete a journal or guess a missing transition.
- `store-busy` — another process still holds the learner store lock. Do not edit lock or
  state files and do not turn the same action into a second, differently keyed action. Wait
  for the other operation to finish, then inspect with `next`; retry an already authorized
  keyed action only with its original key and input.
- `unknown-input` — the input string itself is not one the machine recognises at all, not
  merely illegal here. A bug in your own call, not the learner's.
- `quiz-finished` — `quiz next` was called with no open question. The quiz already moved on
  (probably to `complete`); call `next` to see where.
- `unknown-option` — the label given to `answer` was not one of the current question's
  options. Ask the learner again rather than guessing which one they meant.
- `not-a-phase-boundary` — `ceremony` was called but the most recently completed lesson was
  not the last one in its phase. Only call `ceremony` when `complete`'s envelope reported
  `phase_completed: true`.
- `no-workspace` — `artifact add` was called outside a workspace. Artifact registration is
  optional: skip it and continue. Do not manufacture a workspace or edit state merely to
  make this optional pointer succeed.
- `course-not-found` — the requested workspace course id/path cannot be resolved. Run
  `courses` from the intended workspace again, use its usable emitted `path`, or ask the
  learner for the actual path/ref. Do not repair the workspace manifest by hand or silently
  choose another course.
- `artifact-missing` — the offered artifact path does not exist. Ask for the existing work's
  actual path or skip registration; never create placeholder work to satisfy the command.
- `artifact-outside-workspace` — the path is not inside this workspace. Explain the boundary
  and ask whether the learner has existing work under the returned `showcase`; do not copy or
  move content merely to bypass the refusal.
- `coordinate-required` — there is no validated completed coordinate to associate with the
  ceremony or artifact. Use only the `coordinate` returned by ceremony or
  `archived.coordinate` returned by the confirmed submission; never substitute the current
  lesson position or edit completion history.
- `artifact-invalid` — the title or workspace-relative path is not a valid artifact value.
  Correct the proposed metadata or skip registration; do not alter learner state directly.
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

Call `skilling next --course <path>` again. It does not advance the lesson; first use may
initialize state and a pending prepared operation may finish recovery. Consistent existing
state is read without changing progress.
