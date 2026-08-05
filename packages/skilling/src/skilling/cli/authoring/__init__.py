"""Author-facing commands: check a course, scaffold one, inspect it, compare two versions.

Nothing here touches a learner's record. `show --state` reads one to display a position, which
is the only contact with progress state in this group — and it is a read.
"""

from ._diff import diff
from ._init import init
from ._show import show
from ._today import today
from ._validate import validate

__all__ = ["diff", "init", "show", "today", "validate"]
