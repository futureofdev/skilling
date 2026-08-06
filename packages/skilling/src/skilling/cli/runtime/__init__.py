"""Read-only cross-course verbs: today, just ``courses``.

Named for the eventual home of the JSON transition verbs (``next``, ``advance``, ``progress``,
...), which are developed on their own in-flight branches and land here later rather than in
this one — see ``_courses.py`` for what this verb resolves, and what it honestly cannot.
"""

from ._courses import courses

__all__ = ["courses"]
