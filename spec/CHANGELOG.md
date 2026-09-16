# Specification changelog

All changes to the Skilling specification, including errata. See [CONTRIBUTING](../CONTRIBUTING.md) for the change process and semver rules.

## 1.4.0-draft — 2026-08-08

In development alongside this wave; entries below land with the change they describe.

### Recoverable file-runtime transitions — 2026-09-16

The [file runtime](runtime.md#recoverable-file-runtime-transitions) now journals the record
and teaching scratch as one recoverable transition, reads them as a coherent snapshot, and
checks both before-images under its course lock. `advance --key` retains lifetime operation
identities across intervening writes and completion; retries return current state with a
replay marker, and different-input key reuse refuses without effects. Unkeyed advance and
answer gain atomic recovery without a retry guarantee. Legacy scratch keys are reserved
without guessed input, and existing version-1 completion journals remain compatible. The
typed snapshot/transition API is file-only; the generic store protocol and public record,
log and homework models are unchanged. This does not promote package/specification versions
or establish confirmed-submission recovery.

### Recoverable completion and required backend operations — 2026-09-16

[Runtime completion](runtime.md#completion) now prepares a stable operation identity and the
complete runtime-derived write set before durable effects. The required store interface adds
`get_completion_receipt` and `commit_completion`, with `CompletionReceipt`, `HomeworkWrite`,
`CompletionCommit` and `CompletionCommitResult` defining the public seam. Existing third-party
backends must implement these operations; completion refuses unsupported backends before
writing, with no fallback to the old separate writes. This is a backend-contract change
within the current draft, not a package or specification version promotion.

Recovery preserves the original completion/log/unlock times, final phase badges, homework
slot or queue, and completion checkpoint reset. Cooperating reads and writes finish pending
intent first; retries return current record/revision data. Completion hooks fire after a new
durable commit and are suppressed during recovery or replay, so external delivery remains
best-effort. Portable internal recovery metadata supplements the existing record/log/homework
layout; existing files and history are preserved without inferred legacy repairs. Completion
recovery does not establish general scratch or confirmed-submission interruption safety.

### The learner workspace

[Workspace](workspace.md) specifies one folder a learner opens in any Agent-Skills host —
Claude Code, Codex, Claude Cowork, ChatGPT Work — with everything the machinery needs hidden
under `.skilling/` and a visible root that grows with what the learner builds. `.skilling/state`
is a `<state-root>` exactly as [the file layout](runtime.md#the-file-layout) already binds it —
re-pointed, not forked — and `.skilling/courses` holds fetched content in `<id>@<version>`
directories, a subtree structurally disjoint from state, so a course's progress and its content
never collide.

The manifest, `.skilling/workspace.yaml`, is what makes a folder a workspace: per course an
`id`, `version`, the `ref` exactly as the learner gave it, a `path` relative to `.skilling/`, a
`showcase` directory relative to the workspace root, and `added_at`. Every path in it is
relative, so zipping or syncing the folder into a sandboxed host carries everything the
manifest points at. Discovery is git's model — walk up from the current directory to the
nearest directory holding the manifest, with `SKILLING_WORKSPACE` overriding the start point —
and keys on the manifest existing, so a stray legacy state directory is never mistaken for a
workspace. Host entry files (`CLAUDE.md`, `AGENTS.md`) are maintained inside marked blocks,
create-or-grow, with foreign content outside the markers never touched.

### Artifacts on the record

The [progress record](runtime.md#the-progress-record) gains an optional `artifacts` list —
`path` (workspace-relative, POSIX separators), `title`, `coordinate`, `added_at` — pointers to
work the learner built, recorded only through the CLI at the two moments the loop already owns:
phase ceremony and confirmed homework submission. Artifacts never gate the flow, and they are
not a fourth kind of evidence — the record holds a pointer and a title, never a judgement.
Additive: a record without the field loads unchanged.

### Enumeration reports location within a workspace

1.3's [course enumeration](skill-pack.md#course-enumeration) deliberately reported no path and
no version — honest at the time, because state genuinely never recorded where a course's
content lives, and documented as the gap it was. The workspace manifest now records exactly
that fact, so within a workspace the enumeration reports each course's location, and a fresh
conversation no longer has to ask the learner where a course they already added lives. Outside
a workspace nothing changes.

### Folder-scoped installs by default

[Skill pack installs](skill-pack.md#installing-and-removing) become folder-scoped by default —
into the enclosing workspace's own `.claude/skills/` and `.agents/skills/`, receipted exactly
as before — with the learner's home profile as the opt-in rather than the default. A pack in
the folder travels with the folder, which is what a sandboxed host that mounts the workspace
needs and a home-profile install can never give it.

## 1.3.0-draft — 2026-08-05

In development alongside Wave 1; entries below land with the change they describe.

### Quiz questions must be numbered 1, 2, 3

A course with a quiz numbered `1. 1. 1.` validated cleanly and rendered, in any markdown
viewer, as `1. 2. 3.` — indistinguishable from a correctly numbered quiz to every human who
ever looked at it. The gap was invisible precisely where it mattered: `about` references
[index questions by these numbers](course-format.md#quick-quiz), so a duplicate or a skipped
number silently points remediation at the wrong question.

This is 1.0's [numbering and bijection rule](course-format.md#numbering-and-structure) applied
one level down — phases and lessons already had to number `0`/`1`..`n` with no gaps or repeats;
quiz questions within a lesson now face the same requirement, fixed at exactly `1`, `2`, `3`.
Both example courses already number their quizzes this way, so nothing conforming breaks.

### Mid-lesson position

`position` gains `question_index` (optional, 0-based), meaningful only when `beat` is `quiz` or
`remediate`. A runtime that records it resumes the learner on the recorded question instead of
restarting the quiz. Additive, like `beat` itself: a record without it resumes at question 0.

Remediation bookkeeping — wrong-answer counts, an offered revisit — stays runtime-private and
is never persisted, so it resets on resume. [Resume](runtime.md#resume) writes down the
resulting residual: a resumed session may re-offer a revisit already offered, or route forward
from the concept gate when a return to the quiz was pending. Mild, recoverable, and at most
once per resume.

### Attestation on `objectives_met`

`objectives_met` gains `provenance`, required whenever `evidence` is `observed`: `checked` (what
was actually inspected), `verify` (the objective's verify sentence, verbatim), and `attested_by`
(which host is making the claim). [Objectives and the record](runtime.md#objectives-and-the-record)
states why plainly — it is recorded **because the attestation cannot be verified**, not as a
substitute for verification. A store has no way to confirm that a host actually ran the check it
claims to; the honest response is to write down exactly who made the claim and what they said
they checked, so a later reader can weigh it, rather than either refusing the claim outright or
accepting it silently.

`explained` and `homework` entries carry no `provenance` — only `observed` is a claim about
something outside the conversation. Additive: a 1.1/1.2 record with `explained` or `homework`
evidence keeps loading unchanged, because neither ever needed provenance to begin with.

### Skill pack: a fixed triad, installed once per learner

[Skill pack](skill-pack.md) specifies how a course reaches a learner through a host's own
Agent Skills mechanism — `/name` in Claude Code, `$name` in the generic convention that Codex
and roughly forty other hosts share — instead of a bespoke integration. The reference
implementation ships one: a fixed, hand-maintained triad, `learn`/`progress`/`homework`,
installed once per learner via `skilling install` — no course argument, no per-course
generation step. Every course-structure fact a skill states — a title, a lesson count, a
learner's position — is read from the CLI at the moment it is needed; none is ever baked into
a skill's own files. Course identity and persona are resolved the same way, at invocation time,
by calling `skilling courses` and `skilling next` rather than by remembering or authoring
either.

`skilling courses` is new: a read-only enumeration of every course a learner has local progress
for, most-recently-active first, id and best-effort title and last-activity date only — the
mechanism a triad installed once per learner needs to ask "which course did you mean" and a
pack generated for exactly one course never did. `skilling install`/`skilling uninstall` write
and remove the whole triad as one receipt-based unit across both host conventions, atomically:
a hand-edit to one skill refuses removal of all three, not just the edited one.

An earlier design, `skilling pack <course>`, generated a skill pack per course, baking that
course's id and persona into the generated files at packaging time. It did not ship: reviewing
it against a hand-written precedent that generated per course as well showed the generated
content never varied by more than a title string across courses, so per-course generation was
protecting nothing a fixed triad does not already cover, while adding a packaging step per
course, an install step per course, and no path for a choreography upgrade to reach an
already-installed course without redoing both. The triad and its once-per-learner install
replace it.

## 1.2.0-draft — 2026-08-05

**A correction, and the surface it needs.** 1.1's `tested_by` let a quiz settle an objective.
That was wrong, and the golden example made it obvious: 168 capability claims written into the
record on the strength of multiple-choice answers, 142 of them resting on a single four-option
question — guessed right a quarter of the time. Worse, 31 described actions a quiz cannot
observe at all. `Have Node.js and npm installed on your computer` was being settled by *"Why
use nvm instead of installing Node.js directly?"*, which a learner with no Node at all answers
correctly.

The specification's own [what the record knows](../docs/concepts/what-the-record-knows.md) says
an objective recorded without evidence is worse than one left absent, because a later tutor
believes it. 1.1 shipped 168 violations of that.

### The diagnosis

`tested_by` conflated two jobs with wildly different accuracy requirements.

**Aboutness** — "this question touches that objective" — steers what a tutor says next. Cheap,
useful, and tolerant of error: being slightly off costs a slightly-off sentence.

**Evidence** — "this learner can do that" — goes into a record that outlives the conversation.
Expensive, load-bearing, and intolerant of error.

One field cannot serve both. 1.2 separates them.

### Objective kinds

Every structured objective now declares a `kind`:

- **`knowledge`** — the learner can explain something. Settled by a tutor probing in
  conversation.
- **`practice`** — the learner did something, or their machine is in some state. Settled only by
  a runtime that can go and look.

The distinction is not academic: `Understand what npm is` and `Have npm installed` read alike
and need completely different evidence. Courses sit heavily on one side — the golden example is
72% practice, and `hello-skilling` is 100% knowledge.

### Runtime capabilities

A Conforming Runtime claim now names what it can observe — `converse`, `observe`, `assess` — and
**a runtime must not settle an objective whose kind it lacks the capability for.** A chat tutor
with no filesystem access leaves every `practice` objective alone however confident the learner
sounds. A text walker settles nothing at all, and is still conforming.

This is what makes the honest outcome the *default* rather than a discipline.

### Verification

A `practice` objective may carry `verify` — a sentence describing what success looks like, for a
runtime that can go and look:

```yaml
verify: Both node and npm report a version number when asked for one
```

Prose rather than a command, for the same reason [ceremony carries facts rather than
sentences](course-format.md#ceremony): an agent with shell access is good at working out *how*
to check something, and a literal command is a liability — `node --version` is wrong behind a
version manager, and Windows and macOS need different commands for the identical objective.

An optional literal `check` is available where determinism matters, and is explicitly a
**proposal**: a runtime may decline it, must put it through its host's permission model, and
must never run it silently.

`verify` is optional even on a `practice` objective. "Apply the design system consistently" is a
judgement, not a check, and an objective with no `verify` stays unsettled — which is the honest
outcome and better than a check that pretends.

### Also

- **`tested_by` → `about`**, and there is no `evidence: quiz`. Evidence values are now
  `explained`, `observed`, `homework`.
- **The quiz has an honest job:** a checkpoint that surfaces confusion and drives remediation.
  It settles nothing. All of the golden example's mappings survive with their real purpose
  intact.
- **The MCP binding now has a reason to exist.** It was deferred as "a surface we should
  support"; it is the surface that would give a runtime `observe`, and therefore the only honest
  way to settle a `practice` objective. Specified for, not yet built.

## Errata against 1.1.0-draft

Found by porting a real 64-lesson course — the one this format was generalised from — into the
repository as `examples/coding-bootcamp` (which has since moved out of the repository). All three are the
kind of thing only real content finds.

- **Key Terms was over-specified by its validator, not by its text.** The specification asks
  for `- **Term**: definition` items. The validator additionally required the colon to touch
  the closing asterisks and forbade `*` inside the term, which rejected
  `- **CPU** (Central Processing Unit): …` and `` - **`p-*`**: … `` — both perfectly reasonable
  and both used throughout the source. Eleven false findings; the check is now as loose as the
  prose always was.
- **`{hashtags}` was missing from the ceremony placeholder set.** The source's share copy ends
  in four hashtags. With no placeholder, a literal template had to restate the tags that
  `brand.hashtags` already declared — the exact duplication this format exists to prevent.
  Added, rendered with each `#` applied.
- **Phase `highlight` guidance produced text that reads wrong.** It said to write a clause
  completing "this learner just…", so authors wrote third person — and the most obvious use is
  a share post in the first person, which then reads "I made *their* first commit". The
  guidance now asks for pronoun-free clauses, which work in both voices.

The port also surfaced eight defects in the *course* rather than the specification: seven quiz
answers that restated the correct option and gave no reason, and one homework section with no
submission line. Those are fixed in the ported copy, and they are what `quiz-answer-no-reason`
exists for.

## 1.1.0-draft — 2026-08-03

Additive. Four surfaces, no change required of any existing course — a `spec_version: "1.0"`
course validates unchanged under a 1.1 tool, and there is a test that proves it.

### Hooks

Eight named events a runtime emits to registered sinks: `lesson_started`, `gate_opened`,
`quiz_answered`, `lesson_completed`, `badge_awarded`, `phase_completed`, `course_completed`,
`homework_submitted`. One envelope, fire-and-forget delivery that must survive a sink which is
slow as well as one which is broken.

The rule that matters is the one about what a runtime must *not* do: no enrolment, no cohorts,
no catalogues, no dashboards. Those attach to the events from outside. It is the most
opinionated line in the specification and the reason this stays a format rather than becoming
an LMS.

Hooks were deliberately deferred at 1.0 on the grounds that a specification should not bind
extension points before anyone has extended anything. They bind now because there is an
adopter with nine branded share prompts and a completion beacon that 1.0 had nowhere to put.

### Telemetry

Opt-in per learner and ternary, identity as a write-once anonymous id, payloads content-free.
Consent is checked before a sink is ever handed an event, so a sink that forgets to check is
not *able* to leak.

Stated plainly, because it is true: content-free is not behaviour-free. An opted-in learner's
gate timings and answer booleans let a sink reconstruct where they hesitated and what they got
wrong. A producer presenting the choice should not pretend otherwise.

### Ceremony

A `ceremony` block in the manifest carrying **facts a tutor may not invent** — product, url,
mention, handles, hashtags — plus a one-clause `highlight` per phase, plus optional literal
templates used verbatim when present.

This shape follows from the framework being AI-first. A tutor writes a better celebration than
a template can, contextual and different every time; what it must not do is guess a social
handle. So the manifest holds the facts and the tutor writes the prose. A template is the
escape hatch for wording that is genuinely non-negotiable, and for runtimes with no model in
them.

Derived numbers arrive as placeholders (`{completed_count}`, `{lesson_count}`), which is how
an author gets "3 of 9" into a share post without ever writing a count. Templates are scanned
for authored counts like everything else.

### Addressable objectives

Optional structured `objectives:` in lesson frontmatter with stable ids, `objectives_met` on
the record with `evidence`, and `tested_by` mapping quiz questions to objectives.

An audit of 1.0 found that everywhere the format talked *to the tutor* it was AI-native, and
everywhere it modelled *the learner* it was a content-management system. Objectives were the
sharpest instance: a lesson's actual contract, written as prose that nothing could reference.
Addressable objectives let remediation name the objective a wrong answer implicates rather than
re-presenting the whole concept.

Structured and prose objectives are mutually exclusive — allowing both would be two sources of
truth for the same sentences.

Writing `objectives_met` is optional, as homework checking is: a runtime that cannot judge
writes nothing and conforms. `tested_by` is what lets a model-free runtime participate at all.

### Conforming Producer

The fourth conformance class, for anyone embedding a runtime in a product: never write learner
state around the runtime, never synthesise learner input, never undo protocol ordering in the
interface, present the telemetry choice honestly.

### Also

- **A badge is not an objective**, stated plainly. `skills_unlocked` records that a lesson
  completed; `objectives_met` claims a capability was demonstrated. A runtime must not infer
  either from the other. Badge behaviour is unchanged — what changed is that the specification
  now admits what a badge means.
- **The quiz's design is now argued rather than assumed.** A new section says what three fixed
  hand-written questions buy (validatable, comparable, stable keys for assessed mode) and what
  they cost (a tutor that could ask a better question is not allowed to). The page previously
  read as though multiple choice were obviously correct.

## 1.0.1-draft — 2026-08-03

Editorial only. Fourteen places where the text did not say what it meant, found by handing
[course format](course-format.md) to three readers who had nothing else — no repository, no
example course, no author to ask — and asking each to author a conforming course. All three
courses validated with zero findings, which was the *weak* result; the useful output was the
list of things each of them had to guess.

Two were genuine divergences, where readers made different choices from the same sentence:

- **Whether a phase `overview.md` obeys the lesson section rules.** One reader used `##`
  headings in an overview; two deliberately avoided them, unsure whether the "no other `##`
  headings" rule reached that far. It does not: an overview now explicitly has no constraints
  at all.
- **Whether markdown tables are allowed inside a section.** The list "Prose, code blocks,
  `###` subheadings, lists" read as exhaustive to one reader, who avoided a table that would
  have taught his subject better, while another used one. The list is now stated to be
  illustrative.

Twelve more were unanimous guesses — every reader had to decide, and every reader said so:

- **Phase numbers are not zero-padded**; only lesson numbers are. All three inferred this
  correctly from one example and flagged it as an inference.
- **`## Homework Assignment` is never declared in `sections`.** Its presence is settled by the
  manifest.
- **Registry order applies to optional sections too**, not only required ones.
- **The absence form is exactly `status: none` plus a non-empty `intent`** — a closed
  vocabulary, now stated as one.
- **The last lesson of a course has no `## Next Up`** and nothing for a runtime to generate a
  teaser from. Previously the specification simply stopped short of saying so.
- **A `#` heading is not forbidden**, since only `##` is constrained — but it duplicates the
  frontmatter title, and now says so.
- **A new course starts at `1.0.0`.**
- **Badge ids follow the same rules as the course `id`** — which the validator already
  enforced while the text constrained only uniqueness. A specification narrower than its own
  tool is a specification bug.
- **A registered badge need not be unlocked by any lesson.**
- **Unknown fields are rejected, not ignored** — true of the implementation, unstated in the
  text.
- **The course directory's own name is free** and need not match `id`.
- **The quiz answer line's shape is parsed**, so it is now specified: literal `**Answer:**`,
  label, restated option text, then the reason, wrapping freely.

Two clarifications go further than wording:

- **"Structural count" is now defined.** It means a count of the course's own phases and
  lessons, or of the learner's position among them. A course titled *Three Useful Knots* was
  never in breach, but two readers worried it might be. The rule is also now stated to cover
  `overview.md` and `intent` strings, because a runtime reads those to the learner.
- **"Self-contained" was generalised from a coding course and said so by accident.** A reader
  observed that "nothing outside the lesson" makes any physical-skill exercise impossible,
  since you cannot tie a knot in a markdown file. It means no outside *information*; required
  equipment is fine and should be named.

One finding is not fixed here because it needs new mechanism: a badge is written to the record
when its lesson completes, which can be *before* the learner has done the homework that badge
implies. A reader spotted this independently. It is addressed in 1.1, where the specification
starts distinguishing a completion marker from a capability claim.

## Errata against 1.0.0-draft

Corrections the reference implementation forced. Recorded rather than silently worked
around — a library that quietly disagrees with its own specification is the failure mode
this section exists to prevent.

- **A lesson title ending in `?` inside a `{ … }` flow mapping is not valid YAML.** The
  draft's own full manifest example could not be loaded by any conforming tool. The example
  now quotes the title, and [course format](course-format.md#the-manifest) notes which
  characters need quoting in flow mappings. Found by the round-trip test over every YAML
  example in this specification.
- **Phase completion is derived, not stored.** [Ceremony](runtime.md#phase-boundary-ceremony)
  said a runtime must "mark the phase complete in the record", which contradicted the rule
  that structural facts are never stored. Reworded: completion is computed from the phase's
  lessons and the record's `completed` set, and no field records it.
- **`get_homework_archive` added to the store interface.** The specification required a
  retried submission to return the archived result, but the operation table gave a store no
  way to read its own archive. The read half of `append_homework_archive` is now listed in
  [the store interface](runtime.md#the-store-interface).

## 1.0.0-draft — 2026-08-03

First published draft. Promoted to 1.0.0 once the reference implementation's exit gates are green and `examples/hello-skilling` delivers end to end.

### Added

- **[Course format](course-format.md)** — course directory layout, `course.yaml` manifest, numbering and bijection rules, the no-authored-counts rule, lesson frontmatter, the section registry, declared absence, section content rules, the Quick Quiz grammar (three questions, four options, inline answer with reason), the Homework Assignment grammar, the `assets/` convention, and course-version semantics with coordinate stability.
- **[Runtime](runtime.md)** — scope of conformance (transitions, not prose), the delivery loop and its beats, gates as open waits, declared-absence skips, one-question-at-a-time quiz delivery, remediation, idempotent completion, phase-boundary ceremony, resume, the progress record, the append-only completion log, the streak algorithm, the single-slot homework mailbox, the store interface, and the normative single-learner file layout.
- **[Conformance](README.md#conformance)** — three classes: Conforming Course, Conforming Runtime, Conforming Store.

### Deliberately not bound

Assessed mode, hooks and telemetry, the runtime API, the MCP binding, and skill packs. Each arrives as a minor version once an implementation has exercised it — see [what 1.0 deliberately leaves out](README.md#what-10-deliberately-leaves-out).

### Notes on provenance

This draft generalises a single 64-lesson course delivered through a coding agent. Six defects in that course drove specific rules here; five are retired by 1.0 and one — answer keys held apart from learner-visible content — waits for assessed mode. The table is in [why these constraints exist](README.md#why-these-constraints-exist).

The heavier standards register of the pre-1.0 working draft (per-rule identifiers such as `MAN-004`, RFC-2119 capitals, and a fourth Producer conformance class) was dropped before publication. Stable identifiers now belong to [validator error codes](../docs/error-codes.md), which is where they are actually used.
