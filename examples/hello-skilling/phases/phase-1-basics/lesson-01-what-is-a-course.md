---
title: "What Is a Course?"
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

## Learning Objectives
By the end of this lesson, you will:
- Know what files a Skilling course is made of
- Be able to read a `course.yaml` and work out where any lesson lives on disk
- Understand why a course never states how many lessons it has

## The Concept
A Skilling course is a **directory**. There is no database, no export format, no upload step. If you can put a folder in a git repository, you can publish a course.

The directory holds exactly two kinds of thing: one manifest, and some markdown lessons.

```
hello-skilling/
├── course.yaml
└── phases/
    └── phase-1-basics/
        ├── overview.md
        ├── lesson-01-what-is-a-course.md
        ├── lesson-02-anatomy-of-a-lesson.md
        └── lesson-03-the-delivery-loop.md
```

### The manifest is the source of truth

`course.yaml` is the only place a course's *structure* is written down. It lists the phases, and inside each phase it lists the lessons:

```yaml
phases:
  - number: 1
    slug: basics
    name: Skilling Basics
    lessons:
      - { number: 1, slug: what-is-a-course, title: What Is a Course? }
      - { number: 2, slug: anatomy-of-a-lesson, title: Anatomy of a Lesson }
```

Notice what is *not* in there: any file paths. A lesson's path is derived from its numbers and slugs, always in the same shape:

```
phases/phase-{number}-{slug}/lesson-{NN}-{slug}.md
```

So the second lesson above must live at `phases/phase-1-basics/lesson-02-anatomy-of-a-lesson.md`. Not "conventionally". Must. A validator checks that every lesson in the manifest exists on disk and that every lesson file on disk appears in the manifest — one to one, no exceptions. There is no way to have a stray draft lesson lying around that a tutor might one day find.

### Coordinates

A lesson is addressed by its **coordinate**: the phase number and lesson number joined with a dot. `1.2` means phase 1, lesson 2. Coordinates turn up everywhere — in a lesson's prerequisites, in a learner's progress record, in a completion log. They are short, stable, and they don't depend on titles, which authors love to reword.

### Counts are never written down

Here is the rule that surprises people. **A course may not state a structural count anywhere.** Not `a 9-lesson phase`, not `lesson 3 of 12`, not `you're 40% through`.

Every one of those is derivable from the manifest, and anything derivable that you also write down becomes a second source of truth. Second sources of truth drift. The course this format was built from hand-maintained its lesson counts in six different places, and by the time anyone noticed, no two of them agreed.

So instead of writing `in lesson 4 of 9 we'll cover the box model`, you write "next we'll cover the box model", and the tutor works out the numbers from the manifest. It knows them exactly, always.

## Key Terms
- **Course**: A directory containing a `course.yaml` manifest and markdown lesson files
- **Manifest**: `course.yaml` — the single source of truth for a course's structure
- **Phase**: A named, numbered group of lessons; the unit at which courses celebrate progress
- **Lesson**: One markdown file, delivered in one sitting
- **Coordinate**: A lesson's address, written `{phase}.{lesson}` — for example `1.2`
- **Derived**: Computed from the manifest rather than authored; counts and percentages are always derived

## Hands-On Exercise
Here is a fragment of a real manifest:

```yaml
id: brewing-basics
title: Brewing Basics
phases:
  - number: 0
    slug: equipment
    name: Equipment
    lessons:
      - { number: 1, slug: the-kettle, title: The Kettle }
      - { number: 2, slug: grinders, title: Grinders }
  - number: 1
    slug: technique
    name: Technique
    lessons:
      - { number: 1, slug: water-temperature, title: Water Temperature }
```

Work out, on paper or in your head:

1. The full path of the file for the lesson titled "Grinders".
2. The coordinate of the lesson titled "Water Temperature".
3. Its `description` currently reads `A short 3-lesson introduction to coffee.` One phrase in there breaks a rule. Which, and why?

Answers are in the quiz below — have a go before you read on.

## Quick Quiz
1. Where does the lesson titled "Grinders" live?
   - a) `lessons/grinders.md`
   - b) `phases/equipment/grinders.md`
   - c) `phases/phase-0-equipment/lesson-02-grinders.md`
   - d) Wherever the author put it — the manifest records the path

   **Answer:** c) `phases/phase-0-equipment/lesson-02-grinders.md` — the path is
   derived from the phase number and slug plus the zero-padded lesson number and
   slug. The manifest never records paths, which is exactly why they can't drift.

2. What is the coordinate of "Water Temperature"?
   - a) `1.1`
   - b) `0.3`
   - c) `technique.water-temperature`
   - d) `3`

   **Answer:** a) `1.1` — it is the first lesson of phase 1. Lesson numbers
   restart at 1 in every phase, so a coordinate always needs both parts.

3. Why is `A short 3-lesson introduction to coffee` not allowed as a description?
   - a) Descriptions must be a single sentence
   - b) It states a structural count, which is derivable from the manifest
   - c) Descriptions may not mention lessons at all
   - d) The number should be written as a word

   **Answer:** b) It states a structural count. The manifest already knows there
   are three lessons; writing it again creates a second source of truth that will
   be wrong the moment a fourth lesson is added — and nothing will notice.

## Next Up
Next we open a single lesson file and look inside. Lessons have a fixed anatomy — the same headings, in the same order, every time — and there's a good reason it isn't configurable.
