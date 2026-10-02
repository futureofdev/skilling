---
title: Objectives, quizzes and homework
description: How to write objectives a tutor can act on, quizzes that teach, and homework.
---

# Objectives, quizzes and homework

## Objectives

You can write objectives as a plain bullet list under `## Learning Objectives`. Or give them ids
in the frontmatter, so a tutor can aim at a specific one:

```yaml
objectives:
  - id: what-a-terminal-is
    kind: knowledge
    text: Say what the terminal is and why developers use it
    about: [1, 3]
  - id: open-a-terminal
    kind: practice
    text: Open the terminal on your own computer
    verify: A terminal is open and its prompt responds to a command
```

If you use the frontmatter form, leave out the `## Learning Objectives` section. One source of
truth is enough.

There are two kinds:

- **`knowledge`**: something the learner can explain. A tutor checks it in conversation.
- **`practice`**: something the learner does, or a state their machine is in. Only a tutor that
  can look at files, Git or command output can confirm it.

`verify` describes what success looks like in a sentence. You can add a literal `check` command
too, but treat it as a suggestion: the tutor may decline it, and it never runs without the
learner's permission. `about` lists the quiz questions that relate to the objective, so a tutor
can say "that one was about opening a terminal" instead of repeating the whole lesson.

## Quizzes

Every quiz has exactly three questions, each with four options labelled `a)` to `d)`, and an
answer line that gives the right option **and why**:

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

The reason matters most. The tutor reads it out even when the learner guessed right.

A quiz is a checkpoint, not proof. It surfaces confusion, and it never marks an objective as
achieved on its own. After a wrong answer the tutor offers to explain the concept again, and a
wrong answer never blocks a learner from finishing the lesson.

## Homework

Homework belongs on the **last lesson of a phase**, where the tutor delivers it at the phase
boundary. Set `homework: true` on that lesson in the manifest, then add a
`## Homework Assignment` section:

```markdown
## Homework Assignment
### Build Your Profile Page
**Objective:** Put the lesson's HTML into practice on something that's yours.

- [ ] A page using semantic HTML5 elements
- [ ] A heading, a paragraph about you, and a list of three interests

**Stretch Goals:**
- [ ] Add a photo with meaningful alt text

**Submission:** Tell your tutor when it's ready and share the file.
```

Each `- [ ]` requirement gets its own feedback. Stretch goals get feedback too, but never hold a
learner back. The tutor always asks before submitting anything.

The full rules are in the [course format specification](/spec/course-format#section-content).
