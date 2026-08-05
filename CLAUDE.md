# Skilling

An open format for AI-tutored courses: what authors write, what a tutor does, what is durably
true about a learner afterwards. Monorepo: normative spec (`spec/`), explanatory docs
(`docs/`), generated schemas (`schemas/`), LLM-free reference implementation
(`packages/skilling/`), example courses (`examples/`). Start at `llms.txt` for the full map.

## Commands

- `task check` — everything CI runs: lint, typecheck, tests, freshness checks, example validation
- `task fix` — ruff format + autofix
- `task schemas && task docs` — regenerate `schemas/` and `docs/error-codes.md` after model edits
- `task test -- -k <expr>` — a subset of the suite

`task check` must pass before any commit. No exceptions. If `task` is not on PATH, every task
is a one-line `uv run` wrapper — read `Taskfile.yml` and run those directly.

## Authority

- Normative text lives only in `spec/`. When `docs/`, `README.md`, code, or a schema disagrees
  with `spec/`, the spec wins and the other artifact has the bug.
- `schemas/` and `docs/error-codes.md` are generated from the Pydantic models. They look
  normative but are derived — never hand-edit; regenerate and commit (freshness is checked).
- The spec version is declared once, in `spec/README.md`. `README.md` and `llms.txt` repeat it;
  a test in `test_docs.py` keeps all three honest. Bump them together.

## Gotchas

- Error codes are immutable. Never rename, renumber, or reuse a published code — retire it and
  add a new one (`CONTRIBUTING.md`).
- A change to what authors write is one PR: spec text + validator + fixture + error code +
  CHANGELOG entry, plus `examples/hello-skilling` if affected.
- Nothing binds before an implementation has run it. Unexercised surfaces ship as documented
  gaps, never as normative text.
- `examples/coding-bootcamp` is the golden example and validates with zero findings. When it
  and the validator disagree, suspect the validator first — the format was generalised from
  this course, and it is supposed to argue back.
- `packages/skilling` stays LLM-free: no model, agent-framework, or API-key dependency, ever.
  New runtime deps must earn their place; tooling goes in dependency groups.

## Ways of working

- Thematic PRs: every change is a branch off `main` and a PR with exactly one theme, reviewed
  by the maintainer before merge. Unrelated fixes discovered en route become their own PR.
- Research the current idiom before adopting any new library, pattern, or convention — fetch
  live docs; training-data memory goes stale.

## Keeping this file current

A living contract, not an archive. When a new concept or subsystem lands, add a targeted one-
or two-line entry; prune anything tooling now enforces. For each line ask: would removing it
cause a mistake? Hard budget: 60 lines — to add, first cut.
