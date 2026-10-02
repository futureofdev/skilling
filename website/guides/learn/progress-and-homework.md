---
title: Progress and homework
description: Check how you're doing, and how homework review and submission work.
---

# Progress and homework

## Checking your progress

Ask the tutor "how am I doing?", or type `/progress` in Claude Code or `$progress` in Codex.
You'll see the lessons you've finished, where you are in the course, and your streak.

Those numbers are read from the saved record each time you ask, never estimated from the
conversation. You can see the same information yourself from anywhere inside the learning
folder:

```bash
skilling courses --json
skilling progress --course welcome-skilling
```

## Homework

Some lessons end a phase with homework: a short assignment with a checklist of requirements.

When you get there, the tutor:

1. Shows you the assignment.
2. Looks at what you made and gives feedback on each requirement in turn.
3. Asks whether you want to submit.

Reviewing your work isn't the same as submitting it. Nothing is submitted until you clearly
say so. Stretch goals get feedback too, but they never hold you back.

You can also type `/homework` (or `$homework`) to ask what's due or to get feedback on it.

## Where your work goes

Each course gets its own folder under `showcase/`. That's where your notes, code and anything
else the course asks you to make should live. It's yours: keep it, share it, or put it in Git.

Next: [your workspace](your-workspace).
