# Examples

Two courses, doing different jobs.

## [`coding-bootcamp`](coding-bootcamp/) — the golden example

Nine phases, 64 lessons, from "I have never installed anything" to a deployed portfolio site. This is the course the whole format was generalised from, and it is the one to read when you want to know what Skilling looks like at real scale.

It exercises every surface the format has:

| | |
|---|---|
| Lessons | 64 across 9 phases, homework at every phase boundary |
| Structured objectives | 235 — 64 knowledge, 171 practice, 22 with a `verify` clause |
| Declared absences | 24 exercise, 12 key terms, 7 next-up — every one with a stated reason |
| Badges | 12 registered, awarded across 11 lessons |
| Ceremony | brand facts, a per-phase highlight, and a literal share template |

```bash
uvx skilling validate examples/coding-bootcamp     # zero findings
uvx skilling show examples/coding-bootcamp         # every count derived
uvx skilling deliver examples/coding-bootcamp      # ~380 keystrokes end to end
```

It is also where format problems surface first. Porting it found a validator too strict about Key Terms, a missing `{hashtags}` placeholder, and guidance that told authors to write phase highlights in the third person when the obvious use is first — see [the changelog](../spec/CHANGELOG.md). That is what a golden example is for: it is the thing that argues back.

**The content is not perfect and is meant to be iterated on.** The port already had to fix seven quiz answers that restated the correct option and gave no reason, and a homework section with no submission line. Expect to find more.

## [`hello-skilling`](hello-skilling/) — learn the format in ten minutes

Three lessons that teach Skilling by being a Skilling course: what a course is, the anatomy of a lesson, the delivery loop. Its homework is to author a conforming course of your own.

Read this one first, and copy from it when you are starting out. It is small enough to hold in your head, which `coding-bootcamp` is not.

```bash
uvx skilling validate examples/hello-skilling
uvx skilling deliver examples/hello-skilling
```

## Which one do the docs use?

The [guides](../docs/authoring-a-course.md) quote `hello-skilling` for snippets, because a three-lesson course makes a legible example. They point at `coding-bootcamp` whenever the question is "but does this hold up on something real?"
