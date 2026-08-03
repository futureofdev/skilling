# Skilling v1 — design of record

**Date:** 2026-08-03 · **Status:** accepted, implemented in this repository

## Problem

A working draft of the Skilling specification existed as strategy material: twelve documents in a heavy standards register — RFC-2119 capitals, per-rule identifiers (`MAN-004`, `DEL-012`), four conformance classes — plus an eighteen-page concepts tier and an eight-phase roadmap. No code. Several documents bound surfaces that no implementation had ever run.

That draft did its job: the thinking is sound and the provenance is real, generalised from a 64-lesson course that ran with actual learners. But it was not something a course author would read, and nothing in it was checkable.

This repository is v1: a specification light enough to be read in one sitting, plus the reference library that makes it enforceable.

## Decisions

### The specification

**Author fresh, in a light register.** The working draft became reference material rather than source. Prose "must", field tables, good/poor examples — the register of a format specification people actually use, not a standards-body document. Per-rule identifiers are gone.

**Two pages, split by audience.** `spec/course-format.md` is everything a course author writes; `spec/runtime.md` is everything a tutor implementer must do. An author reads one page and is finished. Implementers read both.

**Stable identifiers moved to error codes.** The draft's rule IDs existed so findings could be cited. Findings come from a validator, so the validator owns the identifiers — kebab-case error codes, immutable, each pointing at a specification anchor. Identifiers now live where they are used and version with the tool that emits them.

**Three conformance classes: Course, Runtime, Store.** Store stays separate because the promise that a learner's history outlives any one runtime is only real if a store is independently implementable and independently testable. The draft's fourth class, Producer, waits for 1.1 — its requirements live in hooks and telemetry, which v1 does not bind.

**v1 binds seven surfaces and no more:** course format, lesson format, delivery loop, progress record, homework, storage, conformance. Assessed mode, hooks and telemetry, the runtime API, the MCP binding, and skill packs are documented gaps. A specification should not bind a surface no implementation has run, and saying so in public is cheaper than a major version later.

Two consequences worth recording:

- **There is no `assessment` block in the v1 manifest at all.** The draft made `assessment.mode` a required field with two values. With assessed mode deferred, the field does not exist; every 1.0 course is informal. At 1.1 it arrives optional, defaulting to `informal`, so nothing breaks.
- **`runtime.md` opens with its scope-of-conformance statement** — it binds observable transitions and record writes, never prose. Without that, the next decision is incoherent.

**One inherited defect is documented as unfixed.** Of the six defects the source course had, five are retired by 1.0 rules. The sixth — answer keys sitting inline with learner-visible content — is not, because informal delivery keeps answers inline by design and the separation needs assessed mode. Saying so in the specification is the honesty discipline working.

### The reference implementation

**Python, uv workspace, Pydantic.** The next implementation after this one is a model-backed tutor on Pydantic AI. Same language means the delivery state machine is written once and the tutor binds tools directly onto it, rather than reimplementing the loop across a process boundary.

**The core is LLM-free.** Validating a course in CI, loading a manifest in a reporting job, or building an authoring tool must not drag in an agent framework or an API key. The core is parse, validate, transition, persist.

**`skilling deliver` claims Conforming Runtime.** It walks the real loop, holds real gates on real input, grades the quiz mechanically from the inline answer lines, re-presents the concept on remediation, and writes a real record through the file store. It re-prints rather than re-explains, and it cannot judge homework — so the specification is written such that neither is required to conform, and a runtime that *does* offer homework checking has extra duties rather than the baseline having fewer.

This is the load-bearing test of the whole design. If a text walker with no model can conform, then conformance binds machinery. If it could not, the specification would be asserting things about prose that no suite could ever check.

**Homework is mailbox mechanics only.** Slot, queue-behind, submit-with-its-own-confirmation, append-only archive, idempotence — all mechanical, all in the core. Per-requirement judgement is a documented runtime duty and explicitly optional.

**JSON Schemas are generated and non-normative.** `task schemas` emits them from the Pydantic models for editor autocomplete. Prose stays the only normative source; hand-authored normative schemas would be a second text to keep from drifting, and generated normative schemas would quietly make the implementation the specification.

**Conformance fixtures are test-internal.** One clean course plus one minimally-corrupted variant per error code, under `packages/skilling/tests/fixtures/`. A published cross-language conformance suite is worth building when a second implementation exists to run it, and not before.

### Included because authoring fresh made them free

Three improvements the working draft had deferred to future minor versions cost nothing at v1 and would each have been a breaking or awkward addition later:

- A manifest `license` field, SPDX-checked. Private courses need to say so; open ones need to be reusable.
- An `assets/` convention with relative-only references and dangling-reference checks. Real courses carry diagrams.
- Course-version semantics with teeth: patch is content-only, minor is additive and coordinate-stable, major is anything that moves or renumbers — plus `skilling diff` to check coordinate stability mechanically. A version number that makes a checkable promise is worth having before the first course churns versions, not after.

## What this repository is not doing

- **The zero-to-portfolio port.** The 64-lesson course that this format generalises is the acceptance test, and it lands as its own project with its own implementation spec. Porting real content while the specification is still moving would fossilise the source system's accidents — which is the exact failure this whole exercise exists to avoid.
- **A model-backed tutor.** Next, on Pydantic AI, against this core's public surface. If it needs a private hook, the core's design is wrong.
- **A published site.** The specification is written so a static site generator can be pointed at `spec/` without restructuring. `llms.txt` ships now because it is cheap and agents are a real audience.

## Verification

The specification is proven by the library; the library is proven by its gates. Every error code fires on its own fixture and the clean fixture produces nothing. Every YAML example in the specification round-trips through the models. Every transition in the loop diagram is table-tested, and illegal transitions are rejected. The store suite runs against the protocol rather than the backend, so the eventual database backend costs nothing to test.

The gate that matters most is not automated: hand `spec/course-format.md` alone to a reader with no other context and ask for a conforming course. Anywhere they guess, the page is ambiguous — and the fix is the page, not the course.
