---
title: Validate and fix findings
description: Use the validator locally and in CI, and read its findings.
---

# Validate and fix findings

```bash
skilling validate ./my-course --strict
skilling show ./my-course
```

`validate` checks your course against the format and reports each problem with a stable error
code and a link to the rule behind it. `show` prints the structure Skilling sees, including the
counts it works out for you.

## Why `--strict`

Without `--strict`, warnings are reported but don't fail. Learners fetching your course from
Git get the strict check, though: Skilling refuses to start a remote course with warnings or
errors. So treat `--strict` as your publishing gate.

## Keep it in CI

Error codes never change meaning once published. A retired code is retired, never reused, so
it's safe to build CI around them. A minimal GitHub Actions step:

```yaml
- uses: astral-sh/setup-uv@v9
- run: uvx skilling validate . --strict
```

## Before you publish an update

Compare the old and new versions so you pick the right version bump:

```bash
skilling diff ./old ./new --strict
```

| Change | Bump |
|---|---|
| Wording, examples or corrections | Patch |
| New lessons at the end of a phase, or new phases at the end | Minor |
| Moving, removing or renumbering lessons | Major |

Learners on an older version keep their progress through patch and minor updates. A major
version can't carry progress across automatically.

Every code is listed in the
[error code catalogue](https://github.com/futureofdev/skilling/blob/main/docs/error-codes.md).
