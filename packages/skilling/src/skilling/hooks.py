"""Hooks and telemetry: where mechanism ends and policy begins.

Since spec 1.1. A runtime emits named events; an adopter attaches enrolment, dashboards, HR
exports and share campaigns *outside* it. That boundary is the most opinionated rule in the
specification and the reason this stays a format rather than becoming an LMS.

Three properties are load-bearing and all three are tested:

* **Fire-and-forget.** A sink that raises cannot break delivery, and a sink that is *slow*
  cannot delay it either — which is why :class:`ThreadedSink` exists.
* **Consent lives here, not in a sink.** A sink that forgot to check ``opt_in`` must not be
  *able* to leak, so the check happens before any sink is handed an event.
* **Content-free payloads.** Coordinates, numbers, booleans, timestamps. No prose, ever.

No sink in this module talks to a network. The framework phones nobody's home by default; an
HTTP sink is about twenty lines and belongs to the adopter who wants one.
"""

from __future__ import annotations

import contextlib
import json
import queue
import threading
import uuid
from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import Field

from .models import Record, Strict


class EventName(StrEnum):
    LESSON_STARTED = "lesson_started"
    GATE_OPENED = "gate_opened"
    QUIZ_ANSWERED = "quiz_answered"
    LESSON_COMPLETED = "lesson_completed"
    BADGE_AWARDED = "badge_awarded"
    PHASE_COMPLETED = "phase_completed"
    COURSE_COMPLETED = "course_completed"
    HOMEWORK_SUBMITTED = "homework_submitted"


class Event(Strict):
    """One hook event: the shared envelope plus a content-free payload."""

    event: EventName
    occurred_at: datetime
    course_id: str
    course_version: str
    spec_version: str
    learner: str
    """The producer's ``learner_id`` for a first-party sink; the anonymous id for telemetry."""

    payload: dict[str, Any] = Field(default_factory=dict)

    def as_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), separators=(",", ":"), sort_keys=True)


@runtime_checkable
class HookSink(Protocol):
    def emit(self, event: Event) -> None: ...


class NullSink:
    """Explicitly nothing. Useful as a default and as the honest answer to "where does this
    go?" when the answer is nowhere."""

    def emit(self, event: Event) -> None:
        return None


class RecordingSink:
    """Keeps events in memory. The obvious test double, and handy in development."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)

    def names(self) -> list[str]:
        return [str(e.event) for e in self.events]


class JsonlSink:
    """Appends one JSON object per line. Readable, greppable, and `jq`-able.

    Point one at a full walk and read the file as if you were the sink operator — it is the
    quickest way to find out what opting in actually exposes.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def emit(self, event: Event) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(event.as_json() + "\n")


class ThreadedSink:
    """Wraps any sink so a slow one cannot delay the delivery loop.

    The queue is bounded and overflow *drops* rather than blocking, because the specification's
    fire-and-forget rule outranks any sink's completeness. Telemetry is directional signal; the
    completion log is the audit trail.
    """

    def __init__(self, sink: HookSink, *, maxsize: int = 256) -> None:
        self.sink = sink
        self.dropped = 0
        self._queue: queue.Queue[Event | None] = queue.Queue(maxsize=maxsize)
        self._thread = threading.Thread(target=self._drain, daemon=True, name="skilling-sink")
        self._thread.start()

    def emit(self, event: Event) -> None:
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            self.dropped += 1

    def _drain(self) -> None:
        while True:
            event = self._queue.get()
            if event is None:
                return
            # A sink's failure is never the loop's problem.
            with contextlib.suppress(Exception):
                self.sink.emit(event)

    def close(self, timeout: float = 2.0) -> None:
        """Drain what is queued, then stop. Best-effort by design."""
        self._queue.put(None)
        self._thread.join(timeout=timeout)


def new_anonymous_id() -> str:
    """A fresh pseudonymous identity for telemetry. Never derived from ``learner_id``."""
    return uuid.uuid4().hex


class Dispatcher:
    """Holds sinks, applies consent, and swallows every failure.

    Two registries, because they answer to different rules. A **first-party** sink stays inside
    the adopter's trust boundary and sees the producer's ``learner_id``. A **telemetry** sink
    leaves it, so it sees an anonymous id and only when the learner has said yes.
    """

    def __init__(
        self,
        first_party: Iterable[HookSink] = (),
        telemetry: Iterable[HookSink] = (),
        *,
        spec_version: str | None = None,
    ) -> None:
        self.first_party = list(first_party)
        self.telemetry = list(telemetry)
        if spec_version is None:
            from .errors import SPEC_MAJOR, SPEC_MINOR

            spec_version = f"{SPEC_MAJOR}.{SPEC_MINOR}"
        self.spec_version = spec_version

    @property
    def active(self) -> bool:
        return bool(self.first_party or self.telemetry)

    def telemetry_allowed(self, record: Record) -> bool:
        """Consent is checked here so a forgetful sink cannot leak.

        An unset anonymous id also blocks emission: with nothing to identify the events by,
        the only honest options are to invent an id or to stay quiet, and staying quiet is the
        one that does not surprise anybody.
        """
        return bool(record.telemetry.opt_in) and bool(record.telemetry.anonymous_id)

    def emit(
        self,
        name: EventName,
        record: Record,
        *,
        occurred_at: datetime,
        **payload: Any,
    ) -> None:
        if not self.active:
            return

        def envelope(learner: str) -> Event:
            return Event(
                event=name,
                occurred_at=occurred_at,
                course_id=record.course_id,
                course_version=record.course_version,
                spec_version=self.spec_version,
                learner=learner,
                payload={k: v for k, v in payload.items() if v is not None},
            )

        if self.first_party:
            self._fan_out(self.first_party, envelope(record.learner_id))
        if self.telemetry and self.telemetry_allowed(record):
            self._fan_out(self.telemetry, envelope(record.telemetry.anonymous_id))

    @staticmethod
    def _fan_out(sinks: list[HookSink], event: Event) -> None:
        for sink in sinks:
            # Fire-and-forget is the whole contract: a raising sink is swallowed here so it
            # can never reach the learner or block a record write.
            with contextlib.suppress(Exception):
                sink.emit(event)

    def close(self) -> None:
        for sink in [*self.first_party, *self.telemetry]:
            closer = getattr(sink, "close", None)
            if callable(closer):
                with contextlib.suppress(Exception):
                    closer()


NO_HOOKS = Dispatcher()
"""A dispatcher with nothing registered. The default everywhere, so hooks are opt-in for a
runtime as well as for a learner."""


def parse_sink(spec: str) -> HookSink:
    """Turn a CLI ``--sink`` argument into a sink. Only local sinks are available by design."""
    kind, _, target = spec.partition(":")
    kind = kind.strip().lower()
    if kind == "null":
        return NullSink()
    if kind == "jsonl":
        if not target:
            raise ValueError("jsonl sink needs a path: --sink jsonl:events.jsonl")
        return JsonlSink(target)
    raise ValueError(f"unknown sink {kind!r}. Available: null, jsonl:<path>")
