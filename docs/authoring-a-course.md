# Authoring a course

A walkthrough from empty directory to a course a tutor can deliver. The normative details are in [course format](../spec/course-format.md); this page is the order to do things in.

## 1. Scaffold

```bash
uvx skilling init brewing-basics
```

You get a manifest, one phase, two lessons, and a phase overview. It validates clean immediately, so anything the validator says from here on is something *you* changed.

Look at the second lesson's frontmatter before you touch anything else — it ships with two declared absences, which is the part of the format people most often get wrong first.

## 2. Plan in the manifest, not in prose

Decide your phases and lessons in `course.yaml` before writing any teaching. The manifest is the only place structure lives, so this is also the moment to get numbering right: lessons restart at 1 in every phase, and nothing may skip.

```yaml
phases:
  - number: 1
    slug: equipment
    name: Equipment
    lessons:
      - { number: 1, slug: the-kettle, title: The Kettle }
      - { number: 2, slug: grinders, title: Grinders, homework: true }
  - number: 2
    slug: technique
    name: Technique
    lessons:
      - { number: 1, slug: water-temperature, title: Water Temperature }
```

Then create the files at their derived paths — `phases/phase-1-equipment/lesson-02-grinders.md` — and run `skilling show` to check the shape is what you had in mind:

```bash
uvx skilling show ./brewing-basics
```

Everything under **Derived** in that output is computed. If a number there surprises you, the manifest is wrong, not the display.

## 3. Write the concept first, the quiz last

Within a lesson, `## The Concept` is the load-bearing section. A tutor re-presents it when a learner asks to go deeper and again when they answer a quiz question wrongly, so write it as something that can be read twice — with a second example rather than a louder version of the first.

Only then write the quiz, and write it *against* the concept: three questions, four options, and an answer line that gives the reason.

```markdown
   **Answer:** b) Talk to your computer with text commands — it's a direct
   text conversation with the operating system.
```

The reason after the dash is not decoration. It is what the tutor says as feedback, including to a learner who guessed right and learned nothing.

## 4. Decide every optional section out loud

Three sections are optional, and every one of them needs a decision recorded in `sections`:

```yaml
sections:
  key_terms: present
  exercise:
    status: none
    intent: "Project phase: the learner's own build is the exercise."
  next_up: present
```

Writing `sections: {}` is invalid even when the sections genuinely aren't there. The test to apply to an `intent` is whether a stranger reading it would agree the absence was deliberate.

## 5. Never write a number down

No lesson counts, no "lesson 3 of 12", no percentages — anywhere, including in the description and in the teaching prose. Write "next we'll look at grinders", and let the tutor work out where that falls.

If you need to *quote* a bad example (as this repository's own example course does), put it in backticks. The validator skips code spans and fenced blocks, because showing a counter-example is exactly what code formatting is for.

## 6. Validate, and read the anchors

```bash
uvx skilling validate ./brewing-basics
```

```
error  phases/phase-1-equipment/lesson-02-grinders.md:61  quiz-answer-no-reason
       Question 2's answer names the correct option but gives no reason.
       A learner who guessed right still needs the why.
       → spec/course-format.md#quick-quiz

1 error, 0 warnings
```

Follow the anchor when a finding seems wrong. Either the specification convinces you, or you have found a bug worth reporting — both are useful outcomes, and the second one is how the specification improves.

Warnings do not make a course non-conforming. Use `--strict` in CI if you want them to.

## 7. Deliver it yourself before anyone else does

```bash
uvx skilling deliver ./brewing-basics --state ./.skilling
```

This walks the real delivery loop with no language model in it, which makes it a blunt but honest reviewer. You will feel every gate, notice every concept that is too thin to re-read, and find out immediately whether your quiz questions are answerable from what you actually wrote.

Sitting through your own course is the cheapest review available.

## 8. Give the tutor facts, not sentences

**Since 1.1**, and entirely optional. If your course belongs to something with a name, a URL, or a social handle, put those in `ceremony.brand` and give each phase a one-clause `highlight`:

```yaml
ceremony:
  brand:
    product: Brewing Basics
    url: brewing.example
    hashtags: [Coffee, LearningInPublic]
phases:
  - number: 1
    slug: equipment
    name: Equipment
    highlight: dialled in their first shot by taste
    lessons: [ … ]
```

That is all most courses need. A tutor writes the celebration itself — fresh, in the learner's register — and the facts are there so it does not have to guess your handle. It will guess, if you make it.

Reach for `phase_completed_template` only when the wording is genuinely fixed: legal copy, a campaign, something signed off. Then use placeholders rather than numbers — `{completed_count}` of `{lesson_count}` is how you get "3 of 9 lessons done" into a share post without maintaining a count, and writing the number yourself is still an `authored-count` error.

## 9. Consider giving objectives ids

**Since 1.1**, also optional. Written as prose, your objectives are the one part of a lesson a tutor cannot act on. Given ids and mapped to quiz questions, they become the thing a tutor names when a learner gets something wrong:

```yaml
objectives:
  - id: dial-by-taste
    text: Taste a shot and say which way to move the grind
    tested_by: [1, 3]
```

Declaring `objectives:` means dropping the `## Learning Objectives` section — they are mutually exclusive, because two copies of the same sentences is the drift the format refuses everywhere else.

The `tested_by` mapping is what lets even a model-free runtime record that a learner demonstrated something, rather than merely attended. Worth the two extra lines.

## 10. Version it honestly

Once anyone has started your course, the version number is a promise about coordinates:

| Bump | You may |
|---|---|
| Patch | Edit content — wording, examples, fixes |
| Minor | Append lessons to the end of a phase, or add trailing phases |
| Major | Move, remove, or renumber anything |

`skilling diff` checks you kept the promise:

```bash
uvx skilling diff ./published ./candidate --strict
```

```
1.0.0 → 1.1.0  (declared: minor)

  • 1.2 was appended

  all existing coordinates stable
  minimum bump required: minor
  declared minor bump is sufficient
```

Put that in CI. It is what lets a runtime roll a learner forward automatically without wondering whether their recorded position still means anything.

## Where authors most often go wrong

| Mistake | What happens |
|---|---|
| Silence about a missing exercise | `section-absence-undeclared`. Declare it with a reason instead |
| An answer line that restates the option | `quiz-answer-no-reason`. Add the why |
| A stray draft lesson under `phases/` | `lesson-file-orphan`. A tutor could have delivered it |
| Renumbering a lesson but not the manifest | `frontmatter-manifest-mismatch`. That duplication exists to catch exactly this |
| "A 9-lesson course" in the description | `authored-count`. The manifest already knows |

The full list is in [error codes](error-codes.md).

## When you want to see it done at scale

[`examples/coding-bootcamp`](../examples/coding-bootcamp/) is a real 64-lesson course carried in this repository. Worth opening when a rule feels abstract:

- **How to word a declared absence** — it has 43 of them, and the ones for phases 4, 5 and 6 show what a per-phase reason looks like rather than 22 copies of the same sentence.
- **How much `tested_by` to write** — 168 of its 235 objectives map to a quiz question. The other 67 do not, deliberately: "appreciate why this matters" is not a quiz question, and a loose mapping produces confidently wrong capability claims.
- **A ceremony block with a real brand in it**, and a share template that says "6 of 64 lessons done" without any author having written a number.

It was ported from a course that existed before the format did, so it is also the honest record of what that costs: seven quiz answers had to gain a reason, one homework section had no submission line, and a whole phase had to be renumbered.
