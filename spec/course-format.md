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

The asymmetry is deliberate: **lesson numbers are zero-padded to two digits and phase numbers are not.** `phase-1-basics`, not `phase-01-basics`; `lesson-01-first-steps`, not `lesson-1-first-steps`. Lessons are padded so a directory listing sorts correctly past nine; phases are rarely numerous enough to need it.

The `{slug}` in each path is the `slug` field from the manifest, not a slugified `title`. The two are often the same and need not be.

A phase directory may contain an `overview.md`. It has **no constraints at all** — any headings, any structure, any length — because it is orientation rather than a delivery script. Runtimes present it when a phase begins.

Only files matching `lesson-{NN}-{slug}.md` are lesson files. `overview.md`, anything under `assets/`, and any other file you keep alongside your course are invisible to the manifest rules below.

The course directory's own name is yours. It need not match the manifest's `id`, and nothing derives from it.

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
| `skills` | No | Badges the course can award: a list of `{id, name}`. Ids follow the same rules as `id` above, and must be unique within the manifest. A registered badge need not be unlocked by any lesson. |
| `ceremony` | No | Facts a tutor may not invent, plus optional literal templates. **Since 1.1** — see [Ceremony](#ceremony). |

**Unknown fields are rejected, not ignored.** At 1.0 there are no optional additions to guess at, so a key that is not in this table is a typo worth reporting rather than an extension point. The same applies to lesson frontmatter.

A brand-new course starts at `version: "1.0.0"`. Nothing forbids `0.1.0`, but the [version semantics](#course-versions) are promises about coordinate stability, and a course with learners in it should be making them.

There is no assessment field in this version — every 1.0 course is delivered informally, with answers written inline in the lesson. Assessed delivery, where answers live in separate key files, arrives in a later version as an optional addition.

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

A phase entry may also carry a `highlight` — one clause naming what the learner just achieved, used at [ceremony](#ceremony). **Since 1.1.**

**Keep it free of pronouns.** A tutor may use it in the third person ("they built…") and a share post will use it in the first ("I built…"), so `wrote a first working function` works everywhere and `wrote their first working function` reads wrong in half the places it appears.

```yaml
  - number: 2
    slug: javascript
    name: JavaScript
    highlight: wrote a first working function
    lessons: [ … ]
```

A lesson is addressed by its **coordinate**, written `{phase}.{lesson}` — so `2.1` is phase 2, lesson 1. Coordinates appear in prerequisites, progress records, and completion logs.

## Numbering and structure

- Phase numbers must be unique and ascend by exactly 1. The first phase may be numbered `0` or `1`.
- Lesson numbers must be unique within their phase and ascend by exactly 1, starting at `1`.
- Every lesson in the manifest must exist on disk at its derived path, and every `lesson-{NN}-{slug}.md` on disk must appear in the manifest. The mapping is exactly one-to-one — no missing files, no orphans. Nothing else on disk is a lesson file, so an `overview.md` or an asset is neither missing nor an orphan.
- A lesson entry's `number`, `slug`, and `title` must agree with the lesson file's frontmatter.
- If a lesson entry sets `homework: true`, the lesson file must carry a `## Homework Assignment` section. If it does not, the file must not carry one.

These rules exist because the course this specification generalises shipped with two lessons numbered 04, two numbered 05, and no 02 or 03 in one phase — and nothing noticed for months.

## Derived counts

**Never write a structural count anywhere in a course.** Lessons per phase, total lessons, phase boundaries, "lesson 3 of 9", percentage complete — all of it is derived from `phases`. Authoring any of it creates a second source of truth that will drift, and validators reject it.

A **structural** count is one about the course's own phases and lessons, or about the learner's position among them. Counts *of your subject matter* are not structural and are perfectly fine: a course called *Three Useful Knots* is not in breach, and neither is "the train waits two minutes" or "a list of three interests".

The rule covers every learner-facing string in the course, including a phase `overview.md` and a section's `intent`, because a runtime reads those out too. Avoid position language in an intent for that reason — write why a section is absent, not where the lesson sits.

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
| `objectives` | No | Structured, addressable learning objectives. **Since 1.1** — see [Learning Objectives](#learning-objectives). Present it and the `## Learning Objectives` section must be absent. |
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

Required sections must be present with these exact headings. **Every section in the table, required or optional, appears in the table's order** — an optional section that is present sits at its registry position, and an absent one simply leaves no gap. No other `##` headings are permitted: a lesson is a delivery script, not a free-form document. Use `###` subheadings freely inside a section.

Two details the table cannot show:

- **`## Homework Assignment` is never declared in `sections`.** Its presence is settled entirely by the manifest's `homework` flag, so declaring it again would be the second source of truth this format spends a whole section arguing against. Only the three rows marked "declare as" belong in `sections`.
- **A single `#` heading is not forbidden**, because only `##` is constrained — but a lesson body has no use for one. The title is already in the frontmatter and the manifest; a third copy is duplication the format would rather you avoided.

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

The absence form is exactly those two keys and no others. `status` takes the single value `none` — there is no `skipped`, `absent`, or `n/a` — and `intent` is required and must be non-empty. An absence with an empty intent is the defect this rule exists to catch, dressed up as compliance.

A runtime surfaces the intent to the learner in place of the missing beat, so an absence reads as deliberate rather than broken. Write it for a learner's ears, not as a note to yourself.

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

#### Structured objectives

**Since 1.1.** Objectives are a lesson's actual contract — "by the end you will be able to X" — and as prose nothing can reference one. Give them ids in the frontmatter instead and they become addressable, which lets a tutor target remediation at the objective a wrong answer implicates rather than re-presenting the whole concept, and lets a runtime record which capabilities a learner has actually demonstrated.

```yaml
objectives:
  - id: open-a-terminal
    text: Open the terminal on your own computer
    tested_by: [1, 3]
  - id: run-a-command
    text: Run a command and read what it prints
    tested_by: [2]
```

| Field | Required | Constraints |
|---|---|---|
| `id` | Yes | Lowercase kebab-case, unique within the lesson. Stable: a learner's record refers to it. |
| `text` | Yes | The outcome, phrased from the learner's side, as the prose form would be. |
| `tested_by` | No | Quiz question numbers that test this objective. Each must exist. |

**Structured and prose objectives are mutually exclusive.** Declare `objectives:` and the `## Learning Objectives` section must be absent — a runtime renders the structured form in its place. Omit `objectives:` and the section stays required, exactly as in 1.0. Allowing both would be two sources of truth for the same sentences, which is the drift this format refuses everywhere else.

`tested_by` is what makes objectives useful to a runtime that cannot judge work: when every question testing an objective is answered correctly, that objective was demonstrated, and the runtime can say so in the record. Without it, marking objectives met needs a tutor with judgement. Both are conforming; see [runtime](runtime.md#objectives-and-the-record).

An objective is not a badge. A badge marks that a lesson completed; an objective claims a capability was demonstrated. Keeping them separate is deliberate — see [what the record knows](../docs/concepts/what-the-record-knows.md).

### The Concept

The teaching body. Prose, code blocks, `###` subheadings, lists, tables, block quotes — any markdown that explains the idea. That list is illustrative, not exhaustive; the only structural restriction inside a section is that you may not open a new `##`.

This is the section a runtime re-presents when a learner asks to go deeper or answers a quiz question wrongly, so it should be substantial enough to explain twice.

### Key Terms

When present, a list of `- **Term**: definition` items.

```markdown
## Key Terms
- **Shell**: The program inside the terminal that interprets commands
- **Prompt**: The `$`, `%`, or `>` symbol indicating the terminal is ready
```

### Hands-On Exercise

When present, it must be self-contained: steps or a starting skeleton the learner can attempt without going to find **information** the lesson did not give them. A learner sent elsewhere for an instruction has hit a dead end the runtime cannot rescue them from.

Self-contained is about knowledge, not equipment. A course on espresso may require an espresso machine and a course on knots may require a length of rope — name what is needed in the lesson or the phase overview, prefer substitutes a learner probably already owns, and the exercise is self-contained. This is worth stating because the format was generalised from a course where every exercise needed only a text editor, and most subjects are not like that.

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

The answer line's shape matters, because a runtime parses it:

- `**Answer:**` is literal, bold and colon included.
- It opens with the correct option's label, then restates that option's text, then gives the reason. A runtime strips the restated text to find the reason, so an answer that gives only the letter has no reason to read out.
- It may wrap across as many source lines as it needs. Indented continuation lines belong to the same answer.

The reason is not decoration. A runtime reads it aloud as feedback, and a learner who guessed correctly still needs to hear why.

Question numbers are what [`tested_by`](#structured-objectives) refers to, so renumbering a quiz means revisiting the objectives that point at it.

### Why the quiz is fixed and hand-written

Three questions, four options, authored rather than generated. That is a choice, not an obvious truth, and it is worth naming what it buys and costs.

It buys three things a generated quiz cannot have. A validator can check it, so a malformed quiz fails a build instead of a lesson. Every learner gets the same questions, so "most people miss question 2" is a sentence that means something. And assessed delivery, when it arrives, needs stable keys to hold answers against.

It costs the obvious thing: a tutor that could have asked a better question — one aimed at what *this* learner just got confused about — is not allowed to. That is a real loss in a format built for AI tutors, and the trade is made deliberately in favour of the three properties above. A future version may let a tutor generate supplementary questions alongside the authored three; it will not remove them.

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

**On the last lesson of a course there is nothing to tease**, and no manifest entry for a runtime to generate one from. Declare `next_up` absent, and say that in the intent. Do not write a `## Next Up` that promises material the course does not contain.

## Ceremony

**Since 1.1.** Entirely optional. A course with no `ceremony` block gets a plain, unbranded celebration at each phase boundary, exactly as before.

This block exists because of a specific division of labour. A tutor writes a better celebration than any template could — contextual, in the learner's own register, different every time. What a tutor must **not** do is invent a product name, a URL, or a social handle, because it will guess `@YourCourse` when the real handle is `@your.course`. So the manifest carries the facts, and the tutor writes the prose.

```yaml
ceremony:
  brand:
    product: Claude Academy
    url: futureofdev.com/claude-academy
    mention: "@claudeai"
    handles:
      x: "@FutureOfDev"
      instagram: "@claude.academy"
    hashtags: [WebDev, CodingJourney]
  phase_completed_template: |
    🎉 Just completed Phase {phase_number}: {phase_name}!

    {phase_highlight}

    Built with {mention} — free at {url}
```

| Field | Required | Constraints |
|---|---|---|
| `brand.product` | No | The name of the product or programme the course belongs to. |
| `brand.url` | No | Where a reader can find it. |
| `brand.mention` | No | A handle to credit, including its `@`. |
| `brand.handles` | No | A mapping of platform name to handle. Keys are free-form; handles include their `@`. |
| `brand.hashtags` | No | A list of tags **without** the `#`. A runtime adds it, so an author cannot produce `##WebDev`. |
| `phase_completed_template` | No | Literal copy, used verbatim when present. |
| `course_completed_template` | No | The same, for the end of the course. |

### Placeholders

A template may use these and no others. An unknown placeholder is an error, because a template that silently renders `{phase_nmae}` as literal text ships to social media.

| Placeholder | Filled with |
|---|---|
| `{phase_number}`, `{phase_name}` | The completed phase |
| `{phase_highlight}` | That phase's `highlight` |
| `{course_title}` | The manifest `title` |
| `{completed_count}`, `{lesson_count}` | Derived by the runtime |
| `{product}`, `{url}`, `{mention}` | From `brand` |
| `{hashtags}` | From `brand.hashtags`, with each `#` added |

`{completed_count}` and `{lesson_count}` are how you get "3 of 9 lessons done" into a share post **without** writing a count. The runtime fills them; you never maintain them. Writing the numbers yourself is still a [derived-count](#derived-counts) violation, and the validator scans templates for it.

If a template uses `{phase_highlight}`, every phase needs a `highlight`. A share post with a hole in the middle is worse than one that never promised a highlight.

### When to write a template at all

Prefer not to. Facts plus a tutor beats a template for almost every course, and gives every learner something written for them rather than for everyone. Reach for a literal template only when the wording is genuinely non-negotiable — a legal line, a campaign, copy someone signed off — or when you know your course will be delivered by a runtime that has no model in it and can only assemble facts plainly.

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
