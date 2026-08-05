---
title: "Anatomy of a Lesson"
phase: 1
lesson: 2
duration_minutes: 20
prerequisites: ["1.1"]
skills_unlocked: [course-anatomy]
objectives:
  - id: declare-absence
    kind: knowledge
    text: Explain why silence about a missing section is a defect and a declared absence is not
    about: [1]
  - id: name-the-sections
    kind: knowledge
    text: Name the required sections of a lesson and put them in the right order
    about: [2]
  - id: read-frontmatter
    kind: knowledge
    text: Say what a lesson's frontmatter declares, and why it repeats the manifest
    about: [3]
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## The Concept
A lesson is one markdown file with two parts: YAML frontmatter, then a fixed set of sections with exact headings in a fixed order.

### Frontmatter

```yaml
---
title: "Anatomy of a Lesson"
phase: 1
lesson: 2
duration_minutes: 20
prerequisites: ["1.1"]
skills_unlocked: [course-anatomy]
sections:
  key_terms: present
  exercise: present
  next_up: present
---
```

`title`, `phase`, and `lesson` must agree with the manifest entry this file derives from. That looks like duplication, and it is — but it is *checked* duplication. A validator compares the two, so a file that gets renumbered without its manifest entry being updated fails immediately rather than being delivered as the wrong lesson.

`skills_unlocked` lists badge ids the learner earns by finishing this lesson. Those ids must be registered in the manifest's `skills` list. This matters more than it looks: in the course this format came from, eleven lessons declared badges and the delivery system never wrote a single one to the learner's state. Learners earned things that did not exist. Here, a declared badge that never reaches the record is a runtime failure, not a cosmetic one.

### The section registry

There is a fixed list of permitted headings, and no others:

| Heading | Status |
|---|---|
| `## Learning Objectives` | Required |
| `## The Concept` | Required |
| `## Key Terms` | Optional |
| `## Hands-On Exercise` | Optional |
| `## Quick Quiz` | Required |
| `## Homework Assignment` | Only when the manifest says `homework: true` |
| `## Next Up` | Optional |

They must appear in that order. You cannot invent a `## Further Reading` section, and you cannot put the quiz before the concept. Use `###` subheadings freely inside a section — this lesson does.

That rigidity is the point. A tutor delivering your course has never read it before and cannot ask you what you meant. It knows a lesson has a concept to teach and a quiz to ask because *every* lesson does. A configurable anatomy would mean every course teaches the tutor a new shape, and every tutor guesses.

### Declared absence

Three of those sections are optional — but "optional" does not mean you can stay quiet about them. Every optional section must be declared in `sections`, either as present or as an explicit absence carrying your reason:

```yaml
sections:
  key_terms: present
  exercise:
    status: none
    intent: "Project phase: the learner's own build is the exercise."
  next_up: present
```

An empty `sections: {}` is invalid even if the sections genuinely aren't there.

This exists because of a specific, painful failure. In the course this format came from, 24 of its 64 lessons had no exercise at all. Nobody had decided that — it just happened, lesson by lesson. The tutor, finding no exercise, helpfully improvised one. So every learner got a different course, and no two learners could compare notes on the same material.

Absence is completely fine. Sometimes there genuinely shouldn't be an exercise. What is not fine is a reader — human or tutor — being unable to tell the difference between a decision and an oversight. When you declare the absence, the tutor tells the learner your reason instead of inventing something.

## Key Terms
- **Frontmatter**: The YAML block at the top of a lesson file, declaring identity and section presence
- **Section registry**: The fixed list of permitted `##` headings, in their required order
- **Declared absence**: An optional section marked `status: none` with an `intent` explaining why
- **Badge**: A named skill, registered in the manifest, awarded via a lesson's `skills_unlocked`
- **Beat**: One step of delivery — a tutor turns each section into a beat

## Hands-On Exercise
You're writing the final lesson of a project phase. It has objectives, a concept, and a quiz. It has no key terms — the vocabulary was all covered earlier — and no exercise, because the learner is building their own project and that *is* the practice. It's the last lesson in the course, so there's nothing to tease.

Write the frontmatter for it. Assume it is lesson 4 of phase 6, titled "Shipping It", takes about 45 minutes, follows on from lesson 3 of the same phase, and awards a badge with the id `deployment`.

Every optional section needs a decision, and every absence needs a reason someone else would find convincing.

## Quick Quiz
1. A lesson has objectives, a concept, a quiz, and nothing else. Its frontmatter says `sections: {}`. What's wrong?
   - a) Nothing — the optional sections are absent, and the frontmatter reflects that
   - b) `sections` should be omitted entirely when there are no optional sections
   - c) Each optional section must be declared as present or as an absence with intent
   - d) A lesson must have at least one optional section

   **Answer:** c) Each optional section must be declared. Silence leaves a reader
   unable to tell a deliberate choice from an oversight — which is exactly how 24
   lessons ended up quietly missing their exercises.

2. Why is the section list fixed rather than configurable?
   - a) To keep lesson files small
   - b) So a tutor that has never read your course knows what shape it is
   - c) Because markdown only supports a fixed set of headings
   - d) To make lessons render consistently on the web

   **Answer:** b) So a tutor knows the shape in advance. The tutor cannot ask you
   what you meant, so the anatomy has to be knowable without asking — a
   configurable anatomy just moves the guessing to delivery time.

3. A lesson's frontmatter says `lesson: 3`, but the manifest lists it as lesson 4. What happens?
   - a) The manifest wins, and the file is delivered as lesson 4
   - b) The frontmatter wins, and the file is delivered as lesson 3
   - c) The course fails validation
   - d) The tutor asks the learner which is correct

   **Answer:** c) The course fails validation. The duplication between manifest and
   frontmatter exists precisely so the mismatch is caught — picking a winner would
   silently deliver the wrong lesson.

## Next Up
Now you can read a course and read a lesson. Next we look at what a tutor actually *does* with them — the delivery loop, and the gates that make it tutoring rather than playback.
