# The Skilling specification

**Version 1.0.1-draft** · Specification text licensed [CC BY 4.0](LICENSE)

> The patch level is editorial. Courses declare `spec_version` as `"major.minor"`, so a
> `"1.0"` course is unaffected by anything in 1.0.1 — the text says more, and requires
> nothing new.

Skilling is an open format for AI-tutored, skill-based courses. It specifies three things precisely enough that independent implementations interoperate:

- **What authors write** — a course directory: one manifest, markdown lessons with a fixed anatomy → [course format](course-format.md)
- **What a tutor does** — the delivery loop, its gates, and what it writes → [runtime](runtime.md)
- **What is durably true afterwards** — the learner's record, and the store behind it → [runtime](runtime.md#the-progress-record)

In 1984 Benjamin Bloom showed that students taught one-to-one outperform classroom students by two standard deviations, and asked how to deliver that at scale. AI tutors are the first credible answer. Skilling standardises the part that must not fragment: the course format, the tutoring loop, and the learner's record.

## Conformance

Three classes. Each is claimed and checked independently; one implementation may claim several. A conformance claim names its class and the specification version range it targets — "Conforming Course, Skilling 1.0" — because "Skilling-compatible" on its own is not a claim.

### Conforming Course

A course directory that satisfies [course format](course-format.md). Checkable now:

```bash
uvx skilling validate ./my-course
```

Zero errors means conforming.

### Conforming Runtime

Delivers courses through the [delivery loop](runtime.md#the-delivery-loop): beats in order, gates held open, quiz one question at a time with reasons, remediation offered, completion written idempotently, ceremony at phase boundaries, resume from the record.

Notably, this does not require a language model. A text walker that holds the gates and writes a correct record conforms — which is the point of [scoping conformance to transitions](runtime.md#scope-of-conformance) rather than to prose.

### Conforming Store

Persists records, completion logs, and homework behind [the store interface](runtime.md#the-store-interface), with optimistic concurrency, append-only guarantees, durability, and atomic completions. One test suite runs unchanged against every backend — that is what makes "a learner's history outlives any one runtime" a fact rather than a hope.

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
| **Hooks and telemetry** — the extension points an adopter attaches policy to | Needs an adopter with policy to attach |
| **Runtime API** — the embedding surface a product builds an interface on | Needs a second interface to bind against, or it binds one product's accidents |
| **MCP binding** — delivery into a coding agent for hands-on courses | Needs the statefulness questions answered by running code |
| **Skill packs** — a course compiled to Agent-Skills format | Needs the generator |

Because assessed mode is not yet bound, every 1.0 course is informal: quiz answers are written inline in the lesson. When `assessment.mode` arrives it will be an optional field defaulting to `informal`, so no 1.0 course breaks.

## Why these constraints exist

This format is not designed from first principles. It generalises one 64-lesson course that ran with real learners, and most of the rules below exist because that course got something wrong first.

| What went wrong | What this specification does about it |
|---|---|
| Lesson counts were hand-maintained in six places and drifted | Structural counts [may not be authored at all](course-format.md#derived-counts) — everything derives from the manifest |
| Badges were declared on eleven lessons and never written to state | `skills_unlocked` [must reach the record](runtime.md#completion) on completion, or the runtime is non-conforming |
| One phase had two lessons numbered 04, two numbered 05, and no 02 or 03 — undetected for months | [Numbering and bijection rules](course-format.md#numbering-and-structure), mechanically checked |
| A learner could answer all three quiz questions wrongly and be congratulated | [Remediation](runtime.md#remediation) is required, with a re-explanation offered on every wrong answer |
| 24 of 64 lessons silently lacked an exercise, so the tutor improvised a different course each time | [Declared absence](course-format.md#declared-absence): absence is fine, undeclared absence is not |
| Answer keys sat inline with learner-visible content, so the course could never be assessed | **Not yet fixed.** Informal delivery keeps answers inline by design; the separation arrives with assessed mode at 1.1 |

The last row is deliberate. A specification that claimed to have solved every problem it inherited on the first draft would be lying about the easiest thing to check.

## Reading order

Authors: [course format](course-format.md), then [authoring a course](../docs/authoring-a-course.md).

Runtime implementers: [course format](course-format.md), then [runtime](runtime.md), then [implementing a runtime](../docs/implementing-a-runtime.md).

Store implementers: [the progress record](runtime.md#the-progress-record) through [the file layout](runtime.md#the-file-layout).

For *why* a constraint is shaped the way it is, see [concepts](../docs/concepts/).

## Changes

Every change, including errata, is recorded in the [CHANGELOG](CHANGELOG.md). The change process, and the rule that error codes are never renumbered or reused, are in [CONTRIBUTING](../CONTRIBUTING.md).
