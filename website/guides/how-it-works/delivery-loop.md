---
title: The delivery loop
description: How a lesson file becomes a tutoring conversation.
---

# The delivery loop

Every tutor that follows the Skilling format walks each lesson through the same steps, called
*beats*:

| Section in the lesson | Beat |
|---|---|
| (none) | welcome |
| `## Learning Objectives` | objectives |
| `## The Concept`, `## Key Terms` | concept |
| `## Hands-On Exercise` | exercise |
| `## Quick Quiz` | quiz |
| `## Next Up` | completion |

At each gate the tutor waits for a real reply from the learner. It never answers on the
learner's behalf to move things along.

## What's fixed and what isn't

The loop fixes *when* things happen. It says nothing about *how* the tutor talks. Persona,
warmth, analogies and how a second explanation differs from the first are all left to the
course's `tutor` settings and to the tutor itself.

That's deliberate. Nobody can require a language model to teach well. What the format can
require is that the machinery around it is correct: lessons happen in order, gates wait,
answers aren't revealed early, and progress is saved properly. That's what conformance checks.

## Mechanism without a model

The `skilling` package contains no language model. Claude Code or Codex supplies the
conversation, and the CLI handles the loop and the record. The package even includes
`skilling deliver`, a plain-text tutor with no model at all that still passes the runtime
checks. If a plain text walker can conform, conformance is clearly about the machinery, not
about how well a model teaches.

## Where it falls short

A fixed shape won't suit every subject. A course that wants five reading sections and no quiz
can't be a Skilling course. The format trades authoring flexibility for courses that any tutor
can teach.

Read the [design rationale](https://github.com/futureofdev/skilling/blob/main/docs/concepts/the-delivery-loop.md)
or the [runtime specification](/spec/runtime#the-delivery-loop).
