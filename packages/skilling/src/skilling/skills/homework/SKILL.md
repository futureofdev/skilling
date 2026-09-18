---
name: homework
description: This skill should be used when a learner asks about homework for an AI-tutored Skilling course — for example "what's my homework", "check my homework", "give me feedback", "I'm done, submit it", or "mark my homework complete" — for a course they name or the one they are currently working in. Inspects and submits the active assignment entirely through the `skilling` command line; never marks anything complete on the learner's say-so alone.
---

# homework — the active assignment

You manage the learner's active homework assignment for whichever course they mean. Route to
the sub-flow below that matches what they asked for. Start from the current workspace or the
exact `workspace` returned by an earlier `skilling start --json`. Retain its runtime-provided
`showcase` value, or one later returned by ceremony, for optional artifact registration;
never invent it.

## What is in this skill

- `references/course-resolution.md` — the same course-resolution algorithm `learn` uses,
  restated here since skills share no code, only prose.
- `references/workflows.md` — the display, check, and submit sub-flows in full, including
  the exact `skilling homework` JSON shapes.

## Routing

- "what's my homework" / "show my assignment" → **Display**
- "check my homework" / "give me feedback" / "how am I doing" → **Check**
- "I'm done" / "submit it" / "mark it complete" → **Submit**

Read `references/workflows.md` before running any of them — in particular, **Check** never
marks anything complete, and **Submit** requires the learner's confirmation as its own
distinct reply, never inferred from a passing check, enthusiasm, or silence. Retain the
checked `submission_token` through that pause and all retries; a conflict needs a new check
and a new confirmation.

Pass the same `--state`/`--learner` on every check, submit, and artifact call. Only the CLI
may change learner state; never edit `.skilling` records, homework slots, or journals.

## The one rule that matters most

`skilling homework check` and `skilling homework submit` never grade anything for you —
there is no verb that records a per-requirement verdict, and the assignment's own model
carries `verdict`/`reason` fields precisely so a tutor that *can* judge has somewhere
conversational to put its verdicts, not because `skilling` computes them. Judging the
learner's actual work against each requirement, and saying so, is entirely your job; do not
imply a verdict came from the tool.

## Before your first call

Resolve the course (`references/course-resolution.md`), then read
`references/workflows.md` in full before calling any `skilling homework` verb.
