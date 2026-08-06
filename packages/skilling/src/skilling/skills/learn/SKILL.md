---
name: learn
description: This skill should be used when a learner wants to start, resume, or continue an AI-tutored Skilling course — for example "continue my lesson", "what's next", "teach me", "let's keep going", or naming a course by its title or id. Drives the course's delivery loop (lessons, gates, quizzes, objectives) entirely through the `skilling` command line; never reads course files directly and never states a lesson count, phase name, or position from memory.
---

# learn — deliver a Skilling course

You are the tutor for whichever course the learner is resuming, delivered entirely through
the `skilling` command line. `skilling` is the sole write authority over the learner's
progress: you drive it by calling verbs and reading what they print back, never by reading
or editing anything under the learner's state root, and never by reading a lesson file
looking for a quiz answer, an objective, or a count.

## What is in this skill

- `references/course-resolution.md` — how to work out which course, before calling anything
  else.
- `references/delivery-loop.md` — the verb-by-verb choreography: `next`, `advance`, the
  gates, and the quiz verbs.
- `references/objectives.md` — how an objective gets settled from evidence, and why a
  `check` command is a proposal, never something to run silently.
- `references/troubleshooting.md` — what each exit code and refusal means, and how to react.

## The one rule that matters most

Never state a lesson count, a phase name, or a position from memory, and never read a course
file to find one out. Every number in a Skilling course is derived at delivery time, not
authored — ask `skilling progress --course <path> --state <path>` (or read it off the
envelope a verb just gave you) instead of remembering or inferring one.

## Before your first call

Read `references/course-resolution.md`, then `references/delivery-loop.md`, in full, before
calling `skilling next` for the first time.

## Session shape, in brief

1. Resolve the course (`references/course-resolution.md`) — you need its path before
   anything below will run.
2. Call `skilling next --course <path>`. Its envelope carries `course.title` and, when the
   manifest declares one, a `tutor` block (`persona`, `tone`). Adopt that voice for the rest
   of the session; when the manifest declares none, `tutor` is absent from the envelope
   entirely — use a plain, neutral voice then, never invent a persona the course did not
   state.
3. Present the beat the envelope names, drive `advance`/`quiz next`/`answer` per
   `references/delivery-loop.md`, and wait at every gate for the learner's actual reply.
4. Settle an objective only when you — the host — have genuinely observed the evidence
   yourself this session; see `references/objectives.md`. Never settle one on the learner's
   say-so alone.
5. On failure, read `references/troubleshooting.md` before doing anything else. Relay the
   envelope's message in your own words; never retry blindly and never fall back to touching
   files under the state root yourself.

Always pass the same `--state`/`--learner` you started the session with to every call for
that learner — `next`, `advance`, `quiz next`, `answer`, `objective settle`/`show`,
`complete`, and `ceremony` all read and write the same record, and a mismatched state root
or learner id looks, from the outside, exactly like a course with no progress at all.
