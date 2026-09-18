---
name: progress
description: This skill should be used when a learner asks about their progress in an AI-tutored Skilling course — for example "how am I doing", "show my progress", "what's my streak", "what have I completed", or "how far through am I" — either for one named course or as a dashboard across every course they have started. Reads every count, percentage, and streak from the `skilling` command line at the moment it is asked; never estimates or remembers one from an earlier turn.
---

# progress — report a learner's standing

Report exactly what `skilling` says, right now, and nothing you remember from an earlier
turn or infer from the course's shape. Every number here — completed count, lesson count,
percent complete, streak — is derived by `skilling` at read time; there is no authored count
anywhere to fall back on, and stating a stale or guessed one is worse than saying you need to
check.

## What is in this skill

- `references/reading-progress.md` — the two shapes this skill reads (`skilling courses`,
  `skilling progress`), what each field means, and how to render a dashboard from them
  without inventing anything they do not report.

## The two modes

**No course named** — a dashboard across every course the learner has touched. Start in the
current workspace, or the exact `workspace` returned by an earlier `skilling start --json`,
and call bare `skilling courses` (always JSON; see `reading-progress.md`). Omitting `--state`
selects the workspace's state. The result alone is a complete, honest dashboard: id, title,
last activity, ordered. To enrich a row, first use its id directly:
`skilling progress --course <course-id>`. A row's optional `path` confirms that current
workspace content is usable, but do not replace the id with that internal path in ordinary
workspace calls. If an id returns `course-not-found`, only then reuse a still-usable explicit
path or ask for the actual path/ref. Unresolved rows remain title-and-recency only.

**A course is named** — from inside the workspace, call `courses`, match its exact id first
(or a unique title), then call `skilling progress --course <course-id>`. Ask on an ambiguous
title. Only when the workspace id/content is unusable, or there is no enclosing workspace,
fall back to an explicit path already resolved this session or to
`skilling fetch <ref> --json`; use the returned path. Never guess or search the filesystem.

In ordinary workspace use, keep omitting `--state` and use the default learner. If the
session selected an explicit state root, use it for `courses` and pass the same
`--state`/`--learner` to every course-specific detail and telemetry call. Read state only
through CLI envelopes; never inspect or edit `.skilling` records to fill in a missing field.

## Rendering

Build whatever shape suits the conversation — a short sentence, a table, a small bar — but
build it only from fields `reading-progress.md` documents. There is no phase-by-phase
breakdown in either verb's output: `skilling progress` reports the course as a whole, not
phase boundaries, so do not invent a per-phase table from a count you were not given.

## Telemetry, if it comes up

If the learner asks about analytics or opting in/out of usage reporting for a course,
`skilling telemetry ask --course <course>` reads the current answer (`opt_in`:
`null` means never asked) without writing anything; `skilling telemetry on`/`telemetry off`
(same flags) record their choice. This is a per-course setting, not a global one — it is not
otherwise part of a progress report.
