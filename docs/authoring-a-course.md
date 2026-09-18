# Author a Skilling course

This is the shortest path from an empty directory to a course another person can start from a
stable Git ref. The [course format](../spec/course-format.md) is normative.

## 1. Install and scaffold

Install the same persistent CLI learners use:

```bash
uv tool install 'skilling==0.5.0'
skilling init my-course
```

The scaffold includes `course.yaml`, one phase, lesson files and an overview. Add a `README.md`
for learners that says what the course teaches, who it is for, its prerequisites, how to
start it and where to get help. Include a licence appropriate for the content and assets.

## 2. Establish identity and prerequisites

Choose a stable lowercase `id` and semantic `version` in `course.yaml`. The id becomes part of
the durable learner record and showcase path, so do not rename it casually. Describe actual
prerequisites before the learner starts; a tutor cannot repair a missing operating system tool
by pretending it exists.

Version changes preserve learner coordinates:

| Change | Minimum bump |
|---|---|
| Wording, examples or corrections | Patch |
| Append lessons to a phase, or add trailing phases | Minor |
| Move, remove or renumber existing coordinates | Major |

Use `skilling diff OLD NEW --strict` before publishing an update.

## 3. Write structure first

Declare phases and lessons in `course.yaml`; do not duplicate counts in prose. Each lesson
file lives at its derived phase/lesson path. Record whether optional key terms, exercise and
next-up sections are present or deliberately absent.

Write the concept before the quiz. Every quiz has exactly three questions, four options and an
answer that explains why. Use structured knowledge objectives for what a learner can explain
and practice objectives for something observable they do. A `verify` clause is appropriate
only when a runtime can genuinely check the outcome.

The compact [hello-skilling](../examples/hello-skilling/) course is useful for learning the
format. [workbench](../examples/workbench/) demonstrates the full authoring surface.

## 4. Validate strictly

```bash
skilling validate ./my-course --strict
skilling show ./my-course
```

Remote acquisition refuses warnings as well as errors, so `--strict` is the publication gate.
Follow each finding's specification anchor. Keep the strict command in CI.

## 5. Preview as a learner

Do not review only the source files. Start a fresh workspace, separate from the course checkout:

```bash
skilling start ./my-course my-course-preview --json
```

Open the returned workspace in Claude Code or Codex, invoke `/learn` or `$learn`, and walk the
course with genuine answers. Check the first-run explanation, waits, remediation, learner work,
homework review and separate submission confirmation. A mechanical CLI walk checks structure;
it is not a substitute for editorial review.

## 6. Publish a stable source

Commit the course to a Git repository. A course may live at the repository root or, on GitHub,
in a subdirectory. Tag the reviewed commit and test the exact learner command in a clean
workspace:

```bash
skilling start 'gh:owner/repository@v1.0.0#courses/my-course' clean-preview --json
```

Omit `#courses/my-course` when the course is at the repository root. You may use a full commit
instead of a tag. Publish the tested command in the course README; do not advertise a moving
branch as immutable or a direct ZIP URL as a supported source.

See [Course sources](course-sources.md) for authentication, supported transports, cache
identity and update behaviour.
