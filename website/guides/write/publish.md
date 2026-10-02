---
title: Publish and share
description: Tag a release, test the start command, and tell learners how to begin.
---

# Publish and share

## Put it in Git and tag it

Commit your course to a Git repository. It can sit at the root, or in a subfolder if you use
GitHub. Tag the commit you've reviewed:

```bash
git tag v1.0.0
git push origin v1.0.0
```

## Test the exact command learners will run

Start it from a clean folder, the way a stranger would:

```bash
skilling start 'gh:you/your-repo@v1.0.0#courses/my-course' clean-preview --json
```

Leave off `#courses/my-course` if the course is at the root of the repository. A full commit
works in place of the tag. Don't advertise a branch as if it were fixed, and don't offer a ZIP
download as a source, because Skilling doesn't fetch those.

## Write a README for learners

Say what the course teaches, who it's for, what they need first, how to start, and where to get
help. Include the tested start command and a licence for the content. Then add the badge:

```markdown
[![built with Skilling](https://raw.githubusercontent.com/futureofdev/skilling/main/brand/assets/github/badges/built-with-skilling.svg)](https://github.com/futureofdev/skilling)
```

## Shipping updates

Bump `version` for every change, even a typo fix. Skilling refuses different content that
claims a version a learner already has. Learners can then move up with
`skilling upgrade --course <id>` or `/upgrade-skilling`, keeping their progress through patch
and minor releases.

The [authoring reference](https://github.com/futureofdev/skilling/blob/main/docs/authoring-a-course.md)
has the full checklist.
