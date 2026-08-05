"""Producer-facing packaging: fetch a course, pack it, install the pack.

Nothing here validates a learner's progress. ``fetch`` is the only member so far — it turns
a ref into a validated, cached course directory that every other command's ``--course``
argument can point at.
"""

from ._fetch import fetch

__all__ = ["fetch"]
