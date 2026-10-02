---
title: Your first course
description: Go from an empty folder to a course you can take yourself.
---

# Your first course

A Skilling course is a folder of markdown files plus one `course.yaml`. You don't need an
account or a platform. Anyone with Claude Code or Codex can take it, and so can any other
tutor that follows the format.

## Scaffold it

Install the same CLI that learners use, then make a skeleton:

```bash
uv tool install skilling
skilling init my-course
```

You get a small course that already passes validation:

```text
my-course/
├── course.yaml
└── phases/
    └── phase-1-basics/
        ├── overview.md
        ├── lesson-01-first-steps.md
        └── lesson-02-going-further.md
```

## Fill in `course.yaml`

The manifest says what the course is and how it's laid out:

```yaml
spec_version: "1.4"
id: my-course
title: My Course
version: "0.1.0"
description: What a learner will be able to do by the end.
language: en
license: CC-BY-4.0
tutor:
  persona: >
    A calm guide who explains one idea at a time and checks in before moving on.
phases:
  - number: 1
    slug: basics
    name: Basics
    lessons:
      - { number: 1, slug: first-steps, title: First Steps }
      - { number: 2, slug: going-further, title: Going Further }
```

A few things to get right early:

- **Pick a stable `id`.** It ends up in every learner's progress record and showcase folder,
  so don't rename it later.
- **Keep counts out of your prose.** Don't write "this course has 12 lessons". Skilling works
  counts out from the manifest, so they can never go stale.
- **Say what learners need first.** If the course assumes Node or Git, say so in the
  description and README. A tutor can't install a tool by pretending it's there.

## Write the lessons

Each lesson file has a fixed set of sections in a fixed order. That's what lets any tutor teach
it without guessing. [Anatomy of a lesson](lesson-anatomy) walks through it.

## Check it, then take it

```bash
skilling validate ./my-course --strict
skilling start ./my-course my-course-preview --json
```

Open the preview folder in Claude Code or Codex and type `/learn` or `$learn`. Answer the
questions for real, get one wrong on purpose, and try the homework. Being taught your own
course shows you things that rereading it won't.

The [Hello, Skilling](https://github.com/futureofdev/skilling/tree/main/examples/hello-skilling)
course is a small, complete example to copy from.
