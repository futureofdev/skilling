# Embed a file-backed Python session

`skilling.session` is an experimental Python API for a trusted producer controller. It is
LLM-free and uses the same file runtime as the teaching, completion and companion CLI
commands. The runtime specification remains authoritative; these Python signatures are not a
new conformance class. Use a build containing this API; the previously allocated core 0.7.0
release does not by itself establish that the API is present in published artifacts.

Give the controller explicit absolute paths and a validated course. The facade does not
choose a workspace, consult state-root environment variables or change the current directory.
`load_course` validates an explicit directory and recovers any enclosing workspace import
before consuming content. Its optional `workspace_root` enforces course containment.

```python
from pathlib import Path

from skilling.session import FileSession, SessionRefusal, VersionMismatch, load_course

workspace = Path("/absolute/path/to/learner-workspace")
course = load_course(
    workspace / ".skilling/courses/welcome-skilling@1.0.0",
    workspace_root=workspace,
)
session = FileSession.open(
    course,
    state_root=workspace / ".skilling/state",
    learner_id="local",
    workspace_root=workspace,
)
view = session.snapshot()
```

The default initializes a missing record. With `initialize=False`, a missing record produces
a welcome snapshot with `revision=None` and actions refuse until a record exists. Existing
prepared file operations may recover during reads, as with the CLI. The state root serves one
learner; selecting another learner's stored stream refuses. Non-file backends, relative paths,
unsafe state descendants and corrupt residuals refuse. A loaded `Course` is trusted input:
validate through `load_course` and keep authored content fixed while a controller uses it.

Each operation reloads the coherent record/revision/scratch snapshot. `SessionSnapshot`,
`BeatView`, `QuestionView`, `QuizFeedback` and `ActionResult` contain copied frozen values;
options, objectives and tutor tones are immutable tuples. `BeatView.content()` returns a fresh
JSON-safe copy of the active content. Snapshots contain course identity/title, position and
coordinate, revision, active beat, legal inputs, counts and authored tutor persona/tone. They
contain no course object, file path, store, parser, receipt key or future quiz content.
`question()` returns only the current quiz question's number, text and options.

Keep `session`, `course`, state paths and action event ids on the trusted controller side.
Send only the safe teaching values needed for a particular model request. Authored/model prose
is content, never authorization to call a method. The controller must bind gate choices and
answer labels to actual learner controls. A delivered non-gate beat can advance only after the
controller successfully presents it; merely reading a snapshot is not learner consent.

```python
# After presenting the current non-gate beat, or receiving its explicit learner control:
result = session.advance("next", event_id="controller-owned-event-1")
view = result.snapshot

# At the quiz beat, display these choices before accepting the learner's selection:
question = session.question()
feedback = session.answer("b")  # illustrative learner choice; never choose for a learner
# Present feedback.correct and feedback.reason before continuing the lesson.
```

`advance(input, event_id=None)` accepts the existing delivery `Input` enum or its string value.
A repeated event id with the same input returns the **current** snapshot with `replayed=True`,
even after intervening actions or completion. It does not retain an original outcome. Reusing
an id for another input refuses. New learner actions need fresh event ids. Unkeyed `advance`
and `answer(label)` are recoverable writes but are not safe retries: a repeated answer may
answer a later question. `answer` returns correctness, the authored reason and remediation
objectives/revisit offer; it never settles objectives. This extraction does not add durable
pending feedback, acknowledgement or keyed-answer recovery. Preserve the returned feedback
and present it before fetching another question; do not blindly retry after presentation or
model failure.

`SessionRefusal` has a typed `kind` (`RefusalKind.INVALID`, `CONFLICT` or `ILLEGAL`), a `code`
and an explanatory exception message. `VersionMismatch` additionally carries `course_id`,
`from_version`, `to_version`, `resumable`, typed upgrade `reason` and `refusal_message`.
It never upgrades progress implicitly. The CLI continues to produce exit 5/`error.upgrade`
and its offline cached `next.upgrade` hint; workspace discovery and command text belong to
the CLI. Use the explicit upgrade workflow to change a record's version.

File integrity/recovery exceptions such as `RecoveryRequired`, `StatePathError` and `StoreBusy`
remain typed core exceptions. A refused action does not imply rollback of an earlier committed
operation. The producer owns identity/session binding, learner controls, presentation,
optional history, model/credentials and usage limits. This API supplies no model tools,
provider dependency or general filesystem authority.

Completion and companions use that same controller-owned session. At the completion beat,
`complete(expected_revision)` commits the current lesson against the revision the controller
observed. Repeating a committed completion preserves its badges, queue and log.
`ceremony(coordinate=None)` selects the existing completion chronology and returns share text
and a workspace-relative showcase. Neither operation infers that a learner presented work.

`homework_check()` retrieves the active assignment, queued assignments and a submission token;
it does not evaluate requirements or initialize a missing record. Keep its token on the
controller side. Only after the learner explicitly submits, call `homework_submit(token)`.
A successful replay returns the original archive without consuming a successor assignment.
Malformed or differently bound tokens refuse before state access.

`objectives(capabilities=())` reports authored objectives and whether each can be settled with
those producer capabilities. `settle_objective(id, capabilities, checked=..., attested_by=...,
expected_revision=...)` requires the actual observation and provenance for practice evidence.
Knowledge settlement requires the existing conversational capability; quiz correctness never
settles an objective. `ObjectiveSettlementError` in `skilling.delivery` retains `ValueError`
compatibility and exposes a typed `ObjectiveRefusal` reason. The facade maps those refusals to
`SessionRefusal` codes. `progress()` returns copied progress values. `telemetry()` reads consent;
`telemetry(True)` and `telemetry(False)` persist only an explicit learner choice.

`artifact_add(path, title, workspace_root=..., path_base=..., coordinate=None,
expected_revision=...)` requires explicit absolute workspace and path-base roots. It records
an existing file inside that workspace at the existing completion chronology, using the same
relative-path upsert and containment rules as the CLI. Call it only at the two authored
artifact moments: phase ceremony and confirmed homework submission. It adds no timing
gate or general filesystem tool. `artifacts()`
returns copied entries. A stopped writer can reopen a relocated workspace and state tree with
new explicit roots; persisted artifact paths remain workspace-relative.

Companion results are frozen copied values. Homework tokens and artifact paths are controller
values; send models only the assignment or relative showcase content needed for the task.
Optional `expected_revision` arguments reject stale writes with the existing `Conflict`
exception. Read-only homework checks preserve record, queue, receipts and scratch bytes;
prepared file operations may still recover as described above.
