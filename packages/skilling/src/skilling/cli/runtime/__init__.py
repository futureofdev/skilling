"""The JSON transition verbs: one process, one transition, one line of stdout.

``_common`` is the shared plumbing every verb in this subpackage is built from — ``Session``,
``ExitCode``, and the open/emit/fail/scratch primitives. ``_session`` is this task's four
verbs (``next``, ``advance``, ``complete``, ``ceremony``); ``_quiz`` adds ``quiz next`` and
``answer`` beside it; later waves add ``_objectives``, ``_homework``, ``_progress``, each
importing the same ``_common`` rather than reinventing session assembly.
"""

from ._common import (
    ExitCode,
    Scratch,
    Session,
    emit,
    fail,
    now_override,
    open_session,
    save_scratch,
)
from ._quiz import answer
from ._quiz import app as quiz
from ._session import advance, ceremony, complete, next

__all__ = [
    "ExitCode",
    "Scratch",
    "Session",
    "advance",
    "answer",
    "ceremony",
    "complete",
    "emit",
    "fail",
    "next",
    "now_override",
    "open_session",
    "quiz",
    "save_scratch",
]
