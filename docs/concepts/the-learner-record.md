# The learner record

*Why the record owes nothing to the conversation that produced it, and why it stores as little as possible.*

Normative home: [runtime § the progress record](../../spec/runtime.md#the-progress-record).

## Two rules, one purpose

The record has two unusual constraints, and both exist so that a learner's history outlives the thing that created it:

1. **No transcript is ever required.** The record and completion log must be fully reconstructible without any message history.
2. **Nothing derivable is stored.** Counts, percentages, phase boundaries, "lesson 3 of 9" — all computed from the manifest plus `completed`.

## Why transcripts are excluded

If progress lived inside a chat log, then changing tutor would mean losing everything. Switch model, switch product, switch employer: your history was a side effect of a conversation, and the conversation is gone.

So the record is deliberately thin and deliberately boring — coordinates, dates, a streak, a badge set. A transcript is a runtime's convenience, not part of what is true about a learner.

This is also what makes the [store interface](../../spec/runtime.md#the-store-interface) implementable by someone who knows nothing about tutoring. A store persists a small YAML document. It does not need to understand a conversation, and it is explicitly forbidden from interpreting one.

## Why counts are not stored

Because they drift. Not might — do.

The course this format generalises maintained its lesson counts in six separate places: the manifest, the delivery skill, a progress file, two phase overviews, and the marketing copy. By the time anyone checked, no two agreed, and the learner-facing one was wrong.

Every one of those numbers was derivable. Each was written down anyway, because writing it down was easier than computing it, once. That is how a second source of truth is born, and a second source of truth is a bug with a delay on it.

So the format forbids authoring counts [in a course](../../spec/course-format.md#derived-counts) and forbids storing them in a record. `skilling show` prints them under a heading that says *never authored*, because the useful thing to know about a count is where it came from.

The same logic covers phase completion. A phase is complete when its lessons are in `completed` — computed, not stamped. A `phases_completed` field would be exactly the drift the rest of the design refuses.

## The log is the truth

Alongside the record sits an append-only completion log: one entry per completion, never rewritten, never reordered.

The record's `completed` set must be reconstructible from the log alone, and **where they disagree, the log wins.** This gives the record a cheap, current, disposable quality — if it is ever corrupted, it can be rebuilt.

It also gives an adopter something auditable that a mutable summary never can. "When did this learner finish that lesson, and against which version of the course?" is answerable from the log, permanently, without trusting whatever wrote the record last.

Ceremony and artifact defaults follow the completion log's append order. The completed array
is a set, and timestamps do not determine sequence. Imported records without a log can use
a sole completed coordinate; otherwise pass `ceremony --coordinate 1.2` or
`artifact add PATH --title TITLE --coordinate 1.2` for a known completed lesson. Ceremony
requires a phase endpoint. Both commands refuse malformed or conflicting history even with
an override, without repairing it or creating a new record. Completion retries continue to
use their durable receipt rather than these presentation defaults.

## Streaks are counted in local days

The streak is defined in the record's own timezone, not the server's. A learner in Auckland finishing at 11pm has finished today, and a runtime that counted in UTC would break their streak while they were looking at it. Small thing; the sort of small thing that makes people stop.

## Limits

A thin record cannot answer questions it does not store: how long a learner spent, which explanations they needed, where they struggled. Some of that is worth knowing, and all of it is an adopter's business — build it beside the record, on hooks and logs, not inside it. The moment the record grows fields a tutor must maintain, it stops being portable.

Nor does the record authenticate anyone. `learner_id` is opaque: whoever embeds the runtime assigns it and is responsible for what it means.

## See also

[Mechanism and policy](mechanism-and-policy.md) · [The homework mailbox](the-homework-mailbox.md)
