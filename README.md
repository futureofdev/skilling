# Skilling

**An open format for AI-tutored courses.** Write a course as markdown; any conforming tutor can deliver it, and the learner's record outlives whichever tutor delivered it.

```
my-course/
├── course.yaml
└── phases/
    └── phase-1-basics/
        ├── lesson-01-first-steps.md
        └── lesson-02-going-further.md
```

```bash
uvx skilling validate ./my-course     # is it conforming?
uvx skilling deliver ./my-course      # teach it, no model required
```

## Why

In 1984 Benjamin Bloom showed that one-to-one tutoring beats classroom teaching by two standard deviations, and asked how to deliver that at scale. AI tutors are the first credible answer — but a tutor is only as portable as the course it reads and the record it writes. Skilling standardises exactly those two things and nothing else.

It is not an LMS, not a UI, not a pedagogy, and not tied to any model vendor.

## Where to start

| You want to… | Read |
|---|---|
| Write a course | [spec/course-format.md](spec/course-format.md) — the only page you need |
| Walk through authoring one | [docs/authoring-a-course.md](docs/authoring-a-course.md) |
| Build a tutor | [spec/runtime.md](spec/runtime.md), then [docs/implementing-a-runtime.md](docs/implementing-a-runtime.md) |
| Understand a design decision | [docs/concepts/](docs/concepts/) |
| See the format at real scale | [examples/coding-bootcamp/](examples/coding-bootcamp/) — 9 phases, 64 lessons, deployed portfolio |
| Learn the format in ten minutes | [examples/hello-skilling/](examples/hello-skilling/) — learn Skilling by being taught it |
| Know what conforming means | [spec/README.md#conformance](spec/README.md#conformance) |

## The reference implementation

The `skilling` package is an **LLM-free** core: typed models of the format, a loader, a validator, the delivery state machine as pure functions, and a progress store. Validating a course in CI or loading a manifest in a reporting job must not drag in an agent framework, a model dependency, or an API key.

```bash
uvx skilling validate ./my-course     # conformance check, with error codes
uvx skilling init my-course           # scaffold a conforming skeleton
uvx skilling show ./my-course         # resolved structure and derived counts
uvx skilling deliver ./my-course      # walk the loop; a Conforming Runtime
uvx skilling diff ./v1 ./v2           # classify a version bump
```

`skilling deliver` is a real Conforming Runtime with no language model in it. That is deliberate: if a text walker can conform, then [conformance binds machinery rather than vibes](spec/runtime.md#scope-of-conformance). A model-backed tutor is the next implementation, not the first.

## The golden example

[`examples/coding-bootcamp`](examples/coding-bootcamp/) is a real 64-lesson course — the one this format was generalised from — carried in the repository and validating with zero findings. It exercises every surface: 235 structured objectives, 43 declared absences each with a stated reason, 12 badges, ceremony facts and a share template.

It is deliberately the thing that argues back. Porting it found a validator too strict about Key Terms, a missing ceremony placeholder, and authoring guidance that produced text reading wrong in the first person. A format with no course at this scale behind it has not been tested; a format that never changes when you point one at it has not been listened to.

## Status

Specification **1.0.0-draft**. See [what 1.0 deliberately leaves out](spec/README.md#what-10-deliberately-leaves-out) — assessed mode, hooks, the runtime API, MCP delivery, and skill packs each wait for an implementation to exercise them first.

Known implementations are listed in [docs/implementations.md](docs/implementations.md). A one-row registry is an honest registry; until someone we have never met builds the second row, "standard" is a claim under test.

## Licence

Specification text in [`spec/`](spec/): [CC BY 4.0](spec/LICENSE). Everything else, including the library: [Apache-2.0](LICENSE).

Contributions: [CONTRIBUTING.md](CONTRIBUTING.md).
