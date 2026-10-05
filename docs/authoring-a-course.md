# Author a Skilling course

This is the shortest path from an empty directory to a course another person can start from a
stable Git ref. The [course format](../spec/course-format.md) is normative.

## 1. Install and scaffold

Install the same persistent CLI learners use:

```bash
uv tool install skilling
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

Use `skilling show ./my-course --json` for machine-readable lesson estimates and phase/course
sums. Totals add declared `duration_minutes`; missing or unreadable lesson metadata is listed
in `missing_duration_lessons` and makes the displayed estimate incomplete, rather than zero
minutes of learning. These are author estimates, not measured completion times.

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

## 6. Write exercises for a tutor, not a text editor

An Agent Skills host can keep most exercise work inside the tutoring conversation. Write the
exercise around the outcome, the decisions the learner must make, and the evidence that would
show success. Avoid making manual transcription, switching to an editor, or opening another
terminal part of the learning objective when the tutor can perform that mechanical work.

For conceptual work, ask the learner to classify, predict, justify, or critique; let the tutor
turn that reasoning into a durable artifact and show it back for review. For code and command
work, put the important decision before the action, then let the tutor edit, run, and display
the relevant result through the host's permission model. Reserve learner-only steps for things
the host genuinely cannot or must not do, such as entering credentials, authenticating an
account, approving a consequential action, or manipulating physical equipment.

This is delivery guidance, not a new course-format requirement. A plain text runtime still
conforms, and the exercise must remain self-contained even when no model-backed tutor is
available.

## Writing for beginners

Start with a familiar situation and explain why the skill helps before asking a question.
Introduce one idea at a time, show a worked example, then ask the learner to make a small
choice and explain it. A short “last time” recap connects the next lesson to what they
already know. Keep one running analogy across lessons, and say where it stops matching the
real system.

Place a small diagram before a dense explanation. Terminal-friendly ASCII diagrams work in
`text` fences; use a course-relative file under `assets/` when a detailed image is necessary.
Describe the same relationship in words so the lesson still works in a text-only runtime.

```text
learner's choice -> observed result -> explanation -> another try
```

Give exercises a concrete starting point: a worked example to adapt, a prediction to test,
or a few approaches to compare. Teach the needed concepts before requesting output, then
invite the learner to justify their choice and revisit it after feedback. These are editorial
patterns, not required sections or a change to the normative course format.

## 7. Publish a stable source

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
