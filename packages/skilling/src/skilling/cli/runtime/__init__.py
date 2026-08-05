"""The JSON transition verbs: one process, one transition, one line of stdout.

``_common`` is the shared plumbing every verb in this subpackage is built from — ``Session``,
``ExitCode``, and the open/emit/fail/scratch primitives. ``_session`` is this task's four
verbs (``next``, ``advance``, ``complete``, ``ceremony``); later waves add ``_quiz``,
``_objectives``, ``_homework``, ``_progress`` beside it, each importing the same ``_common``
rather than reinventing session assembly.
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
from ._session import advance, ceremony, complete, next

__all__ = [
    "ExitCode",
    "Scratch",
    "Session",
    "advance",
    "ceremony",
    "complete",
    "emit",
    "fail",
    "next",
    "now_override",
    "open_session",
    "save_scratch",
]
