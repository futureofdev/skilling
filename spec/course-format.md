# Course format

> The complete format specification for a Skilling course. This is the only page a course author needs.

A course is a directory of markdown lessons plus one manifest. Everything structural — how many lessons there are, where phases begin and end, which lesson comes next — is derived from the manifest, never written down twice.

## Directory structure

A course is a directory containing, at minimum, a `course.yaml` file and one lesson:

```
my-course/
├── course.yaml                        # Required: the manifest
├── assets/                            # Optional: images, diagrams, data files
└── phases/
    └── phase-0-getting-started/
        ├── overview.md                # Optional: shown at phase start
        ├── lesson-01-what-is-code.md
        └── lesson-02-your-terminal.md
```

Lesson files live at `phases/phase-{number}-{slug}/lesson-{NN}-{slug}.md`, where `{number}` is the phase number, `{NN}` is the lesson number zero-padded to two digits, and both slugs are lowercase kebab-case. The path is derived from the manifest — you do not declare it anywhere.

A phase directory may contain an `overview.md`. It has no required structure; runtimes present it when a phase begins.

## The manifest

`course.yaml` is the single source of truth for a course's structure.

**Minimal example:**

```yaml
spec_version: "1.0"
id: hello-course
title: Hello Course
version: "1.0.0"
phases:
  - number: 1
    slug: basics
    name: Basics
    lessons:
      - { number: 1, slug: first-steps, title: First Steps }
```

**Example with optional fields:**

```yaml
spec_version: "1.0"
id: zero-to-portfolio
title: Zero to Portfolio
version: "2.0.0"
description: Build and deploy your first portfolio site.
language: en
license: CC-BY-4.0
authors:
  - Customer Zero L&D
tutor:
  persona: >
    A warm, encouraging instructor who explains with everyday analogies.
  tone:
    - Encouraging, never condescending
    - Re-explain differently when the learner is confused
phases:
  - number: 0
    slug: getting-started
    name: Getting Started
    lessons:
      - { number: 1, slug: what-is-code, title: "What Is Code?" }
      - { number: 2, slug: your-terminal, title: Your Terminal, homework: true }
skills:
  - { id: git-basics, name: Git Basics }
```

> A title containing `?`, `:`, or `#` must be quoted when written inside a `{ … }` flow
> mapping — YAML gives those characters other meanings there. The block form needs no
> quoting.

### Manifest fields

| Field | Required | Constraints |
|---|---|---|
| `spec_version` | Yes | The Skilling version this course targets, as `"major.minor"`. A runtime refuses a course whose major version it does not support, and warns on an unsupported minor. |
| `id` | Yes | 1–64 characters, lowercase `a-z`, `0-9` and hyphens only. Must not start or end with a hyphen, or contain consecutive hyphens. Must stay stable across course versions — progress records key on it. |
| `title` | Yes | Non-empty. |
| `version` | Yes | The course's own semantic version. Any published content change bumps it. See [Course versions](#course-versions). |
| `description` | No | One or two sentences. |
| `language` | No | A BCP-47 language tag. Defaults to `en`. |
| `license` | No | An [SPDX identifier](https://spdx.org/licenses/) such as `CC-BY-4.0`, or the literal `proprietary`. |
| `authors` | No | A list of names or organisations. |
| `tutor` | No | `persona` (a string) and `tone` (a list of strings) guide how a tutor speaks. Guidance only — no runtime behaviour depends on them. |
| `phases` | Yes | A non-empty ordered list. See [Phases and lessons](#phases-and-lessons). |
| `skills` | No | Badges the course can award: a list of `{id, name}`. Ids must be unique within the manifest. |

There is no assessment field in this version — every 1.0 course is delivered informally, with answers written inline in the lesson. Assessed delivery, where answers live in separate key files, arrives in 1.1 as an optional addition.

### Phases and lessons

Each phase carries a `number`, a `slug`, a `name`, and a non-empty ordered list of `lessons`:

```yaml
phases:
  - number: 2
    slug: javascript
    name: JavaScript
    lessons:
      - { number: 1, slug: variables-and-types, title: Variables and Types }
      - { number: 2, slug: functions, title: Functions, homework: true }
```

Each lesson entry carries a `number`, a `slug`, a `title`, and optionally `homework: true`.

A lesson is addressed by its **coordinate**, written `{phase}.{lesson}` — so `2.1` is phase 2, lesson 1. Coordinates appear in prerequisites, progress records, and completion logs.

## Numbering and structure

- Phase numbers must be unique and ascend by exactly 1. The first phase may be numbered `0` or `1`.
- Lesson numbers must be unique within their phase and ascend by exactly 1, starting at `1`.
- Every lesson in the manifest must exist on disk at its derived path, and every lesson file on disk must appear in the manifest. The mapping is exactly one-to-one — no missing files, no orphans.
- A lesson entry's `number`, `slug`, and `title` must agree with the lesson file's frontmatter.
- If a lesson entry sets `homework: true`, the lesson file must carry a `## Homework Assignment` section. If it does not, the file must not carry one.

These rules exist because the course this specification generalises shipped with two lessons numbered 04, two numbered 05, and no 02 or 03 in one phase — and nothing noticed for months.

## Derived counts

**Never write a structural count anywhere in a course.** Lessons per phase, total lessons, phase boundaries, "lesson 3 of 9", percentage complete — all of it is derived from `phases`. Authoring any of it creates a second source of truth that will drift, and validators reject it.

```yaml
# Poor — a number that must now be maintained by hand
description: A 64-lesson course across 9 phases.
```

```yaml
# Good — the manifest already knows
description: Build and deploy your first portfolio site.
```

The same applies inside lesson bodies: write "next we'll look at the box model", not "in lesson 4 of 9".

## Lesson files

A lesson is one markdown file: YAML frontmatter, then a fixed set of sections with exact headings in a fixed order.

The anatomy is deliberately not pluggable. It is the part of this specification that was validated by a real course with real learners, and a tutor can only deliver a loop whose shape it knows in advance.

### Frontmatter

```yaml
---
title: "Your Terminal"
phase: 0
lesson: 2
duration_minutes: 30
prerequisites: ["0.1"]
skills_unlocked: []
sections:
  key_terms: present
  exercise: present
  next_up: present
---
```

| Field | Required | Constraints |
|---|---|---|
| `title` | Yes | Non-empty. Must match the manifest entry. |
| `phase` | Yes | Must match the manifest entry. |
| `lesson` | Yes | Must match the manifest entry. |
| `duration_minutes` | No | A positive integer. An estimate for the learner; nothing depends on it. |
| `prerequisites` | No | A list of `"{phase}.{lesson}"` coordinates that exist in the manifest. |
| `skills_unlocked` | No | A list of badge ids registered in the manifest's `skills`. A runtime writes these into the learner's record when the lesson completes. |
| `sections` | Yes | Declares the presence or absence of every optional section. See below. |

### The section registry

| Heading (exact) | Status |
|---|---|
| `## Learning Objectives` | Required |
| `## The Concept` | Required |
| `## Key Terms` | Optional — declare as `key_terms` |
| `## Hands-On Exercise` | Optional — declare as `exercise` |
| `## Quick Quiz` | Required |
| `## Homework Assignment` | Required when the manifest sets `homework: true`, forbidden otherwise |
| `## Next Up` | Optional — declare as `next_up` |

Required sections must be present with these exact headings, in this order. No other `##` headings are permitted — a lesson is a delivery script, not a free-form document. Use `###` subheadings freely inside a section.

### Declared absence

Every optional section must be declared in `sections` as either `present` or an explicit absence carrying intent. Silence is not valid.

```yaml
# Good — present
sections:
  exercise: present
```

```yaml
# Good — absent, and the author says why
sections:
  exercise:
    status: none
    intent: "Project phase: the exercise is the learner's own portfolio build."
```

```yaml
# Poor — the reader cannot tell whether this was a decision or an oversight
sections: {}
```

A runtime surfaces the intent to the learner in place of the missing beat, so an absence reads as deliberate rather than broken.

This rule exists because 24 of the originating course's 64 lessons silently lacked an exercise. The tutor improvised one every time, and every learner got a different course. Absence is fine. *Undeclared* absence is the defect.

## Section content

### Learning Objectives

A bullet list of outcomes, phrased from the learner's side.

```markdown
## Learning Objectives
By the end of this lesson, you will:
- Understand what the terminal is and why developers use it
- Know how to open the terminal on your computer
- Be able to run your first terminal commands
```

### The Concept

The teaching body. Prose, code blocks, `###` subheadings, lists — whatever explains the idea. This is the section a runtime re-presents when a learner asks to go deeper or answers a quiz question wrongly, so it should be substantial enough to explain twice.

### Key Terms

When present, a list of `- **Term**: definition` items.

```markdown
## Key Terms
- **Shell**: The program inside the terminal that interprets commands
- **Prompt**: The `$`, `%`, or `>` symbol indicating the terminal is ready
```

### Hands-On Exercise

When present, it must be self-contained: steps or a starting skeleton the learner can attempt using nothing outside the lesson. A learner who has to go and find something else has hit a dead end the runtime cannot rescue them from.

### Quick Quiz

Exactly **three** questions. Each is a numbered item with exactly **four** options labelled `a)` through `d)`, exactly one of which is correct, followed by an answer line giving the correct option **and the reason**.

```markdown
## Quick Quiz
1. What does the terminal let you do?
   - a) Edit photos
   - b) Talk to your computer with text commands
   - c) Browse the web
   - d) Play music

   **Answer:** b) Talk to your computer with text commands — it's a direct
   text conversation with the operating system.
```

The reason is not decoration. A runtime reads it aloud as feedback, and a learner who guessed correctly still needs to hear why.

Three questions and four options are fixed rather than configurable, so that a runtime's quiz beat, a validator's checks, and a learner's expectations are the same in every course.

### Homework Assignment

Required when the manifest sets `homework: true`. It carries a `###` assignment title, an `**Objective:**` line, one or more `- [ ]` requirement checkboxes, optionally `**Stretch Goals:**` checkboxes, and a `**Submission:**` line.

```markdown
## Homework Assignment
### Build Your Profile Page
**Objective:** Put the lesson's HTML into practice on something that's yours.

- [ ] A page using semantic HTML5 elements
- [ ] A heading, a paragraph about you, and a list of three interests
- [ ] Valid HTML with no unclosed tags

**Stretch Goals:**
- [ ] Add a photo with meaningful alt text

**Submission:** Tell your tutor when it's ready and share the file.
```

The `- [ ]` requirements are the unit of feedback: a tutor reports on each one separately. Stretch goals are reported too, but never gate anything.

### Next Up

When present, one or two sentences teasing the next lesson. When absent — and declared absent — a runtime generates a teaser from the manifest instead.

## Assets

Images, diagrams, and data files live in an `assets/` directory at the course root. References must be relative paths, so a course works wherever it is checked out:

```markdown
![The CSS box model](../../assets/box-model.png)
```

Absolute paths and references to files outside the course directory are not permitted. Validators report dangling references, so a deleted image fails a build rather than a lesson.

Large media — video, audio — should be linked to, not packaged.

## Course versions

A course's `version` is a semantic version, and each level means something specific about the **coordinates** (`{phase}.{lesson}`) a learner's record points at:

| Bump | Means | Coordinates |
|---|---|---|
| Patch | Content edits only — wording, examples, typo fixes | Unchanged |
| Minor | Additive: lessons appended to the end of a phase, or new trailing phases | Existing ones unchanged |
| Major | Anything that moves, removes, or renumbers a lesson or phase | May change |

This is what makes it safe for a runtime to roll a learner forward automatically on a patch or minor bump, and to keep them on the version they started for a major one. `skilling diff` checks coordinate stability between two versions mechanically, so the promise a version number makes is testable rather than aspirational.

## Validation

```bash
uvx skilling validate ./my-course
```

The validator reports one finding per problem, each with a stable error code and a pointer back into this page:

```
error  course.yaml:14  lesson-number-duplicate
       Phase 0 has two lessons numbered 4.
       → spec/course-format.md#numbering-and-structure

error  phases/phase-0-getting-started/lesson-03-navigating.md:41
       quiz-wrong-question-count
       Quick Quiz has 2 questions; exactly 3 are required.
       → spec/course-format.md#quick-quiz

2 errors, 0 warnings
```

Error codes are stable and never reused — see [the error-code catalogue](../docs/error-codes.md). A course that validates with zero errors is a **Conforming Course** ([conformance](README.md#conformance)).
