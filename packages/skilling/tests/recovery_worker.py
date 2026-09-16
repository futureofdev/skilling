"""Test-only real-I/O completion worker; never installed as a CLI feature."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

from skilling.course import Course
from skilling.delivery import _completion, complete_lesson
from skilling.store import FileProgressStore, _journal


def utc_storage_test_day(zone: str, now: datetime | None = None) -> date:
    assert zone == "UTC", "storage-native fixtures must not exercise named timezones"
    assert now is not None and now.tzinfo is not None
    return now.astimezone(UTC).date()


def boundary_for(path: Path, data: bytes) -> str:
    if path.name == "completion.yaml":
        return yaml.safe_load(data)["kind"]
    return {
        "completed.yaml": "log",
        "record.yaml": "record",
        "active.yaml": "homework",
        "scratch.yaml": "runtime-state",
    }[path.name]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["complete", "read"])
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--course", type=Path)
    parser.add_argument("--course-id", default="hello-skilling")
    parser.add_argument("--coordinate", default="1.3")
    parser.add_argument("--now", default="2026-08-03T23:59:59+00:00")
    parser.add_argument("--exit-after")
    parser.add_argument("--hold-marker", type=Path)
    parser.add_argument("--calendar", choices=["utc-storage-test"])
    args = parser.parse_args()
    if args.calendar:
        _completion.today_in = utc_storage_test_day
    store = FileProgressStore(args.state)
    if args.action == "complete":
        assert args.course is not None
        course = Course.load(args.course)
        found = store.get_record("local", course.id)
        assert found is not None
        lesson = course.lesson_at(args.coordinate)
        assert lesson is not None
        writer = _journal._write_bytes_atomic

        def write(path: Path, data: bytes) -> None:
            writer(path, data)
            if boundary_for(path, data) == args.exit_after:
                if args.hold_marker:
                    args.hold_marker.write_text("ready", encoding="utf-8")
                    while True:
                        time.sleep(0.05)
                os._exit(73)

        _journal._write_bytes_atomic = write
        outcome = complete_lesson(
            store, course, *found, lesson, now=datetime.fromisoformat(args.now)
        )
        print(
            json.dumps(
                {"revision": outcome.revision, "already_completed": outcome.already_completed}
            )
        )
    else:
        found = store.get_record("local", args.course_id)
        assert found is not None
        slot, _ = store.get_homework("local", args.course_id)
        receipt = store.get_completion_receipt("local", args.course_id)
        print(
            json.dumps(
                {
                    "record": found[0].model_dump(mode="json"),
                    "revision": found[1],
                    "log": [
                        e.model_dump(mode="json") for e in store.get_log("local", args.course_id)
                    ],
                    "slot": slot.model_dump(mode="json") if slot else None,
                    "completed_at": receipt.completed_at.isoformat() if receipt else None,
                    "runtime_state": store.read_runtime_state(args.course_id).decode("utf-8"),
                }
            )
        )


if __name__ == "__main__":
    main()
