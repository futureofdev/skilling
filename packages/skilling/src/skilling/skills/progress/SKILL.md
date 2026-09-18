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
and call `skilling courses --state <path>` (always JSON; see `reading-progress.md`). It lists
every course this learner has local state for, most-recently-active first. That alone is a
complete, honest dashboard: id, title, last activity, ordered. Enrich a row with
`skilling progress --course <path> --state <path>` — completed count, percent complete,
streak, skills unlocked — when that row supplies a usable optional `path`, or when you
already resolved its path this session. A missing or stale path means ask for the real path
or ref; do not guess one and do not search the filesystem. Document that unresolved rows may
be title-and-recency only.

**A course is named** — resolve it exactly as `learn` does (name it → `skilling fetch <ref>`;
already resolved this session → reuse the path) and call
`skilling progress --course <path> --state <path>` directly for today's detail. If the name
does not resolve to a path you can call `fetch` on and you have not already resolved it this
session, ask the learner for the path or ref rather than guessing.

Use the same `--state` for `courses` and the same `--state`/`--learner` selection for every
course-specific detail and telemetry call. Read state only through these CLI envelopes;
never inspect or edit `.skilling` records to fill in a missing field.

## Rendering

Build whatever shape suits the conversation — a short sentence, a table, a small bar — but
build it only from fields `reading-progress.md` documents. There is no phase-by-phase
breakdown in either verb's output: `skilling progress` reports the course as a whole, not
phase boundaries, so do not invent a per-phase table from a count you were not given.

## Telemetry, if it comes up

If the learner asks about analytics or opting in/out of usage reporting for a course,
`skilling telemetry ask --course <path> --state <path>` reads the current answer (`opt_in`:
`null` means never asked) without writing anything; `skilling telemetry on`/`telemetry off`
(same flags) record their choice. This is a per-course setting, not a global one — it is not
otherwise part of a progress report.
