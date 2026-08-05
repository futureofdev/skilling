"""Learner-facing delivery: the interactive text walker.

The walker is a Conforming Runtime with no language model in it, which is the proof that
conformance is machinery rather than prose. The JSON transition verbs a skill pack drives —
the same loop, one process per transition — arrive alongside it as their own group.
"""

from ._deliver import deliver

__all__ = ["deliver"]
