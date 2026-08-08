# Examples

Two courses, doing different jobs.

## [`workbench`](workbench/) — every surface, one sitting

A hands-on course — files, folders, and git — built to exercise every surface the format has while staying quick enough to deliver end to end when testing a runtime or a host. Open a terminal, and it is real practice from the first minute.

| | |
|---|---|
| Structured objectives | Both kinds; every lesson carries an observable `practice` objective with a `verify` clause, one carries a literal `check`, and some practice honestly stays a judgement |
| Declared absences | A key-terms absence and a quiet final lesson, each with a stated reason |
| Badges | Registered in the manifest, every one reachable |
| Ceremony | Brand facts, per-phase highlights, and a literal share template with derived counts |
| Homework | At every phase boundary, with per-requirement checkboxes and stretch goals |
| Assets | A relative-path image reference that must resolve |

```bash
uvx skilling validate examples/workbench     # zero findings
uvx skilling show examples/workbench         # every count derived
uvx skilling deliver examples/workbench      # the whole loop, quickly
```

`packages/skilling/tests/test_examples.py` asserts all of the above structurally, so the course cannot quietly stop covering a surface it exists to cover.

The 64-lesson course the format was generalised from — `coding-bootcamp`, nine phases from nothing installed to a deployed portfolio — has moved out of this repository. [The changelog](../spec/CHANGELOG.md) still records what porting it taught the format; arguing back is what a course at scale is for.

## [`hello-skilling`](hello-skilling/) — learn the format in ten minutes

Three lessons that teach Skilling by being a Skilling course: what a course is, the anatomy of a lesson, the delivery loop. Its homework is to author a conforming course of your own.

Read this one first, and copy from it when you are starting out. It is small enough to hold in your head.

```bash
uvx skilling validate examples/hello-skilling
uvx skilling deliver examples/hello-skilling
```

## Which one do the docs use?

The [guides](../docs/authoring-a-course.md) quote `hello-skilling` for snippets, because a three-lesson course makes a legible example. They point at `workbench` when the question is "what does the whole surface look like in one place?"
