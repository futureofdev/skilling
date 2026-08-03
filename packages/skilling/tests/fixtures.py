"""The clean course fixture: a minimal course that must validate with zero findings.

It is deliberately small but not trivial — two phases so there is a phase boundary, one
homework lesson, one registered badge, declared absences, and an asset reference. Every
corruption in ``corruptions.py`` is a small mutation of this tree, which is why the content
below is written to be easy to target with a string replacement.
"""

from __future__ import annotations

from pathlib import Path

MANIFEST = """\
spec_version: "1.0"
id: clean-course
title: Clean Course
version: "1.0.0"
description: A course that conforms, used as the base for every corruption.
language: en
license: CC-BY-4.0
authors:
  - The Skilling maintainers
tutor:
  persona: A calm instructor.
  tone:
    - Direct
phases:
  - number: 0
    slug: start
    name: Start
    lessons:
      - { number: 1, slug: one, title: One }
      - { number: 2, slug: two, title: Two, homework: true }
  - number: 1
    slug: next
    name: Next
    lessons:
      - { number: 1, slug: three, title: Three }
skills:
  - { id: alpha, name: Alpha }
"""

LESSON_ONE = """\
---
title: "One"
phase: 0
lesson: 1
duration_minutes: 10
prerequisites: []
skills_unlocked: []
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## Learning Objectives
By the end of this lesson, you will:
- Know the first thing

## The Concept
The first thing is worth knowing. See [the diagram](../../assets/diagram.txt) for a picture.

## Key Terms
- **First**: the first thing

## Hands-On Exercise
Try the first thing yourself.

## Quick Quiz
1. What is the first thing?
   - a) Wrong one
   - b) The first thing
   - c) Wrong three
   - d) Wrong four

   **Answer:** b) The first thing — because that is what the concept described.

2. When would you reach for it?
   - a) When the first thing is needed
   - b) Never
   - c) Only on Tuesdays
   - d) When painting

   **Answer:** a) When the first thing is needed — it has exactly one use.

3. What is it not?
   - a) A first thing
   - b) Useful
   - c) A second thing
   - d) Simple

   **Answer:** c) A second thing — those come later and behave differently.

## Next Up
Next we look at the second thing.
"""

LESSON_TWO = """\
---
title: "Two"
phase: 0
lesson: 2
duration_minutes: 10
prerequisites: ["0.1"]
skills_unlocked: [alpha]
sections:
  key_terms: present
  exercise: present
  next_up: present
---

## Learning Objectives
By the end of this lesson, you will:
- Know the second thing

## The Concept
The second thing builds on the first.

## Key Terms
- **Second**: the second thing

## Hands-On Exercise
Try the second thing yourself.

## Quick Quiz
1. What is the second thing?
   - a) Wrong one
   - b) Wrong two
   - c) The second thing
   - d) Wrong four

   **Answer:** c) The second thing — it follows from the first.

2. What does it build on?
   - a) The first thing
   - b) Nothing
   - c) The third thing
   - d) Paint

   **Answer:** a) The first thing — which is why it comes second.

3. Is it optional?
   - a) Yes
   - b) No
   - c) Sometimes
   - d) Only on Tuesdays

   **Answer:** b) No — the third thing depends on it.

## Homework Assignment
### Practise Both Things
**Objective:** Use the first and second things together on something of your own.

- [ ] Use the first thing
- [ ] Use the second thing

**Stretch Goals:**
- [ ] Use them at the same time

**Submission:** Tell your tutor when it is ready.

## Next Up
Next we reach the third thing.
"""

LESSON_THREE = """\
---
title: "Three"
phase: 1
lesson: 1
duration_minutes: 10
prerequisites: ["0.2"]
skills_unlocked: []
sections:
  key_terms:
    status: none
    intent: "The vocabulary was covered in the previous phase and is reused here."
  exercise:
    status: none
    intent: "Project phase: the learner's own build is the exercise."
  next_up:
    status: none
    intent: "Last lesson of the course, so there is nothing to tease."
---

## Learning Objectives
By the end of this lesson, you will:
- Know the third thing

## The Concept
The third thing needs both the others.

## Quick Quiz
1. What does the third thing need?
   - a) Nothing
   - b) Both the others
   - c) Only the first
   - d) Paint

   **Answer:** b) Both the others — it composes them.

2. Where does it sit?
   - a) In the second phase
   - b) In the first phase
   - c) Outside the course
   - d) Nowhere

   **Answer:** a) In the second phase — which is why it can assume the earlier lessons.

3. Is it the end?
   - a) No
   - b) Yes
   - c) Only on Tuesdays
   - d) Unclear

   **Answer:** b) Yes — it is the last lesson, which is why Next Up is declared absent.
"""

PHASE_ZERO = "phases/phase-0-start"
PHASE_ONE = "phases/phase-1-next"

MANIFEST_PATH = "course.yaml"
LESSON_ONE_PATH = f"{PHASE_ZERO}/lesson-01-one.md"
LESSON_TWO_PATH = f"{PHASE_ZERO}/lesson-02-two.md"
LESSON_THREE_PATH = f"{PHASE_ONE}/lesson-01-three.md"

FILES: dict[str, str] = {
    MANIFEST_PATH: MANIFEST,
    f"{PHASE_ZERO}/overview.md": "# Start\n\nWhere the course begins.\n",
    LESSON_ONE_PATH: LESSON_ONE,
    LESSON_TWO_PATH: LESSON_TWO,
    LESSON_THREE_PATH: LESSON_THREE,
    "assets/diagram.txt": "a picture, imagine it\n",
}


def build(root: Path) -> Path:
    """Write the clean course under ``root`` and return the course directory."""
    for relative, content in FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def read(root: Path, relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8")


def write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def edit(root: Path, relative: str, old: str, new: str) -> None:
    """Replace exactly one occurrence, failing loudly if the anchor has drifted."""
    text = read(root, relative)
    if text.count(old) != 1:
        raise AssertionError(
            f"corruption anchor appears {text.count(old)} times in {relative}: {old!r}"
        )
    write(root, relative, text.replace(old, new))
