"""``skilling init`` — a conforming skeleton.

The scaffold validates clean on the first run, and deliberately shows a declared absence
in its second lesson: the fastest way to learn that absence must be declared is to be
handed a file that already declares one.
"""

from __future__ import annotations

import re
from pathlib import Path

MANIFEST = """\
spec_version: "1.0"
id: {slug}
title: {title}
version: "0.1.0"
description: A new Skilling course.
language: en
# license: CC-BY-4.0        # an SPDX identifier, or `proprietary`
phases:
  - number: 1
    slug: basics
    name: Basics
    lessons:
      - {{ number: 1, slug: first-steps, title: First Steps }}
      - {{ number: 2, slug: going-further, title: Going Further }}
# skills:
#   - {{ id: the-basics, name: The Basics }}
"""

OVERVIEW = """\
# Basics

Say what this phase gets the learner to, and what they'll be able to do at the end of it.
Phase overviews have no required structure — a tutor shows this when the phase begins.
"""

LESSON_ONE = """\
---
title: "First Steps"
phase: 1
lesson: 1
duration_minutes: 20
prerequisites: []
skills_unlocked: []
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## Learning Objectives
By the end of this lesson, you will:
- Know the one idea this lesson exists to teach
- Be able to do the smallest useful thing with it
- Recognise when to reach for it

## The Concept
Teach the idea here. Write enough that it can be explained twice — a tutor re-presents this
section when a learner asks to go deeper, or answers a quiz question wrongly.

Use `###` subheadings freely. Do not add new `##` headings: the section list is fixed.

### A worked example
Show it, don't just describe it.

## Key Terms
- **First term**: What it means, in one line
- **Second term**: What it means, in one line

## Hands-On Exercise
Give the learner something to attempt using nothing outside this lesson. Steps, or a
skeleton to fill in. A learner who has to go and find something else has hit a dead end
the tutor cannot rescue them from.

## Quick Quiz
1. Replace this with a question about the concept above.
   - a) A plausible wrong answer
   - b) The right answer
   - c) Another plausible wrong answer
   - d) A fourth option

   **Answer:** b) The right answer — and here is the reason, which the tutor reads out as
   feedback. A learner who guessed correctly still needs this.

2. Replace this with a second question.
   - a) The right answer
   - b) A plausible wrong answer
   - c) Another plausible wrong answer
   - d) A fourth option

   **Answer:** a) The right answer — with the reason it is right, not just a restatement.

3. Replace this with a third question.
   - a) A plausible wrong answer
   - b) Another plausible wrong answer
   - c) The right answer
   - d) A fourth option

   **Answer:** c) The right answer — and why, briefly.

## Next Up
One or two sentences teasing the next lesson. Don't number it: the tutor derives position
from the manifest.
"""

LESSON_TWO = """\
---
title: "Going Further"
phase: 1
lesson: 2
duration_minutes: 20
prerequisites: ["1.1"]
skills_unlocked: []
sections:
  key_terms:
    status: none
    intent: "The vocabulary was introduced in the previous lesson and is reused here."
  exercise: present
  next_up:
    status: none
    intent: "Last lesson of the course — there is nothing after this to tease."
---

## Learning Objectives
By the end of this lesson, you will:
- Extend the first lesson's idea to a second situation
- Know the most common way it goes wrong

## The Concept
Build on lesson one rather than restating it.

Notice this lesson's frontmatter: two optional sections are declared *absent*, each with a
reason. Absence is fine; undeclared absence is not, because a reader cannot tell it from an
oversight. The tutor shows the learner your reason in place of the missing beat.

## Hands-On Exercise
Something slightly harder than the first lesson's exercise.

## Quick Quiz
1. Replace this with a question about this lesson.
   - a) A plausible wrong answer
   - b) The right answer
   - c) Another plausible wrong answer
   - d) A fourth option

   **Answer:** b) The right answer — with the reason.

2. Replace this with a second question.
   - a) The right answer
   - b) A plausible wrong answer
   - c) Another plausible wrong answer
   - d) A fourth option

   **Answer:** a) The right answer — with the reason.

3. Replace this with a third question.
   - a) A plausible wrong answer
   - b) Another plausible wrong answer
   - c) A fourth option
   - d) The right answer

   **Answer:** d) The right answer — with the reason.
"""

_SLUG_SAFE = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    slug = _SLUG_SAFE.sub("-", value.strip().lower()).strip("-")
    return slug or "my-course"


def titleise(slug: str) -> str:
    return " ".join(word.capitalize() for word in slug.split("-"))


def scaffold(target: Path, *, title: str | None = None) -> list[Path]:
    slug = slugify(target.name)
    course_title = title or titleise(slug)
    phase_dir = target / "phases" / "phase-1-basics"
    phase_dir.mkdir(parents=True, exist_ok=True)

    files = {
        target / "course.yaml": MANIFEST.format(slug=slug, title=course_title),
        phase_dir / "overview.md": OVERVIEW,
        phase_dir / "lesson-01-first-steps.md": LESSON_ONE,
        phase_dir / "lesson-02-going-further.md": LESSON_TWO,
    }
    for path, content in files.items():
        path.write_text(content, encoding="utf-8")
    return list(files)
