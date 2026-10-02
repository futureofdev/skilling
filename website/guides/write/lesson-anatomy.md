---
title: Anatomy of a lesson
description: The frontmatter and the fixed sections every lesson uses.
---

# Anatomy of a lesson

A lesson is one markdown file: some YAML frontmatter, then a set of sections with exact
headings, always in the same order.

Why so strict? The tutor teaching your course has never seen it before and can't ask you what
you meant. Because every lesson has the same shape, it always knows where the concept, the
exercise and the quiz are.

## Frontmatter

```yaml
---
title: First Steps
phase: 1
lesson: 1
duration_minutes: 15
prerequisites: []
skills_unlocked: []
sections:
  key_terms: present
  exercise: present
  next_up: present
---
```

`title`, `phase` and `lesson` must match the manifest. The validator compares them, so a lesson
that gets renumbered in one place but not the other fails straight away instead of being taught
as the wrong lesson.

## The sections

| Heading | When |
|---|---|
| `## Learning Objectives` | Required, unless you use [structured objectives](objectives-quizzes-homework#objectives) |
| `## The Concept` | Required |
| `## Key Terms` | Optional |
| `## Hands-On Exercise` | Optional |
| `## Quick Quiz` | Required |
| `## Homework Assignment` | Only when the manifest says `homework: true` |
| `## Next Up` | Optional |

Use `###` subheadings freely inside a section. You can't add new `##` sections or change the
order.

## Say when something is missing on purpose

Every optional section has to be declared in `sections`, either as present or as absent with a
reason:

```yaml
sections:
  key_terms: present
  exercise:
    status: none
    intent: "Project phase: the learner's own build is the exercise."
  next_up: present
```

Leaving a section out is fine. Leaving it out *silently* isn't, because then nobody can tell a
decision from an oversight. A tutor that finds no exercise and no explanation might improvise
one, and then every learner gets a different course.

## Write the concept to be taught twice

The tutor goes back to `## The Concept` when a learner asks to go deeper or gets a question
wrong. A thin concept section can only be taught once. Give it a concrete example, and enough
substance that a second explanation can come at it from a different angle.

## Write exercises for a tutor

The tutor can do the typing, so write exercises around decisions. Ask the learner to classify,
predict, justify or critique something, and let the tutor turn that into a file or a command.
Save learner-only steps for things the assistant can't or mustn't do, such as entering a
password or approving something important.

The complete rules are in the [course format specification](/spec/course-format#lesson-files).
