---
title: Implementations and status
description: Who has built Skilling tooling so far, and how mature the format is.
---

# Implementations and status

Skilling is an open format with a public specification, and it's young.

- **The specification is a draft.** It's versioned, and changes are recorded in the
  [changelog](/spec/CHANGELOG).
- **Conformance is self-certified.** Implementations check themselves against public
  checklists. There's no certification body.
- **Independent implementations: 0.** Every implementation so far was built by the same team.
  Until someone else builds one, "standard" is a claim under test.

## What exists today

The `skilling` Python package is the reference implementation. It includes the validator, the
loader, the delivery state machine, the progress store, the learner CLI, and the skill pack that
Claude Code and Codex use. It has no language model, agent framework or API key in it.

The full list, with exactly what each one claims and what it doesn't, is in the
[implementations registry](https://github.com/futureofdev/skilling/blob/main/docs/implementations.md).

## Build another one

A second implementation from someone we've never met would help the project more than anything
else. Start with the [specification](/spec) and the
[implementation guide](https://github.com/futureofdev/skilling/blob/main/docs/implementing-a-runtime.md).
If you find spec wording that reads two ways, that's worth reporting too, so please
[open an issue](https://github.com/futureofdev/skilling/issues).
