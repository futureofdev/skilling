# skilling

The reference implementation of the [Skilling course format](https://github.com/lhennerley/skilling): typed models, a loader that derives everything structural, a validator with a stable error-code catalogue, the delivery loop as a pure state machine, and a progress store.

**No language model, no agent framework, no API key.** Validating a course in CI or reading a record in a reporting job should not require any of those.

```bash
uvx skilling validate ./my-course     # conformance check
uvx skilling init my-course           # scaffold a conforming skeleton
uvx skilling show ./my-course         # resolved structure and derived counts
uvx skilling deliver ./my-course      # walk the loop
uvx skilling diff ./v1 ./v2           # classify a version bump
```

## Library

```python
from skilling import load_course, validate_course, FileProgressStore
from skilling.machine import LessonShape, start, advance, Input

report = validate_course("./my-course")
if not report.ok:
    for finding in report.errors:
        print(finding.code, finding.location, finding.message)

course = load_course("./my-course")
course.lesson_count  # derived, never authored
course.next_lesson("1.2")
course.is_last_in_phase("1.3")

state = start(LessonShape(has_exercise=True, is_phase_end=False))
state = advance(state, Input.NEXT)  # welcome → objectives
```

`skilling.runtime` holds the completion write set — log first, then record, idempotent by coordinate — so a tutor does not reimplement it and quietly drop a badge.

## Conformance

| Class | Provided by |
|---|---|
| Conforming Course tooling | `skilling validate` |
| Conforming Runtime | `skilling deliver` |
| Conforming Store | `skilling.store.FileProgressStore` |

Licence: Apache-2.0.
