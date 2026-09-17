"""The delivery loop: the pure state machine, the record write set, ceremony copy, and hooks.

Depends on ``course`` (a lesson, resolved, is what a beat delivers) and on ``store`` (the
write set persists through it), and — eagerly, at import time — on ``conformance`` for the
spec version it stamps onto every record and event. That last edge is safe only because
``conformance`` never imports this package back at its own import time; see
``conformance._validate._check_ceremony`` for the deferred import that keeps it that way.
"""

from ..course import next_streak, today_in, utc_now
from ._ceremony import (
    DERIVED_PLACEHOLDERS,
    PLACEHOLDERS,
    assemble,
    facts,
    placeholders_in,
    render,
    share_text,
    tags,
    unknown_placeholders,
    values,
)
from ._chronology import ChronologyInvalid, CoordinateRequired, completed_coordinate
from ._completion import (
    CompletionOutcome,
    assignment_from_lesson,
    complete_lesson,
    skills_for,
)
from ._hooks import (
    NO_HOOKS,
    Dispatcher,
    Event,
    EventName,
    HookSink,
    JsonlSink,
    NullSink,
    RecordingSink,
    ThreadedSink,
    new_anonymous_id,
    parse_sink,
)
from ._machine import (
    Beat,
    IllegalTransition,
    Input,
    LessonShape,
    LessonState,
    advance,
    legal_inputs,
    should_offer_revisit,
)
from ._runtime import (
    SPEC_VERSION,
    ObjectivesMarked,
    StoredRecord,
    load_or_create,
    mark_objectives_met,
    objectives_of,
    set_telemetry_consent,
    settle_objective,
    settleable,
    submit_homework,
)

__all__ = [
    "DERIVED_PLACEHOLDERS",
    "NO_HOOKS",
    "PLACEHOLDERS",
    "SPEC_VERSION",
    "Beat",
    "ChronologyInvalid",
    "CompletionOutcome",
    "CoordinateRequired",
    "Dispatcher",
    "Event",
    "EventName",
    "HookSink",
    "IllegalTransition",
    "Input",
    "JsonlSink",
    "LessonShape",
    "LessonState",
    "NullSink",
    "ObjectivesMarked",
    "RecordingSink",
    "StoredRecord",
    "ThreadedSink",
    "advance",
    "assemble",
    "assignment_from_lesson",
    "complete_lesson",
    "completed_coordinate",
    "facts",
    "legal_inputs",
    "load_or_create",
    "mark_objectives_met",
    "new_anonymous_id",
    "next_streak",
    "objectives_of",
    "parse_sink",
    "placeholders_in",
    "render",
    "set_telemetry_consent",
    "settle_objective",
    "settleable",
    "share_text",
    "should_offer_revisit",
    "skills_for",
    "submit_homework",
    "tags",
    "today_in",
    "unknown_placeholders",
    "utc_now",
    "values",
]
