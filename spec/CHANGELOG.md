# Specification changelog

All changes to the Skilling specification, including errata. See [CONTRIBUTING](../CONTRIBUTING.md) for the change process and semver rules.

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
