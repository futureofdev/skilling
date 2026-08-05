"""Conformance: the error-code catalogue and the validator that emits it.

Depends on ``course`` (it inspects manifests and lessons) and, at call time only, on
``delivery`` (ceremony placeholder checks) — never at import time, which would close a
cycle back through ``delivery``'s own dependency on this package for the spec version.
"""

from ._errors import CATALOGUE, SPEC_MAJOR, SPEC_MINOR, Code, Severity
from ._validate import Finding, Report, validate_course

__all__ = [
    "CATALOGUE",
    "SPEC_MAJOR",
    "SPEC_MINOR",
    "Code",
    "Finding",
    "Report",
    "Severity",
    "validate_course",
]
