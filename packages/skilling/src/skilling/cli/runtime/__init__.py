"""The JSON transition verbs: one process, one transition, one line of stdout.

``_common`` is the shared plumbing every verb in this subpackage is built from — ``Session``,
``ExitCode``, and the open/emit/fail/scratch primitives. ``_session`` is the four session verbs
(``next``, ``advance``, ``complete``, ``ceremony``); ``_quiz`` adds ``quiz next`` and ``answer``
beside it; ``_objectives`` is the ``objective`` sub-app (``settle``, ``show``); ``_homework`` and
``_progress`` are the record verbs (``homework``, ``progress``, ``telemetry``); ``_courses`` is
the read-only cross-course enumeration verb — each importing the same ``_common`` rather than
reinventing session assembly.
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
from ._courses import courses
from ._homework import homework
from ._objectives import app as objective_app
from ._progress import progress, telemetry
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
    "courses",
    "emit",
    "fail",
    "homework",
    "next",
    "now_override",
    "objective_app",
    "open_session",
    "progress",
    "quiz",
    "save_scratch",
    "telemetry",
]
