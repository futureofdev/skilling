# Implementations

Known Skilling implementations and their conformance claims. Claims follow [conformance](../spec/README.md#conformance): a class, a specification version range, self-certified against the public checklists.

## Registry

| Implementation | Classes | Specification | Status |
|---|---|---|---|
| [`workbench`](../examples/workbench/) — every authoring surface, compact | Conforming Course | 1.3 | shipped |
| [`hello-skilling`](../examples/hello-skilling/) — 3 lessons | Conforming Course | 1.2 | shipped |
| [`skilling`](../packages/skilling/) — models, loader, validator | Course tooling | 1.2 | shipped |
| [`skilling deliver`](../packages/skilling/src/skilling/cli/learning/_walk.py) | Conforming Runtime (no capabilities), Conforming Producer | 1.2 | shipped |
| [`skilling.store.FileProgressStore`](../packages/skilling/src/skilling/store/_file.py) | Conforming Store | 1.2 | shipped |
| [The bundled `learn`/`progress`/`homework` triad](../packages/skilling/src/skilling/skills/), delivered by a stock host | Conforming Runtime (converse, observe) | 1.3 | delivery spot-checked; full proof pending |
| Skilling tutor on Pydantic AI | Conforming Runtime (converse, assess) | 1.2 | planned |
| Skilling in a coding harness, over MCP | Conforming Runtime (converse, observe, assess) | 1.2 | specified for, not built |
| *your implementation here* | | | [CONTRIBUTING](../CONTRIBUTING.md) |

A registry where every row is the same author is an honest registry, not an impressive one. Until someone we have never met builds a row, "standard" is a claim under test rather than a fact.

The triad row's capabilities describe what an unmodified Claude Code or Codex session brings on its own — a conversation to judge a `knowledge` objective's explanation (`converse`), and filesystem or command-output access to check a `practice` objective's `verify` sentence (`observe`) — not something the [skill pack](../spec/skill-pack.md) itself adds. The maintainer has directly driven both a real Codex session and a real Claude Code session through `hello-skilling`/`coding-bootcamp` lessons and confirmed the delivery loop behaves correctly (gates, quiz custody, phase-boundary homework) — the `converse` half of this claim. The `observe` half — a host actually settling a `practice` objective from a real filesystem check, with provenance recorded — was not exercised in that pass, nor were the private-repo or offline gates. See [`docs/two-host-proof.md`](two-host-proof.md) for exactly what ran and what's deferred; this row moves to "shipped" only once all five of that document's falsifiability criteria have run with committed artifacts, not before.

`skilling deliver` also claims [Conforming Producer](../spec/README.md#conforming-producer), since it is the interface as well as the runtime: it writes learner state only through the runtime, never synthesises input to unlock a gate, never renders an answer before it is earned, and asks about telemetry with the decline as the default. Claiming the class matters because it means the class is exercised rather than merely described.

## Completion recovery and current limits

The current source adds the required completion backend interface in the 1.4.0 draft:
`get_completion_receipt` and `commit_completion`, with the public completion value types in
`skilling.store`. Third-party stores implementing only the previous interface must add these
operations; `complete_lesson` refuses with `NotSupported` before completion effects when they
are missing. Plugin discovery does not establish compatibility, and no legacy fallback
claims the new guarantee. This change does not promote the registry's historical version
claims or publish a new package release.

The file backend records a portable prepared completion intent before effects, then writes
log, final record, optional homework and completion scratch reset under one course lock.
Cooperating reads and writes recover pending intent first. Retry preserves original times,
phase badges and assignment identity while returning the current record/revision; it does
not restore an obsolete record over later acknowledged changes. Newly committed completion
hooks fire after durability; recovery and replay suppress hooks, so a crash can omit external
events.

The scope is newly journaled completion on a local filesystem used by cooperating processes.
Retain `completion.yaml` when relocating state after writers stop. Existing record/log/homework
formats remain portable; old duplicate history is not removed and missing historical
assignments are not inferred. Corrupt metadata or unexpected bytes require inspection, not
automatic guessed repair. Process termination and filesystem flushes are the supported
verification boundary, not a physical power-loss or network-filesystem claim.

Two known gaps remain outside completion recovery: [interrupted confirmed submission
(#63)](https://github.com/futureofdev/skilling/issues/63) can archive twice before resetting its
slot, and [interrupted general `advance`
(#64)](https://github.com/futureofdev/skilling/issues/64) can commit a record without its
scratch/idempotency result, allowing the same key to advance again.
The completion-related scratch revision guard does not make all transitions transactional.
Full Windows delivery/timezone support remains [#2](https://github.com/futureofdev/skilling/issues/2);
source/cache/import recovery and generic chronology remain #56–#59. Retained host proof and
release readiness are separate from these storage changes. See the
[runtime implementation guide](implementing-a-runtime.md#recovery-scope-and-legacy-state)
for backend and legacy-state handling.

## Why the reference runtime has no language model in it

`skilling deliver` walks the loop, holds the gates on real input, grades the quiz from the lesson's inline answer lines, re-presents the concept on a wrong answer, and writes a correct record. It re-*prints* rather than re-*explains*, and it cannot judge homework.

It conforms anyway, and that is the entire point.

If a text walker can be a Conforming Runtime, then conformance binds machinery — transitions, ordering, record writes — and not prose. If it could *not*, the specification would be asserting things about teaching quality that no test suite could ever check, and "conforming" would mean whatever the person claiming it wanted it to mean.

So the first runtime is deliberately the dullest possible one. A model-backed tutor is the second.

## Architecture of the reference implementation

Two layers, deliberately unequal.

```
skilling (core) — no model dependency
├── models      typed models of every YAML surface
├── lesson      markdown parsing: sections, quiz, homework
├── loader      course directory → resolved course, everything derived
├── validate    the checks, as coded findings
├── machine     the delivery loop as pure functions
├── runtime     the completion write set
├── diff        course-version comparison
└── store       protocol + file backend

skilling tutor (planned) — Pydantic AI
├── agent       persona, narration, re-explanation
├── tools       bound to machine's legal transitions
└── grader      per-requirement homework verdicts
```

The split is load-bearing. Validating a course in CI, loading a manifest in a reporting job, or building an authoring tool must not drag in an agent framework, a model dependency, or an API key. The core is parse, validate, transition, persist — the layer everything else can afford to depend on.

The tutor adds exactly one thing: a language model wired to the core's public surface. If it turns out to need a private hook into the core, the core's design is wrong and the core changes.

## Registering an implementation

Open a pull request adding a row. Name your class or classes, the specification range you target, and where the code is. Nothing is audited — the checklists are public and the claim is yours to make and yours to be wrong about.

What will get a row rejected is an implementation that breaks one of the two boundaries in [implementing a runtime](implementing-a-runtime.md#claiming-conformance): a catalogue grown inside the runtime, or learner state written around it.
