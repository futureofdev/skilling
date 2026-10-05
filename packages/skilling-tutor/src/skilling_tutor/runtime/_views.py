"""Safe copied state and deterministic interpretation of explicit learner controls."""

from __future__ import annotations

import re
from dataclasses import asdict

from skilling.delivery import Beat, Input
from skilling.session import SessionSnapshot


def snapshot_view(snapshot: SessionSnapshot) -> dict[str, object]:
    return {
        "course": asdict(snapshot.course),
        "position": {**asdict(snapshot.position), "coordinate": snapshot.position.coordinate},
        "revision": snapshot.revision,
        "beat": {"name": str(snapshot.beat.name), **snapshot.beat.content()},
        "legal_inputs": [str(choice) for choice in snapshot.legal_inputs],
        "completed_count": snapshot.completed_count,
        "lesson_count": snapshot.lesson_count,
    }


def controls(snapshot: SessionSnapshot) -> list[dict[str, str]]:
    if snapshot.pending_feedback is not None or snapshot.completed_count == snapshot.lesson_count:
        return []
    if snapshot.beat.name is Beat.QUIZ and snapshot.beat.question is not None:
        return [
            {
                "id": f"answer-{o.label}",
                "label": f"{o.label}) {o.text}",
                "operation": "answer",
                "payload": o.label,
            }
            for o in snapshot.beat.question.options
        ]
    if snapshot.beat.name is Beat.COMPLETE:
        return [
            {"id": "complete", "label": "Complete lesson", "operation": "complete", "payload": ""}
        ]
    if snapshot.beat.name is Beat.CEREMONY:
        return []
    return [
        {
            "id": str(choice),
            "label": "Continue"
            if choice is Input.NEXT
            else str(choice).replace("-", " ").capitalize(),
            "operation": "advance",
            "payload": str(choice),
        }
        for choice in snapshot.legal_inputs
        if choice not in (Input.ANSWER_CORRECT, Input.ANSWER_WRONG)
    ]


def chat_control(message: str, snapshot: SessionSnapshot) -> str | None:
    text = " ".join(message.lower().replace("’", "'").split()).rstrip(".! ")
    offered = controls(snapshot)
    # Pasted button text has the same meaning as that currently offered control.
    # Match the whole label: questions, quotations, and explanations remain dialogue.
    for control in offered:
        label = " ".join(control["label"].lower().replace("’", "'").split()).rstrip(".! ")
        if text == label:
            return control["id"]
    readiness = re.fullmatch(
        r"(?:(?:nothing(?: else)?|no(?: more)? questions)[,;]? )?"
        r"(?:please |yes,? )?(?:continue|move on|next|go on|carry on|proceed|"
        r"ready|i am ready|i'm ready|let's (?:continue|move on|proceed))(?: please)?",
        text,
    )
    if readiness:
        choices = {
            Beat.WELCOME: Input.NEXT,
            Beat.OBJECTIVES: Input.NEXT,
            Beat.CONCEPT: Input.NEXT,
            Beat.EXERCISE: Input.NEXT,
            Beat.GATE_CONCEPT: Input.PROCEED,
            Beat.REMEDIATE: Input.CONTINUE,
            Beat.COMPLETE: "complete",
        }
        choice = choices.get(snapshot.beat.name) if isinstance(snapshot.beat.name, Beat) else None
        return next((c["id"] for c in offered if c["id"] == choice), None)
    if snapshot.beat.name is Beat.GATE_EXERCISE:
        attempted = re.fullmatch(
            r"(?:i(?:'ve| have)? (?:tried|attempted)(?: (?:it|the exercise))?|"
            r"i(?:'ve| have) done (?:it|the exercise)|i did (?:it|the exercise)|attempted)"
            r"(?:[,;]? (?:let's |please )?(?:continue|move on|proceed))?",
            text,
        )
        if attempted:
            return next((c["id"] for c in offered if c["id"] == Input.ATTEMPTED), None)
    if snapshot.beat.name is Beat.QUIZ:
        answer = re.fullmatch(r"(?:(?:my answer is|i choose|answer|option) )?([a-z])\)?", text)
        if answer:
            return next((c["id"] for c in offered if c["payload"].lower() == answer[1]), None)
    return None
