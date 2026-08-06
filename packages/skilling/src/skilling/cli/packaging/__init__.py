"""Fetching a course, and installing the bundled skill triad a learner needs to drive one.

``fetch`` turns a ref into a validated, cached course directory that every other command's
``--course`` argument can point at. ``install``/``uninstall`` write the fixed ``learn``/
``progress``/``homework`` triad into a host's Agent-Skills convention — once per learner, not
once per course, so nothing here validates a learner's progress either.
"""

from ._fetch import fetch
from ._install import install, uninstall

__all__ = ["fetch", "install", "uninstall"]
