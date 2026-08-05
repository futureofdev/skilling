"""Hooks and telemetry.

Three properties carry the whole design, and each is tested against the rule rather than the
intention: a sink cannot break or delay delivery, consent is enforced where a sink cannot
forget it, and payloads carry no teaching prose.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from skilling import delivery as runtime
from skilling.course import Course, Position, Record, Telemetry
from skilling.delivery import (
    Dispatcher,
    Event,
    EventName,
    JsonlSink,
    NullSink,
    RecordingSink,
    ThreadedSink,
    new_anonymous_id,
    parse_sink,
)
from skilling.store import LOCAL_LEARNER, FileProgressStore

NOW = datetime(2026, 8, 3, 14, 31, 7, tzinfo=UTC)


def a_record(**kwargs) -> Record:
    base = {
        "learner_id": "learner-42",
        "course_id": "clean-course",
        "course_version": "1.0.0",
        "spec_version": "1.1",
        "position": Position(phase=0, lesson=1),
        "started_at": date(2026, 8, 3),
        "last_activity": date(2026, 8, 3),
    }
    return Record(**{**base, **kwargs})


def consented(anonymous_id: str = "anon-1") -> Record:
    return a_record(telemetry=Telemetry(opt_in=True, anonymous_id=anonymous_id))


class RaisingSink:
    def __init__(self) -> None:
        self.calls = 0

    def emit(self, event: Event) -> None:
        self.calls += 1
        raise RuntimeError("this sink is broken")


class SlowSink:
    def __init__(self, delay: float = 5.0) -> None:
        self.delay = delay
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        time.sleep(self.delay)
        self.events.append(event)


# ------------------------------------------------------------------------ fire-and-forget


def test_a_raising_sink_never_reaches_the_caller() -> None:
    broken, good = RaisingSink(), RecordingSink()
    Dispatcher(first_party=[broken, good]).emit(
        EventName.LESSON_STARTED, a_record(), occurred_at=NOW, coordinate="0.1"
    )
    assert broken.calls == 1
    assert good.names() == ["lesson_started"], "a broken sink must not starve the next one"


def test_a_slow_sink_does_not_delay_the_caller() -> None:
    """Fire-and-forget has to survive slowness, not only failure. A sink that takes five
    seconds has stopped the lesson just as effectively as one that raises."""
    slow = SlowSink(delay=5.0)
    threaded = ThreadedSink(slow)

    started = time.perf_counter()
    Dispatcher(first_party=[threaded]).emit(
        EventName.LESSON_STARTED, a_record(), occurred_at=NOW, coordinate="0.1"
    )
    elapsed = time.perf_counter() - started

    assert elapsed < 0.5, f"emitting took {elapsed:.2f}s — the loop was blocked"


def test_a_threaded_sink_drops_rather_than_blocking_when_full() -> None:
    threaded = ThreadedSink(SlowSink(delay=5.0), maxsize=2)
    dispatcher = Dispatcher(first_party=[threaded])

    started = time.perf_counter()
    for n in range(50):
        dispatcher.emit(EventName.QUIZ_ANSWERED, a_record(), occurred_at=NOW, question=n)
    elapsed = time.perf_counter() - started

    assert elapsed < 0.5
    assert threaded.dropped > 0, "overflow must drop, because blocking would stop the lesson"


def test_a_dispatcher_with_no_sinks_does_nothing() -> None:
    dispatcher = Dispatcher()
    assert not dispatcher.active
    dispatcher.emit(EventName.LESSON_STARTED, a_record(), occurred_at=NOW)


def test_null_sink_accepts_everything_and_keeps_nothing() -> None:
    sink = NullSink()
    assert (
        sink.emit(
            Event(
                event=EventName.LESSON_STARTED,
                occurred_at=NOW,
                course_id="c",
                course_version="1.0.0",
                spec_version="1.1",
                learner="x",
            )
        )
        is None
    )


# -------------------------------------------------------------------------------- consent


def test_a_telemetry_sink_gets_nothing_before_the_learner_is_asked() -> None:
    sink = RecordingSink()
    Dispatcher(telemetry=[sink]).emit(
        EventName.LESSON_STARTED, a_record(), occurred_at=NOW, coordinate="0.1"
    )
    assert sink.events == [], "opt_in is None — the learner has not been asked yet"


def test_a_telemetry_sink_gets_nothing_after_a_decline() -> None:
    sink = RecordingSink()
    declined = a_record(telemetry=Telemetry(opt_in=False, anonymous_id="anon-1"))
    Dispatcher(telemetry=[sink]).emit(EventName.LESSON_STARTED, declined, occurred_at=NOW)
    assert sink.events == []


def test_consent_without_an_anonymous_id_emits_nothing() -> None:
    """With nothing to identify events by, the honest options are to invent an id or stay
    quiet. Staying quiet is the one that surprises nobody."""
    sink = RecordingSink()
    record = a_record(telemetry=Telemetry(opt_in=True, anonymous_id=""))
    Dispatcher(telemetry=[sink]).emit(EventName.LESSON_STARTED, record, occurred_at=NOW)
    assert sink.events == []


def test_a_telemetry_sink_sees_the_anonymous_id_and_never_the_learner_id() -> None:
    sink = RecordingSink()
    Dispatcher(telemetry=[sink]).emit(
        EventName.LESSON_STARTED, consented("anon-xyz"), occurred_at=NOW
    )
    assert [e.learner for e in sink.events] == ["anon-xyz"]
    assert all("learner-42" not in e.as_json() for e in sink.events)


def test_a_first_party_sink_sees_the_learner_id_and_needs_no_consent() -> None:
    """A first-party sink stays inside the adopter's boundary; it is their own data."""
    sink = RecordingSink()
    Dispatcher(first_party=[sink]).emit(EventName.LESSON_STARTED, a_record(), occurred_at=NOW)
    assert [e.learner for e in sink.events] == ["learner-42"]


def test_consent_is_enforced_by_the_dispatcher_not_the_sink() -> None:
    """A sink that forgets to check opt_in must not be *able* to leak."""
    forgetful = RecordingSink()
    dispatcher = Dispatcher(telemetry=[forgetful])
    assert not dispatcher.telemetry_allowed(a_record())
    dispatcher.emit(EventName.QUIZ_ANSWERED, a_record(), occurred_at=NOW, question=1)
    assert forgetful.events == []


def test_anonymous_ids_are_fresh_and_not_derived_from_the_learner_id() -> None:
    first, second = new_anonymous_id(), new_anonymous_id()
    assert first != second
    assert "learner" not in first


def test_consent_assigns_an_id_once_and_never_overwrites_it(tmp_path: Path) -> None:
    store = FileProgressStore(tmp_path / "state", learner_id="learner-42")
    record = a_record()
    revision = store.put_record(record, None)

    record, revision = runtime.set_telemetry_consent(store, record, revision, True)
    assigned = record.telemetry.anonymous_id
    assert assigned

    record, revision = runtime.set_telemetry_consent(store, record, revision, False)
    assert record.telemetry.opt_in is False
    assert record.telemetry.anonymous_id == assigned, "write-once: an id is never recycled"

    record, _ = runtime.set_telemetry_consent(store, record, revision, True)
    assert record.telemetry.anonymous_id == assigned


# ---------------------------------------------------------------------------- the payload


def test_none_valued_payload_fields_are_dropped() -> None:
    sink = RecordingSink()
    Dispatcher(first_party=[sink]).emit(
        EventName.LESSON_COMPLETED, a_record(), occurred_at=NOW, coordinate="0.1", title=None
    )
    assert sink.events[0].payload == {"coordinate": "0.1"}


def test_every_event_carries_the_full_envelope() -> None:
    sink = RecordingSink()
    Dispatcher(first_party=[sink]).emit(
        EventName.PHASE_COMPLETED, a_record(), occurred_at=NOW, phase=0
    )
    event = sink.events[0]
    assert event.course_id == "clean-course"
    assert event.course_version == "1.0.0"
    assert event.spec_version
    assert event.occurred_at == NOW
    assert event.learner == "learner-42"


# ----------------------------------------------------------------------------------- sinks


def test_jsonl_sink_writes_one_object_per_line(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "events.jsonl"
    sink = JsonlSink(path)
    dispatcher = Dispatcher(first_party=[sink])
    for n in (1, 2, 3):
        dispatcher.emit(EventName.QUIZ_ANSWERED, a_record(), occurred_at=NOW, question=n)

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    assert [json.loads(line)["payload"]["question"] for line in lines] == [1, 2, 3]


@pytest.mark.parametrize(
    ("spec", "kind"),
    [("null", "NullSink"), ("jsonl:/tmp/x.jsonl", "JsonlSink")],
)
def test_parse_sink(spec: str, kind: str) -> None:
    assert type(parse_sink(spec)).__name__ == kind


@pytest.mark.parametrize("spec", ["jsonl", "http://example.com", "kafka:topic"])
def test_parse_sink_refuses_what_it_cannot_build(spec: str) -> None:
    with pytest.raises(ValueError, match="jsonl|unknown sink"):
        parse_sink(spec)


# ------------------------------------------------------- wired into the completion writes


def test_completion_emits_its_events_in_order(tmp_path: Path, clean: Course) -> None:
    store = FileProgressStore(tmp_path / "state")
    sink = RecordingSink()
    dispatcher = Dispatcher(first_party=[sink])

    record, revision = runtime.load_or_create(store, clean, LOCAL_LEARNER, now=NOW)
    for coordinate in ("0.1", "0.2"):
        lesson = clean.lesson_at(coordinate)
        assert lesson
        outcome = runtime.complete_lesson(
            store, clean, record, revision, lesson, now=NOW, hooks=dispatcher
        )
        record, revision = outcome.record, outcome.revision

    assert sink.names() == [
        "lesson_completed",
        "badge_awarded",
        "lesson_completed",
        "phase_completed",
    ]


def test_an_idempotent_completion_emits_nothing(tmp_path: Path, clean: Course) -> None:
    store = FileProgressStore(tmp_path / "state")
    sink = RecordingSink()
    dispatcher = Dispatcher(first_party=[sink])

    record, revision = runtime.load_or_create(store, clean, LOCAL_LEARNER, now=NOW)
    lesson = clean.lesson_at("0.1")
    assert lesson
    outcome = runtime.complete_lesson(
        store, clean, record, revision, lesson, now=NOW, hooks=dispatcher
    )
    before = len(sink.events)

    runtime.complete_lesson(
        store, clean, outcome.record, outcome.revision, lesson, now=NOW, hooks=dispatcher
    )
    assert len(sink.events) == before, "a revisit is not a completion, so it is not an event"


def test_a_broken_sink_leaves_the_record_correct(tmp_path: Path, clean: Course) -> None:
    """The record write outranks every sink. Nothing a sink does may change what is stored."""
    store = FileProgressStore(tmp_path / "state")
    dispatcher = Dispatcher(first_party=[RaisingSink()], telemetry=[RaisingSink()])

    record, revision = runtime.load_or_create(store, clean, LOCAL_LEARNER, now=NOW)
    record, _ = runtime.set_telemetry_consent(store, record, revision, True)
    found = store.get_record(LOCAL_LEARNER, clean.id)
    assert found
    record, revision = found

    lesson = clean.lesson_at("0.1")
    assert lesson
    outcome = runtime.complete_lesson(
        store, clean, record, revision, lesson, now=NOW, hooks=dispatcher
    )

    assert outcome.record.completed == ["0.1"]
    reread = store.get_record(LOCAL_LEARNER, clean.id)
    assert reread and reread[0].completed == ["0.1"]
    assert [e.coordinate for e in store.get_log(LOCAL_LEARNER, clean.id)] == ["0.1"]
