<!--
  Goes in the repo `futureofdev/.github`, at `profile/README.md`.
  Renders on the organisation landing page, above the repo list.

  This page is Future of Dev's, not Skilling's. It describes the publication and lists
  Skilling among the things it has created. The endorsement runs one way: Future of Dev
  created Skilling; Future of Dev does not own the ecosystem around it.
-->

# Future of Dev

Learn and build the AI-native way. One edition every Thursday — understand what changed,
learn one method, build one thing.

## What we're building in the open

### [Skilling](https://github.com/futureofdev/skilling) — learn with Claude Code or Codex

In 1984 Benjamin Bloom showed that one-to-one tutoring beats classroom teaching by two
standard deviations, and asked how to deliver that at scale. AI tutors are the first credible
answer — but a tutor is only as portable as the course it reads and the record it writes.

Take a course in Claude Code or Codex. The course and the record you earn stay yours,
whichever of those tutors delivered them:

```bash
uv tool install 'skilling==0.5.0'
skilling start 'gh:futureofdev/skilling@v0.5.0#examples/welcome-skilling' my-learning --json
```

Writing courses is the other half. Author in markdown, and any conforming tutor can deliver
it — the specification is CC BY 4.0, the reference implementation Apache-2.0, and the
reference runtime contains no language model, because if a text walker can conform then
conformance binds machinery rather than vibes.

Skilling is governed as its own format. Future of Dev created it and publishes courses in it,
but the specification, the conformance classes and the registry are deliberately
product-neutral. A second implementation from someone we have never met is the point; until
one exists, "standard" is a claim under test.

## Contributing

Specification ambiguities found by people who did not write it are the most useful
contribution there is. Start with
[CONTRIBUTING.md](https://github.com/futureofdev/skilling/blob/main/CONTRIBUTING.md).

---

<sub>futureofdev.com</sub>
