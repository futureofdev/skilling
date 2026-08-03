# Specification changelog

All changes to the Skilling specification, including errata. See [CONTRIBUTING](../CONTRIBUTING.md) for the change process and semver rules.

## 1.0.1-draft — 2026-08-03

Editorial only. Fourteen places where the text did not say what it meant, found by handing
[course format](course-format.md) to three readers who had nothing else — no repository, no
example course, no author to ask — and asking each to author a conforming course. All three
courses validated with zero findings, which was the *weak* result; the useful output was the
list of things each of them had to guess.

Two were genuine divergences, where readers made different choices from the same sentence:

- **Whether a phase `overview.md` obeys the lesson section rules.** One reader used `##`
  headings in an overview; two deliberately avoided them, unsure whether the "no other `##`
  headings" rule reached that far. It does not: an overview now explicitly has no constraints
  at all.
- **Whether markdown tables are allowed inside a section.** The list "Prose, code blocks,
  `###` subheadings, lists" read as exhaustive to one reader, who avoided a table that would
  have taught his subject better, while another used one. The list is now stated to be
  illustrative.

Twelve more were unanimous guesses — every reader had to decide, and every reader said so:

- **Phase numbers are not zero-padded**; only lesson numbers are. All three inferred this
  correctly from one example and flagged it as an inference.
- **`## Homework Assignment` is never declared in `sections`.** Its presence is settled by the
  manifest.
- **Registry order applies to optional sections too**, not only required ones.
- **The absence form is exactly `status: none` plus a non-empty `intent`** — a closed
  vocabulary, now stated as one.
- **The last lesson of a course has no `## Next Up`** and nothing for a runtime to generate a
  teaser from. Previously the specification simply stopped short of saying so.
- **A `#` heading is not forbidden**, since only `##` is constrained — but it duplicates the
  frontmatter title, and now says so.
- **A new course starts at `1.0.0`.**
- **Badge ids follow the same rules as the course `id`** — which the validator already
  enforced while the text constrained only uniqueness. A specification narrower than its own
  tool is a specification bug.
- **A registered badge need not be unlocked by any lesson.**
- **Unknown fields are rejected, not ignored** — true of the implementation, unstated in the
  text.
- **The course directory's own name is free** and need not match `id`.
- **The quiz answer line's shape is parsed**, so it is now specified: literal `**Answer:**`,
  label, restated option text, then the reason, wrapping freely.

Two clarifications go further than wording:

- **"Structural count" is now defined.** It means a count of the course's own phases and
  lessons, or of the learner's position among them. A course titled *Three Useful Knots* was
  never in breach, but two readers worried it might be. The rule is also now stated to cover
  `overview.md` and `intent` strings, because a runtime reads those to the learner.
- **"Self-contained" was generalised from a coding course and said so by accident.** A reader
  observed that "nothing outside the lesson" makes any physical-skill exercise impossible,
  since you cannot tie a knot in a markdown file. It means no outside *information*; required
  equipment is fine and should be named.

One finding is not fixed here because it needs new mechanism: a badge is written to the record
when its lesson completes, which can be *before* the learner has done the homework that badge
implies. A reader spotted this independently. It is addressed in 1.1, where the specification
starts distinguishing a completion marker from a capability claim.

## Errata against 1.0.0-draft

Corrections the reference implementation forced. Recorded rather than silently worked
around — a library that quietly disagrees with its own specification is the failure mode
this section exists to prevent.

- **A lesson title ending in `?` inside a `{ … }` flow mapping is not valid YAML.** The
  draft's own full manifest example could not be loaded by any conforming tool. The example
  now quotes the title, and [course format](course-format.md#the-manifest) notes which
  characters need quoting in flow mappings. Found by the round-trip test over every YAML
  example in this specification.
- **Phase completion is derived, not stored.** [Ceremony](runtime.md#phase-boundary-ceremony)
  said a runtime must "mark the phase complete in the record", which contradicted the rule
  that structural facts are never stored. Reworded: completion is computed from the phase's
  lessons and the record's `completed` set, and no field records it.
- **`get_homework_archive` added to the store interface.** The specification required a
  retried submission to return the archived result, but the operation table gave a store no
  way to read its own archive. The read half of `append_homework_archive` is now listed in
  [the store interface](runtime.md#the-store-interface).

## 1.0.0-draft — 2026-08-03

First published draft. Promoted to 1.0.0 once the reference implementation's exit gates are green and `examples/hello-skilling` delivers end to end.

### Added

- **[Course format](course-format.md)** — course directory layout, `course.yaml` manifest, numbering and bijection rules, the no-authored-counts rule, lesson frontmatter, the section registry, declared absence, section content rules, the Quick Quiz grammar (three questions, four options, inline answer with reason), the Homework Assignment grammar, the `assets/` convention, and course-version semantics with coordinate stability.
- **[Runtime](runtime.md)** — scope of conformance (transitions, not prose), the delivery loop and its beats, gates as open waits, declared-absence skips, one-question-at-a-time quiz delivery, remediation, idempotent completion, phase-boundary ceremony, resume, the progress record, the append-only completion log, the streak algorithm, the single-slot homework mailbox, the store interface, and the normative single-learner file layout.
- **[Conformance](README.md#conformance)** — three classes: Conforming Course, Conforming Runtime, Conforming Store.

### Deliberately not bound

Assessed mode, hooks and telemetry, the runtime API, the MCP binding, and skill packs. Each arrives as a minor version once an implementation has exercised it — see [what 1.0 deliberately leaves out](README.md#what-10-deliberately-leaves-out).

### Notes on provenance

This draft generalises a single 64-lesson course delivered through a coding agent. Six defects in that course drove specific rules here; five are retired by 1.0 and one — answer keys held apart from learner-visible content — waits for assessed mode. The table is in [why these constraints exist](README.md#why-these-constraints-exist).

The heavier standards register of the pre-1.0 working draft (per-rule identifiers such as `MAN-004`, RFC-2119 capitals, and a fourth Producer conformance class) was dropped before publication. Stable identifiers now belong to [validator error codes](../docs/error-codes.md), which is where they are actually used.
