<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/futureofdev/skilling/v0.6.0/brand/assets/github/readme-banner-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/futureofdev/skilling/v0.6.0/brand/assets/github/readme-banner-light.png">
    <img alt="Skilling — learn one-to-one with Claude Code or Codex" src="https://raw.githubusercontent.com/futureofdev/skilling/v0.6.0/brand/assets/github/readme-banner-light.png" width="100%">
  </picture>
</p>

# skilling

Learn through a portable course in **Claude Code or Codex**. The course, durable progress and
your visible work share one folder, independent of the host delivering it.

## Start learning

Install the CLI persistently, verify it, then create the Welcome workspace:

```bash
uv tool install skilling
skilling --version
skilling start 'gh:futureofdev/skilling@v0.6.0#examples/welcome-skilling' my-learning --json
```

Open the returned `workspace` in Claude Code or Codex. Read the generated host instructions,
then use `/learn` in Claude Code or `$learn` in Codex. Reopen the exact folder first if your
already-running host has not discovered its newly installed folder-scoped skills.

You need [Git](https://git-scm.com/downloads),
[uv](https://docs.astral.sh/uv/getting-started/installation/) and one of those two coding hosts.
Skilling has no model dependency; the host supplies the model and its own account and network
requirements.

The pinned example route becomes available once repository tag `v0.6.0` is published. Until
then it documents the release candidate rather than an available public install.

Read the full [learner guide](https://github.com/futureofdev/skilling/blob/v0.6.0/docs/learning-a-course.md),
[course source guide](https://github.com/futureofdev/skilling/blob/v0.6.0/docs/course-sources.md),
or [troubleshooting guide](https://github.com/futureofdev/skilling/blob/v0.6.0/docs/troubleshooting.md).

## For course authors

```bash
skilling init my-course
skilling validate ./my-course --strict
```

The [authoring walkthrough](https://github.com/futureofdev/skilling/blob/v0.6.0/docs/authoring-a-course.md)
covers course identity, writing, strict validation, fresh-workspace preview and publication.

## Library

The package is the LLM-free reference implementation of the
[Skilling course format](https://github.com/futureofdev/skilling/tree/v0.6.0/spec): typed
models, a loader, validator, pure delivery state machine and file-backed progress store.

```python
from pathlib import Path

from skilling import Course, validate_course

report = validate_course("./my-course")
if report.ok:
    course = Course.load(Path("./my-course"))
    print(course.id, course.version)
```

Specification version: **1.4.0-draft**. Package version: **0.6.0**.

Licence: [Apache-2.0](https://github.com/futureofdev/skilling/blob/v0.6.0/LICENSE).
