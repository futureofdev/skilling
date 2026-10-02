---
title: Finding courses
description: The example courses, and every kind of course source Skilling accepts.
---

# Finding courses

## Courses to try

| Course | What you'll learn |
|---|---|
| [Welcome to Skilling](https://github.com/futureofdev/skilling/tree/main/examples/welcome-skilling) | How to learn well with an AI tutor. Start here. |
| [Hello, Skilling](https://github.com/futureofdev/skilling/tree/main/examples/hello-skilling) | How a Skilling course is put together, taught by a tutor |
| [Workbench](https://github.com/futureofdev/skilling/tree/main/examples/workbench) | Hands-on files, folders and Git in the shell |

Course authors usually publish a ready-made `skilling start` command in their course README.
Copy it, run it, and you're set.

## Where courses can come from

**GitHub.** The shorthand can point at a whole repository or at a course in a subfolder, pinned
to a tag or a full commit:

```text
gh:owner/repository
gh:owner/repository@v1.0.0
gh:owner/repository@v1.0.0#courses/my-course
gh:owner/repository@0123456789abcdef0123456789abcdef01234567
```

A tag is easy to read and repeatable. A full commit is the strongest pin. You can leave the pin
off, but then the copy you have won't follow the branch when it changes.

**Any Git repository.** Use an `https://` or `ssh://` URL for a course at the root of a
repository. These don't support the `@pin` or `#subfolder` parts of the GitHub shorthand.

**A folder on your machine.** Any folder with a `course.yaml` in it:

```bash
skilling start ../my-course my-learning --json
```

Skilling doesn't download ZIP files. If a course comes as an archive, extract it yourself and
point Skilling at the folder.

## Private courses

Skilling uses Git, so it uses whatever login Git already has: a credential manager, an SSH key,
or `gh`. There's no separate Skilling login. Never put a password or token in a course
reference.

## Copies, not links

When you start a course, Skilling checks it and saves a copy in your workspace. Lessons are
taught from that copy, so your course keeps working even if the original repository changes or
disappears. To move to a newer version, use `skilling upgrade` (see
[your workspace](your-workspace#updating-skilling-or-a-course)).

The full rules are in the
[course sources reference](https://github.com/futureofdev/skilling/blob/main/docs/course-sources.md).
