# Contributing to Skilling

Skilling's value is stability: courses and runtimes written against it must keep working. Process is deliberately light until a second independent implementation exists, at which point governance grows with the community.

## How a specification change happens

1. **Propose** — open an issue describing the problem the change solves, which conformance classes it touches (Course, Runtime, Store), and whether it is breaking, additive, or editorial.
2. **Review** — discussion on the issue. Maintainers accept, reject, or ask for a draft.
3. **Draft** — a pull request against `spec/`, following the conventions on the existing pages: prose requirements, field tables, good/poor examples, no per-rule identifiers.
4. **Version** — every accepted change lands with a [`spec/CHANGELOG.md`](spec/CHANGELOG.md) entry and a semver decision:
   - **Major** — breaks an existing conforming course, runtime, or store
   - **Minor** — additive and optional
   - **Patch** — editorial only

## Hard rules

- **Error codes are immutable.** A published validator error code is never renamed, renumbered, or reused. To change what a code means, retire it and add a new one. Codes are the stable identifiers people build CI on; see [docs/error-codes.md](docs/error-codes.md).
- **Errata are recorded, not silently fixed.** If an implementation proves the specification wrong, the correction is a CHANGELOG entry — even at patch level. The failure mode to avoid is a library that quietly works around its own specification.
- **Normative text lives only in `spec/`.** Pages under `docs/` explain and motivate. If a `docs/` page contradicts `spec/`, the specification wins and the docs page has a bug.
- **The specification never names a model vendor normatively.** Vendor and framework references, including in the reference implementation, are informative.
- **Nothing binds before something has run it.** A surface no implementation has exercised ships as a documented gap, not as normative text. That is why 1.0 leaves five surfaces out.

## Anything that changes what authors write

A change to [course format](spec/course-format.md) must arrive with:

- The validator change that enforces it, plus a fixture under `packages/skilling/tests/fixtures/`
- A new error code where the change is checkable
- An update to `examples/hello-skilling` if the example is affected

A rule with no fixture is a rule nobody will notice breaking.

## Contributing code

The reference implementation lives in `packages/` under Apache-2.0.

```bash
task test        # every suite
task lint        # ruff check + format --check
task typecheck   # pyright
task schemas     # regenerate schemas/ from the models
```

Committed schemas must be current — `task schemas` producing a diff fails CI.

## Licence of contributions

Specification text is accepted under [CC BY 4.0](spec/LICENSE); everything else under [Apache-2.0](LICENSE).
