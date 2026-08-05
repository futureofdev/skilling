---
paths: packages/**
---

# Python conventions (packages/)

Agreed 2026-08-05. The exceptions are load-bearing design decisions, not loopholes.

- Directories hold at most 7–8 modules or folders; group into subpackages (`course/`,
  `delivery/`, `conformance/`, `codegen/`). Inside a subpackage modules are private
  (`_file.py`); anything used outside it is re-exported through `__init__.py`.
- Files cap at 600–800 lines. At the ceiling, flag it and propose a split.
- Multi-value returns are NamedTuples, never anonymous tuples. Raw dicts only where keys are
  genuinely open (ceremony templates, hook payloads); homogeneous `tuple[X, ...]` is fine.
- BaseModel only at serialization boundaries (course files, records, schema generation);
  interior logic uses frozen dataclasses.
- Categories are StrEnums, never bare strings.
- Constructors are `@classmethod`s (`Course.load`, `Record.new`) — never module-level
  factories or instance methods.
- No `cast`; no `Any` except genuinely open content (hook payloads, JSON-schema documents).
- Never `getattr` to dodge `X | None` — test for None, or declare the attribute in `__init__`.
  Duck-typing an optional method on an external object is legitimate.
- Inline comments ≤2 lines. Docstrings recording spec rationale are exempt and encouraged.
- Tests cover the critical path for incidental code; spec rules keep fixture-per-rule
  (CONTRIBUTING.md — "a rule with no fixture is a rule nobody will notice breaking").

## Exceptions (deliberate)

- `ProgressStore` and `HookSink` stay Protocols: they are conformance seams — a third-party
  implementation must satisfy them without importing this package's classes. ABC elsewhere.
- The delivery core (`delivery/_machine.py` transitions, record transforms in `_runtime.py`)
  stays pure functions: no I/O, no clock, no store. Purity is what makes conformance
  testable. Stateful components (the CLI walker, stores, the dispatcher) are classes.
