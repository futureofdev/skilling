"""Public copied browser values; opaque runtime references remain controller-owned."""

from __future__ import annotations

from dataclasses import asdict

from skilling.delivery import Beat, Input
from skilling.session import SessionSnapshot


def snapshot_view(snapshot: SessionSnapshot) -> dict[str, object]:
    return {
        "course": asdict(snapshot.course),
        "position": asdict(snapshot.position),
        "revision": snapshot.revision,
        "beat": {"name": str(snapshot.beat.name), **snapshot.beat.content()},
        "legal_inputs": [str(choice) for choice in snapshot.legal_inputs],
        "completed_count": snapshot.completed_count,
        "lesson_count": snapshot.lesson_count,
    }


def controls(snapshot: SessionSnapshot) -> list[dict[str, str]]:
    if snapshot.pending_feedback is not None:
        return []
    if snapshot.beat.name is Beat.QUIZ and snapshot.beat.question is not None:
        return [
            {
                "id": f"answer-{option.label}",
                "label": f"{option.label}) {option.text}",
                "operation": "answer",
                "payload": option.label,
            }
            for option in snapshot.beat.question.options
        ]
    if snapshot.beat.name is Beat.COMPLETE:
        return [
            {
                "id": "complete",
                "label": "Complete this lesson",
                "operation": "complete",
                "payload": "",
            }
        ]
    if snapshot.beat.name is Beat.CEREMONY:
        return [
            {
                "id": "ceremony",
                "label": "Continue after celebration",
                "operation": "ceremony",
                "payload": "",
            }
        ]
    return [
        {
            "id": str(choice),
            "label": "Continue after reading"
            if choice is Input.NEXT
            else str(choice).replace("-", " ").capitalize(),
            "operation": "advance",
            "payload": str(choice),
        }
        for choice in snapshot.legal_inputs
        if choice not in (Input.ANSWER_CORRECT, Input.ANSWER_WRONG)
    ]
