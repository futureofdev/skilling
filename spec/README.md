# The Skilling specification

**Version 1.4.0-draft** · Specification text licensed [CC BY 4.0](LICENSE)

> 1.4, in development alongside this wave, adds the learner [workspace](workspace.md) — one
> folder, opened in any host, carrying state, fetched content, and what the learner builds —
> and artifacts on the record. Entries land in the CHANGELOG per change, and nothing here
> binds until an implementation has exercised it.

Skilling is an open format for AI-tutored, skill-based courses. It specifies three things precisely enough that independent implementations interoperate:

- **What authors write** — a course directory: one manifest, markdown lessons with a fixed anatomy → [course format](course-format.md)
- **What a tutor does** — the delivery loop, its gates, and what it writes → [runtime](runtime.md)
- **What is durably true afterwards** — the learner's record, and the store behind it → [runtime](runtime.md#the-progress-record)

In 1984 Benjamin Bloom showed that students taught one-to-one outperform classroom students by two standard deviations, and asked how to deliver that at scale. AI tutors are the first credible answer. Skilling standardises the part that must not fragment: the course format, the tutoring loop, and the learner's record.

## Conformance

Four classes. Each is claimed and checked independently; one implementation may claim several. A conformance claim names its class and the specification version range it targets — "Conforming Course, Skilling 1.2" — because "Skilling-compatible" on its own is not a claim.

### Conforming Course

A course directory that satisfies [course format](course-format.md). Checkable now:

```bash
uvx skilling validate ./my-course
```

Zero errors means conforming.

### Conforming Runtime

Delivers courses through the [delivery loop](runtime.md#the-delivery-loop): beats in order, gates held open, quiz one question at a time with reasons, remediation offered, completion written idempotently, ceremony at phase boundaries, resume from the record.

Notably, this does not require a language model. A text walker that holds the gates and writes a correct record conforms — which is the point of [scoping conformance to transitions](runtime.md#scope-of-conformance) rather than to prose.

**Since 1.2 a claim also names its [capabilities](runtime.md#capabilities-and-what-may-be-settled)** — `converse`, `observe`, `assess` — because what a runtime can settle about a learner depends on what it can actually see. A runtime with none of them is still conforming; it simply makes no capability claims, which is the truthful thing for it to do.

### Conforming Store

Persists records, completion logs, and homework behind [the store interface](runtime.md#the-store-interface), with optimistic concurrency, append-only guarantees, durability, and atomic completions. One test suite runs unchanged against every backend — that is what makes "a learner's history outlives any one runtime" a fact rather than a hope.

### Conforming Producer

**Since 1.1.** You are one if you embed a runtime in a product and put an interface on it. Four rules:

- **Never create or mutate learner state except through a runtime.** Read records for reporting freely; writing them makes you a second runtime with none of the guarantees, and the record's meaning quietly stops being trustworthy.
- **Never synthesise learner input.** A [gate](runtime.md#gates) unlocks only on input that came from the learner. Not a default, not a timer, not a "continue" your interface clicked on their behalf.
- **Never undo protocol ordering in the interface.** No rendering an unanswered quiz question's answer, no showing question three while question two is open, no displaying key material handed to you in error.
- **Present the telemetry choice honestly.** `null` means ask. No pre-ticked box, no dark-pattern default, and no implying that declining costs the learner something it does not.

These are the rules that let an adopter build whatever interface they like without the record becoming fiction.

## Versioning

The specification carries its own semantic version, independent of any implementation's package version.

| Bump | Means |
|---|---|
| Major | Breaks an existing conforming course, runtime, or store |
| Minor | Additive and optional — new optional fields, new sections binding for the first time |
| Patch | Editorial; no meaning changes |

Courses pin the version they target with `spec_version`; runtimes advertise the range they support.

### What 1.0 deliberately leaves out

Nothing is bound here that no implementation has run. These arrive as minor versions, each once something real has exercised it:

| Surface | Why it waits |
|---|---|
| **Assessed mode** — answer keys held apart from learner-visible content | Needs a runtime that holds keys and a real cohort to be assessed |
| **Runtime API** — the embedding surface a product builds an interface on | Needs a second interface to bind against, or it binds one product's accidents |
| **MCP binding** — delivery into a coding agent over the Model Context Protocol, as an alternative to shelling out to the `skilling` command line | Not the only way to get `observe`: since 1.3, a runtime attests observed evidence through the CLI (`objective settle --evidence observed`, [provenance required](runtime.md#objectives-and-the-record)) with no MCP server involved. An MCP binding would be a second transport for the same capability, not the sole route to it — still needs an actual implementation |
| **Concept-level prerequisites** — `requires: can read a YAML mapping` | Additive; waiting on a tutor that can assess a claim like that |
| **Lesson guidance** — what a tutor should avoid or defer | Additive; the ceremony pattern generalised, and not yet needed by a real course |

Because assessed mode is not yet bound, every course is informal: quiz answers are written inline in the lesson. When `assessment.mode` arrives it will be an optional field defaulting to `informal`, so nothing breaks.

Hooks and telemetry left this table at 1.1, once there was a real adopter with real policy to design against — which is the bar every row above still has to clear.

## Why these constraints exist

This format is not designed from first principles. It generalises one 64-lesson course that ran with real learners, and most of the rules below exist because that course got something wrong first.

| What went wrong | What this specification does about it |
|---|---|
| Lesson counts were hand-maintained in six places and drifted | Structural counts [may not be authored at all](course-format.md#derived-counts) — everything derives from the manifest |
| Badges were declared on eleven lessons and never written to state | `skills_unlocked` [must reach the record](runtime.md#completion) on completion, or the runtime is non-conforming |
| One phase had two lessons numbered 04, two numbered 05, and no 02 or 03 — undetected for months | [Numbering and bijection rules](course-format.md#numbering-and-structure), mechanically checked |
| A learner could answer all three quiz questions wrongly and be congratulated | [Remediation](runtime.md#remediation) is required, with a re-explanation offered on every wrong answer |
| 24 of 64 lessons silently lacked an exercise, so the tutor improvised a different course each time | [Declared absence](course-format.md#declared-absence): absence is fine, undeclared absence is not |
| Answer keys sat inline with learner-visible content, so the course could never be assessed | **Not yet fixed.** Informal delivery keeps answers inline by design; the separation waits for assessed mode |

The last row is deliberate. A specification that claimed to have solved every problem it inherited on the first draft would be lying about the easiest thing to check.

## Reading order

Authors: [course format](course-format.md), then [authoring a course](../docs/authoring-a-course.md).

Runtime implementers: [course format](course-format.md), then [runtime](runtime.md), then [implementing a runtime](../docs/implementing-a-runtime.md).

Store implementers: [the progress record](runtime.md#the-progress-record) through [the file layout](runtime.md#the-file-layout).

Skill pack implementers: [runtime](runtime.md), then [skill pack](skill-pack.md).

Workspace implementers: [the file layout](runtime.md#the-file-layout), then [workspace](workspace.md).

For *why* a constraint is shaped the way it is, see [concepts](../docs/concepts/).

## Changes

Every change, including errata, is recorded in the [CHANGELOG](CHANGELOG.md). The change process, and the rule that error codes are never renumbered or reused, are in [CONTRIBUTING](../CONTRIBUTING.md).
