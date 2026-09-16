# Implementing a runtime

How to build a conforming tutor. The requirements are in [runtime](../spec/runtime.md); this page is how to satisfy them without rewriting the parts that already exist.

## What you are actually adding

The delivery loop, the record write set, and persistence are all mechanical, and all of them are already in the `skilling` package. A tutor adds exactly one thing: judgement — teaching prose, re-explanation, and (optionally) homework verdicts.

If you find yourself writing a state machine or deciding what completion should write, stop. That is the part that is specified, tested, and shared.

```python
from pathlib import Path

from skilling import Course, FileProgressStore
from skilling import delivery

course = Course.load(Path("./brewing-basics"))
store = FileProgressStore("./.skilling")
record, revision = delivery.load_or_create(store, course, learner_id="a1b2c3")
```

## Drive the machine; don't reimplement it

The loop is pure functions over an explicit state value. No I/O, no clock, no model.

```python
from skilling import Beat, Input, LessonShape, LessonState, advance
from skilling.delivery import legal_inputs

shape = LessonShape(has_exercise=True, is_phase_end=False)
state = LessonState.start(shape)          # welcome
state = advance(state, Input.NEXT)        # objectives
state = advance(state, Input.NEXT)        # concept
state = advance(state, Input.NEXT)        # gate-concept
```

At any point, `legal_inputs(state)` tells you what the learner may do next — which is what you turn into tool definitions if your tutor is a model with tools. An input that is not legal raises `IllegalTransition` rather than being quietly absorbed, so a model that tries to skip the quiz fails loudly in development instead of subtly in production.

The machine *permits*; it does not advise. Where the specification says a runtime "should" offer something, that is a predicate:

```python
from skilling.delivery import should_offer_revisit

if should_offer_revisit(state):     # two or more wrong in this quiz
    ...
```

## Hold the gates properly

A gate is an open wait. Two things are easy to get wrong and both matter:

- **No timeouts, ever.** Not a short one. A learner who leaves mid-exercise and returns in a fortnight must find the same gate. If you record beat-level position (`position.beat`), resume lands exactly there.
- **Going deeper is not progress.** `Input.GO_DEEPER` returns to the concept beat without advancing position. A learner asking four follow-up questions has moved nowhere, and a runtime that advances them is punishing curiosity.

If you are embedding a model, the temptation is to let it decide when to move on. Don't: the model narrates, the machine transitions. That separation is what makes conformance checkable at all, since [nothing in the specification binds prose](../spec/runtime.md#scope-of-conformance).

## Let the shared write set do the writing

```python
outcome = delivery.complete_lesson(store, course, record, revision, lesson)
record, revision = outcome.record, outcome.revision

if outcome.already_completed:
    ...   # a revisit; nothing was counted, and nothing should be announced as progress
for badge in outcome.badges_awarded:
    ...   # tell the learner
if outcome.phase_completed is not None:
    ...   # celebrate; your words
if outcome.homework_placed:
    ...   # show the assignment
```

This prepares one completion operation before writing: the original timestamp, log entry,
final record with lesson and phase badges, and any homework slot or queue update. The file
store durably records that intent, applies the log before the record, then completes homework
and resets completion-related scratch before acknowledging. Reopening through the store
finishes pending intent under the same course lock used by other reads and writes. A retry
uses the original operation and its dates, even on the next day; it returns the current
record and revision, preserving later acknowledged changes.

Operation identity belongs to the runtime and binds learner/course/version/coordinate. Do
not infer a failed completion from the record's next-lesson position or the last element of
`completed`. The completion receipt supplies replay identity, while the current record still
authorizes the next lesson's transitions. A prior receipt cannot bypass an unfinished quiz.

Preserving badges is one reason to reuse this rather than reimplement it: in the course this format generalises, eleven lessons declared badges and the delivery system wrote none of them, for months, unnoticed. It was not a hard bug. It was an easy one, in code nobody thought was interesting.

## Persist through the store, not around it

```python
from skilling import Conflict

try:
    revision = store.put_record(updated, revision)
except Conflict:
    ...   # someone else wrote; re-read and retry, never force
```

Writes are optimistically concurrent. A `Conflict` is information, not an obstacle — silently overwriting is the failure mode the revision token exists to prevent.

To add a backend, implement the required `ProgressStore` operations, including
`get_completion_receipt(learner_id, course_id)` and `commit_completion(commit)`. The public
`skilling.store` exports `CompletionReceipt`, `HomeworkWrite`, `CompletionCommit` and
`CompletionCommitResult`; their fields and semantics are in the
[store contract](../spec/runtime.md#completion-commit). Runtime code derives the effects;
your backend validates and persists them, including expected record/log/homework comparisons,
serialized recovery, and returning the current stream on replay. It must never load course
content to reconstruct a missing effect.

This extends the backend contract: an older third-party backend without these methods raises
`NotSupported` from `complete_lesson` before new completion effects. There is no unsafe
fallback. Entry-point discovery still discovers factories; successfully loading a plugin does
not certify its completion support. Exercise the public store contract and interruption,
replay and concurrent-writer cases against your backend before claiming that support.

`Conflict` means reread and prepare against current state. `StoreBusy` means the bounded
course-lock wait expired. `RecoveryRequired` means the intent or target bytes cannot be
safely reconciled; preserve the files for inspection rather than deleting the journal,
forcing stale bytes, or trying a guessed repair. The CLI reports the latter two as
`store-busy` and `recovery-required` (exit 1); stale revision conflicts retain exit 3.

### Recovery scope and legacy state

For the file backend, `<state-root>/<course-id>/completion.yaml` holds a prepared write set
or the latest committed receipt. Prepared metadata contains course-relative targets and
exact before/after bytes; the store validates every target before applying any of them.
Ordinary operations resolve pending intent under the existing course lock. Invalid metadata,
unsafe paths and unexpected target bytes fail closed. The record, completion log and
homework formats are unchanged; `completion.yaml` is internal recovery metadata, not a new
record model or a replacement source of learner progress.

Move the whole state directory, including a pending journal, after all writers have stopped.
Recovery needs no original source path, absolute workspace root or transcript. The supported
coordination scope is cooperating processes on one local filesystem. Atomic replacement and
filesystem flushes support the tested process-interruption behavior; this is not evidence of
physical power-loss survival or coordination across network-mounted clients.

Unjournaled legacy records remain readable. Already-completed coordinates are no-ops; the
runtime does not invent absent historical homework or remove duplicated old log entries. An
uncompleted coordinate already present in the matching legacy log raises `RecoveryRequired`
when no trustworthy intent can recover it. Preserve that state and inspect record, log and
homework together; the runtime does not choose a historical repair for you.

The file runtime's `read_runtime_snapshot` returns one coherent record/revision/scratch
snapshot. `commit_transition` validates a runtime-supplied `TransitionCommit` and compares
both record revision and exact scratch bytes before preparing `transition.yaml`. It persists
the record and scratch together, so interruption cannot forget wrong-answer or revisit state.
This file-only extension leaves the generic `ProgressStore` protocol unchanged; use the
[typed values and methods](../spec/runtime.md#recoverable-file-runtime-transitions), not
separate record/scratch writes, for a CLI transition.

`advance --key` stores immutable identities under `transition-receipts/`. Keep each key for
one authorized action and retry with the same input. A replay returns the current coherent
snapshot with `replayed: true`, including later objective, artifact and consent edits; it
never restores an old response. Different-input reuse raises `IdempotencyKeyConflict` (CLI
exit 3). Completion preserves keys for the whole learner/course/version stream. Unkeyed
`advance` and `answer` recover atomically but do not gain idempotent retries.

Transition, submission and version-1 completion journals are validated together before recovery; two
prepared journals refuse without target writes. Legacy scratch keys have no trustworthy
input and are reserved/refused, not replayed or guessed. New authorized actions use fresh
keys. Preserve transition intent and all receipts when moving the stopped state directory.

## Homework: mechanics are given, judgement is yours

The core places, displays and queues homework. To submit, read the slot and revision, derive
`SubmissionToken.for_slot(learner_id, course.id, course.version, slot, revision).encode()`,
show the assignment, and obtain the learner's distinct confirmation. Pass that retained
value to `submit_homework(store, learner_id, course.id, slot.coordinate, token=token)`.
The CLI equivalent is `homework check` followed, after confirmation, by
`homework submit --token TOKEN` with the same course/state/learner selection.

The token is not consent proof or a credential. Never replace it after confirmation. A
`Conflict` (CLI exit 3) means the assignment changed before acceptance: inspect again and
ask for a new confirmation. Retry an uncertain call with its original token, including on
the next day. An accepted token returns its original archive even if another assignment is
now active; no coordinate-only fallback selects a different item. Missing, malformed or
wrong-stream CLI tokens fail with `invalid-submission-token` (exit 2) before state opens.

Backends must add `get_submission_receipt` and `commit_submission` with the frozen
`SubmissionReceipt`, `SubmissionCommit` and `SubmissionCommitResult` exports. The runtime
derives the archive and queue promotion; the store validates and persists them together.
Older backends get `NotSupported`, naming missing methods before effects. All file journals
validate together before any recovery. Keep `submission.yaml` and `submission-receipts/`
when relocating stopped state. Corrupt metadata requires inspection, and old duplicate
archives are preserved. A new uninterrupted submit emits best-effort hooks after commit;
recovery/replay emits none, and post-commit death can omit dispatch. See the
[backend contract](../spec/runtime.md#submission-commit) for validation and write ordering.

If your tutor can judge work, you owe two things the specification is strict about:

- A check returns a verdict **per requirement** — `met`, `partial`, `not-yet` — each with a reason. Not an overall grade. The `- [ ]` items are the unit of feedback because that is what a learner can act on.
- A check **never** changes slot state, no matter how finished the work looks. Separating feedback from completion is what lets a learner ask "how am I doing?" a dozen times without accidentally finishing.

Submission needs its own explicit confirmation, distinct from the input that asked for it. Not inferred from a passing check, not from enthusiasm, not from silence.

If your tutor *cannot* judge work, display the assignment and accept a confirmed submission. That is conforming — checking is optional, and pretending to check would be worse than declining to.

## Emit events; do not grow a platform

**Since 1.1.** Pass a `Dispatcher` and the eight events fire from the write set and the loop. It defaults to a no-op, so hooks are opt-in for a runtime as well as for a learner.

```python
from skilling.delivery import Dispatcher, JsonlSink, ThreadedSink

hooks = Dispatcher(
    first_party=[JsonlSink("events.jsonl")],          # inside your boundary; sees learner_id
    telemetry=[ThreadedSink(YourHttpSink(url))],      # leaves it; consent-gated, anonymised
)
delivery.complete_lesson(store, course, record, revision, lesson, hooks=hooks)
```

Completion events are dispatched only after the durable commit. A new uninterrupted commit
emits the existing events using its original timestamp. Read-triggered recovery and completed
retries emit none; a crash between commit and dispatch can omit events. These hooks are
best-effort notifications, not an exactly-once external transaction.

Three things the dispatcher does so you cannot get them wrong:

- **Swallows every sink failure.** A raising sink never reaches the learner and never blocks a record write.
- **Checks consent before a sink sees anything.** A telemetry sink registered against a learner who has not opted in receives literally nothing. Do not put that check in your sink; it belongs where a sink cannot forget it.
- **Substitutes the anonymous id** for telemetry, so `learner_id` cannot leave your boundary by accident.

What it cannot do for you is make a slow sink safe. Wrap anything that touches a network in `ThreadedSink`: fire-and-forget has to survive slowness, not only failure.

### An HTTP sink, in full

The core ships no network sink on purpose — the framework should phone nobody's home by default. Here is the whole thing, stdlib only:

```python
import json
import urllib.request
from skilling.delivery import Event

class HttpSink:
    def __init__(self, url: str, *, timeout: float = 2.0) -> None:
        self.url = url
        self.timeout = timeout

    def emit(self, event: Event) -> None:
        request = urllib.request.Request(
            self.url,
            data=event.as_json().encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            response.read()
```

Wrap it in `ThreadedSink` and register it as `telemetry`, not `first_party`, if it leaves your trust boundary. Retries, batching and backoff are yours to add — the specification deliberately says nothing about them, because a sink's reliability is the sink's problem.

### Ask for consent honestly

`opt_in` is ternary: `null` means ask, once. Say what is actually sent, say that declining costs nothing, and make declining the default. `skilling deliver`'s prompt is a reasonable model — and note it names *which quiz answers you get right*, because [content-free is not behaviour-free](concepts/the-telemetry-sink.md#content-free-is-not-behaviour-free).

## Celebrate with facts, not sentences

**Since 1.1.** At a phase boundary, resolve ceremony copy in order: a literal template if the course has one, else compose from the declared `brand` facts, else plain unbranded prose.

If you have a model, step two is where you belong. `skilling.ceremony.facts(brand)` hands you exactly what you may state — product, url, mention, handles, tags — and the constraint is absolute: **say nothing that is not in there.** Not a URL you think is right, not a handle inferred from the product name. That single rule is why the manifest carries facts at all, because a model asked to write a share post will otherwise guess `@YourCourse` when the handle is `@your.course`.

Derived numbers arrive as placeholders. `{completed_count}` and `{lesson_count}` are filled from the manifest and the record, which is how a share post says "3 of 9 lessons done" without any author ever having written a number.

## Name the objective, not the lesson

**Since 1.1.** When a wrong answer's question is [`about`](../spec/course-format.md#remediation-not-evidence) an objective, say which:

```python
implicated = fm.objectives_for_question(question.number)
```

"That one was about opening a terminal" beats re-printing the concept at someone. This is the entire payoff for making objectives addressable.

## Declare what you can actually see

**Since 1.2.** Your conformance claim names its capabilities, and they decide what you may write about a learner:

```python
from skilling.course import Capability

caps = [Capability.CONVERSE, Capability.ASSESS]     # a chat tutor: no filesystem
record, revision, settled = delivery.mark_objectives_met(
    store, record, revision, lesson,
    met=["what-npm-is", "install-node"],            # what you believe
    capabilities=caps,                              # what you may claim
)
# settled == ["what-npm-is"] — install-node is practice, and you cannot see a machine
```

The rule is enforced in `mark_objectives_met`, not left to you, for the same reason telemetry consent lives in the dispatcher: a runtime that claims more than it can observe must not be *able* to write it. Evidence follows from the kind, so you cannot label an observation as an explanation either.

**A quiz settles nothing.** There is no `evidence: quiz` and no code path that produces one. One four-option question is guessed right a quarter of the time, and none can establish that software is installed. Use `about` for remediation and leave the record alone.

If you have `observe` — a coding harness with shell and filesystem access — `delivery.settleable(lesson, caps)` gives you the objectives you may settle, each with the `verify` sentence saying what to look for. Work out *how* yourself; that is what you are good at. A course's `check` command, if it supplies one, is a proposal you may decline and must never run silently.

## Claiming conformance

A claim names its class and version range: *"Conforming Runtime, Skilling 1.0"*. Then hold two lines:

- **Don't grow a catalogue inside the runtime.** Course discovery, cohorts, enrolment, reporting — all of that belongs outside. A runtime delivers one course to one learner.
- **Don't let anything write learner state around the runtime.** Reading records for reporting is fine. Writing them is not, and neither is synthesising learner input to unlock a gate.

An implementation that ignores those isn't a Skilling runtime with extras. It is an LMS using a borrowed file format.

## A worked reference

`skilling deliver` is a complete Conforming Runtime in about three hundred lines with no model in it — see [`cli/learning/_walk.py`](../packages/skilling/src/skilling/cli/learning/_walk.py). It re-prints rather than re-explains and cannot judge homework, and it conforms anyway. That is the shape of the contract: everything mechanical is required, and nothing about the teaching is.

Read it before building yours. It is the smallest honest answer to "what must I actually do?"
