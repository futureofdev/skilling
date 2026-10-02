---
title: Tools for authors
description: What you need installed to write, check and publish a Skilling course.
---

# Tools for authors

You need the same tools as learners, plus a text editor. If you're new to all of this, follow
[install your tools](../learn/install) in the Learn section first. It starts from zero.

| Tool | Why authors need it |
|---|---|
| **Git** | To keep versions of your course and publish it. |
| **uv** | To install Skilling. |
| **Skilling** | To make a starter course, check it, and preview it. |
| **Claude Code or Codex** | To take your own course as a learner would. You can also ask it to help you write. |
| **A text editor** | To write the lesson files. Any editor works. [VS Code](https://code.visualstudio.com/) is free and popular. |
| **A GitHub account** (optional) | The easiest place to publish. Any Git host works. |

Install Skilling:

```bash
uv tool install skilling
skilling --version
```

## Let your assistant help

Claude Code and Codex are good writing partners. Open your course folder in one and ask things
like:

- "Read lesson 1. Is the concept clear enough for a complete beginner?"
- "Suggest three quiz questions for this lesson, with wrong options that are tempting."
- "Run `skilling validate . --strict` and explain any findings."

You stay the author. Check what it writes, especially facts and quiz answers.

## Plain text, by design

Everything in a course is a text file: a `course.yaml` file for the overall shape, and one
markdown (`.md`) file per lesson. **Markdown** is plain text with light formatting: `#` for
headings, `-` for bullet points, `**bold**` for bold. If you've written a README or a chat
message with asterisks, you already know most of it.

Next: [your first course](first-course).
