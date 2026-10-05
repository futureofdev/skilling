"""Provider-free application journeys exercise actual state and streamed native capabilities."""

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from installed_child import policy_model
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ModelRequest, ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from skilling.course import parse_lesson, parse_quiz
from skilling.delivery import Beat
from skilling_tutor import Evidence, Tutor, TutorEventType, TutorSessionError

ROOT = Path(__file__).resolve().parents[3]


def loaded(messages, name="load_capability"):
    return any(
        isinstance(part, ToolReturnPart) and part.tool_name == name
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
    )


async def model_stream(messages, info):
    if not loaded(messages):
        yield {0: DeltaToolCall(name="load_capability", json_args='{"id":"learn"}')}
    else:
        yield "A useful "
        yield "explanation."


def tutor_at(tmp_path, *, stream=model_stream, **kwargs):
    return Tutor(
        agent=Agent(FunctionModel(stream_function=stream)),
        courses={
            "hello": ROOT / "examples/hello-skilling",
            "welcome": ROOT / "examples/welcome-skilling",
        },
        state_dir=tmp_path / "state",
        **kwargs,
    )


def decoded(value):
    return json.loads(json.dumps(value))


async def collect(session, message="Hello", **kwargs):
    events = [event async for event in session.stream(message, **kwargs)]
    assert not any(e.type == "error" for e in events), events
    return decoded(events[-1].state)


def test_native_incremental_stream_preserves_producer_agent_and_dependencies(tmp_path):
    @dataclass
    class ProducerDeps:
        prefix: str

    observed = []
    gate = asyncio.Event()

    async def stream(messages, info):
        observed.append(info)
        if not loaded(messages):
            yield {0: DeltaToolCall(name="load_capability", json_args='{"id":"learn"}')}
        elif not loaded(messages, "application_example"):
            yield {0: DeltaToolCall(name="application_example", json_args="{}")}
        else:
            yield "first "
            await gate.wait()
            yield "second"

    agent = Agent(
        FunctionModel(stream_function=stream),
        deps_type=ProducerDeps,
        instructions="PRODUCER_STYLE",
        model_settings={"temperature": 0.25},
    )

    @agent.tool
    def application_example(ctx: RunContext[ProducerDeps]) -> str:
        return ctx.deps.prefix + " example"

    tutor = Tutor(
        agent=agent,
        courses={"hello": ROOT / "examples/hello-skilling"},
        state_dir=tmp_path,
        deps_factory=lambda learner, course: ProducerDeps(learner),
    )

    async def run():
        session = tutor.session(learner_id="alice", course="hello")
        events = session.stream("teach", request_id="one")
        first = await anext(events)
        assert first.type == "text-delta" and first.text == "first "
        assert session._messages == [{"role": "learner", "text": "teach"}]
        gate.set()
        rest = [e async for e in events]
        assert decoded(rest[-1].state)["messages"][-1]["text"] == "first second"
        assert decoded(rest[-1].state)["continuation"] is None
        acknowledged = await session.acknowledge(decoded(rest[-1].state)["display_id"])
        assert acknowledged["continuation"]
        assert tutor.agent is agent
        assert all("PRODUCER_STYLE" in info.instructions for info in observed)
        assert "application_example" in {t.name for t in observed[0].function_tools}
        assert agent.model_settings == {"temperature": 0.25}

    asyncio.run(run())


def test_scoped_state_is_opaque_alias_isolated_and_durable(tmp_path):
    tutor = tutor_at(tmp_path)
    a = tutor.session(learner_id="../../ALICE_SECRET", course="hello")
    b = tutor.session(learner_id="bob", course="hello")
    c = tutor.session(learner_id="../../ALICE_SECRET", course="welcome")
    assert tutor.session(learner_id="../../ALICE_SECRET", course="hello") is a

    async def run():
        state = decoded(await a.state())
        await collect(a, "continue", request_id="advance", display_id=state["display_id"])
        assert a.service.snapshot().beat.name is Beat.OBJECTIVES
        assert b.service.snapshot().beat.name is Beat.WELCOME
        assert c.service.snapshot().beat.name is Beat.WELCOME
        restarted = tutor_at(tmp_path).session(learner_id="../../ALICE_SECRET", course="hello")
        assert restarted.service.snapshot() == a.service.snapshot()
        assert (decoded(await restarted.state()))["messages"] == []
        with pytest.raises(TutorSessionError):
            await restarted.acknowledge(state["display_id"])

    asyncio.run(run())
    assert all("ALICE_SECRET" not in str(path) for path in tmp_path.rglob("*"))


def test_acknowledged_presentation_continues_once_and_stops_silently_at_gate(tmp_path):
    async def run():
        session = tutor_at(tmp_path).session(learner_id="a", course="hello")
        state = await collect(session, request_id="start")
        old_display = state["display_id"]
        events = []
        for index in range(3):
            state = decoded(await session.acknowledge(state["display_id"]))
            continuation = state["continuation"]["id"]
            events = [
                event
                async for event in session.stream(
                    "", request_id=f"continue-{index}", continuation_id=continuation
                )
            ]
            state = decoded(events[-1].state)
        assert state["snapshot"]["beat"]["name"] == "gate-concept"
        assert len(events) == 1 and events[0].type == "state"
        assert state["continuation"] is None
        repeated = await session.acknowledge(old_display)
        assert repeated["continuation"] is None
        with pytest.raises(TutorSessionError):
            await collect(session, "continue", request_id="stale", display_id=old_display)
        state = await collect(
            session, "continue", request_id="ready", display_id=state["display_id"]
        )
        assert state["snapshot"]["beat"]["name"] == "exercise"

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["exception", "cancel"])
def test_commit_survives_failed_or_cancelled_model_retry_does_not_reapply(tmp_path, failure):
    healthy = False

    async def stream(messages, info):
        if not healthy:
            if failure == "cancel":
                raise asyncio.CancelledError()
            raise RuntimeError("SECRET_PROVIDER_CREDENTIAL")
        async for chunk in model_stream(messages, info):
            yield chunk

    async def run():
        nonlocal healthy
        session = tutor_at(tmp_path, stream=stream).session(learner_id="a", course="hello")
        initial = decoded(await session.state())
        kwargs = dict(request_id="one", display_id=initial["display_id"])
        if failure == "cancel":
            with pytest.raises(asyncio.CancelledError):
                await collect(session, "continue", **kwargs)
        else:
            events = [e async for e in session.stream("continue", **kwargs)]
            assert events[-1].type == "error"
            assert "SECRET" not in repr(events[-1])
            assert (await session.acknowledge(decoded(events[-1].state)["display_id"]))[
                "continuation"
            ] is None
        committed = session.service.snapshot()
        assert committed.beat.name is Beat.OBJECTIVES
        healthy = True
        recovered = await collect(session, "continue", **kwargs)
        assert session.service.snapshot() == committed
        assert len([m for m in recovered["messages"] if m["role"] == "learner"]) == 1
        await collect(session, "continue", **kwargs)
        assert session.service.snapshot() == committed
        with pytest.raises(TutorSessionError, match="different input"):
            await collect(session, "other", **kwargs)

    asyncio.run(run())


def test_rejected_draft_stream_resets_and_cannot_acknowledge_progress(tmp_path):
    agent = Agent(FunctionModel(stream_function=model_stream), retries=1)
    validations = 0

    @agent.output_validator
    def reject_first(text: str) -> str:
        nonlocal validations
        validations += 1
        if validations == 1:
            raise ModelRetry("Try again")
        return text

    tutor = Tutor(
        agent=agent, courses={"hello": ROOT / "examples/hello-skilling"}, state_dir=tmp_path
    )

    async def run():
        session = tutor.session(learner_id="a", course="hello")
        events = [event async for event in session.stream("hi", request_id="one")]
        assert any(event.type == "text-reset" for event in events)
        assert [e.type for e in events].count(TutorEventType.STATE) == 1
        assert session.service.snapshot().beat.name is Beat.WELCOME
        assert len(decoded(events[-1].state)["messages"]) == 2

    asyncio.run(run())


async def walk(session, *, until=None):
    for index in range(160):
        state = decoded(await session.state())
        snapshot = session.service.snapshot()
        if until and until(snapshot):
            return state
        if state["course_complete"]:
            return state
        if state["feedback"]:
            feedback = snapshot.pending_feedback
            assert feedback is not None
            assert state["feedback"]["reason"] == feedback.reason
            state = decoded(await session.acknowledge(state["display_id"]))
            assert state["feedback"] is None
            continue
        if snapshot.beat.name is Beat.QUIZ:
            lesson = session.course.lesson_at(snapshot.position.coordinate)
            assert lesson is not None
            quiz = parse_lesson(lesson.path).section("quiz")
            assert quiz is not None
            question = parse_quiz(quiz.body, quiz.body_line)[snapshot.position.question_index or 0]
            assert question.answer_label is not None
            control = "answer-" + question.answer_label
        else:
            offered = {c["id"] for c in state["controls"]}
            control = next(
                c for c in ("next", "proceed", "attempted", "continue", "complete") if c in offered
            )
        state = await collect(
            session,
            control,
            request_id=f"walk-{index}",
            display_id=state["display_id"],
            control=control,
        )
    raise AssertionError("journey did not finish")


@pytest.mark.parametrize("course", ["hello", "welcome"])
def test_generic_course_quizzes_completion_and_restart(tmp_path, course):
    async def run():
        session = tutor_at(tmp_path).session(learner_id="a", course=course)
        state = await walk(session)
        assert state["course_complete"] and not state["controls"]
        assert state["celebration"]["course_complete"]
        restored = tutor_at(tmp_path).session(learner_id="a", course=course)
        assert (decoded(await restored.state()))["course_complete"]
        assert (decoded(await restored.state()))["controls"] == []

    asyncio.run(run())


def test_quiz_feedback_is_durable_canonical_and_requires_current_ack(tmp_path):
    async def run():
        session = tutor_at(tmp_path).session(learner_id="a", course="hello")
        state = await walk(session, until=lambda s: s.beat.name is Beat.QUIZ)
        events = [
            e
            async for e in session.stream("a", request_id="answer", display_id=state["display_id"])
        ]
        assert len(events) == 1
        state = decoded(events[0].state)
        pending = session.service.snapshot().pending_feedback
        assert pending is not None and state["feedback"]["reason"] == pending.reason
        assert not state["controls"]
        new = tutor_at(tmp_path).session(learner_id="a", course="hello")
        recovered = decoded(await new.state())
        assert recovered["feedback"]["reason"] == pending.reason
        await new.acknowledge(recovered["display_id"])
        assert new.service.snapshot().pending_feedback is None
        await new.acknowledge(recovered["display_id"])
        assert new.service.snapshot().pending_feedback is None

    asyncio.run(run())


def test_review_requires_display_and_rechecks_actual_work(tmp_path):
    evidence = Evidence(
        "Actual inspected learner work", "v1", "Inspected saved work", "application"
    )

    async def observe(learner, course, snapshot):
        return evidence

    async def run():
        nonlocal evidence
        tutor = tutor_at(
            tmp_path,
            evidence_provider=observe,
            review_agent=Agent(
                policy_model(
                    custom_output_args={
                        "objectives": [
                            {
                                "id": "describe-the-learning-loop",
                                "verdict": "supported",
                                "reason": "Explanation supplies each part",
                            },
                            {
                                "id": "choose-a-helpful-adjustment",
                                "verdict": "supported",
                                "reason": "Actual explanation identifies the adjustment",
                            },
                        ]
                    }
                )
            ),
        )
        session = tutor.session(learner_id="a", course="welcome")
        state = await session.review(
            "objectives", "Explain, question, revisit; change the example for a gap."
        )
        review_id = decoded(state)["review"]["id"]
        with pytest.raises(TutorSessionError, match="Render"):
            await session.confirm_review(review_id, "describe-the-learning-loop")
        await session.acknowledge_review(review_id)
        evidence = Evidence("Changed work", "v2")
        with pytest.raises(TutorSessionError, match="changed or expired"):
            await session.confirm_review(review_id, "describe-the-learning-loop")

    asyncio.run(run())


def test_capacity_and_lock_timeout_are_bounded(tmp_path):
    tutor = tutor_at(tmp_path, max_sessions=1, lock_timeout=0.01)
    session = tutor.session(learner_id="a", course="hello")
    with pytest.raises(TutorSessionError, match="capacity"):
        tutor.session(learner_id="b", course="hello")

    async def run():
        async with session._lock:
            with pytest.raises(TutorSessionError, match="still running"):
                decoded(await session.state())

    asyncio.run(run())


def test_one_displayed_review_can_confirm_each_objective_once(tmp_path):
    async def run():
        items = [
            {"id": identity, "verdict": "supported", "reason": "Actual explanation supports it"}
            for identity in ("describe-the-learning-loop", "choose-a-helpful-adjustment")
        ]
        tutor = tutor_at(
            tmp_path, review_agent=Agent(policy_model(custom_output_args={"objectives": items}))
        )
        session = tutor.session(learner_id="a", course="welcome")
        state = decoded(
            await session.review(
                "objectives",
                "I explain a concept, ask a question, then change my example if a gap appears.",
            )
        )
        identity = state["review"]["id"]
        await session.acknowledge_review(identity)
        first = decoded(await session.confirm_review(identity, items[0]["id"]))
        assert first["review"]["id"] == identity
        assert first["review"]["objective_ids"] == [items[1]["id"]]
        revision = session.service.snapshot().revision
        await session.confirm_review(identity, items[0]["id"])
        assert session.service.snapshot().revision == revision
        final = await session.confirm_review(identity, items[1]["id"])
        assert final["review"] is None

    asyncio.run(run())


def test_homework_review_requires_inspected_evidence_and_explicit_submission(tmp_path):
    evidence = Evidence(
        "Actual saved goal and revision after reflection", "v1", "Inspected note", "app"
    )

    async def observe(learner, course, snapshot):
        return evidence

    async def run():
        tutor = tutor_at(tmp_path, evidence_provider=observe)
        session = tutor.session(learner_id="a", course="welcome")
        await walk(session)
        check = session.service.homework_check()
        assert check.active is not None
        slot = check.active
        args = {
            "requirements": [
                {
                    "id": f"{slot.coordinate}/required/{i}",
                    "verdict": "supported",
                    "reason": "Observed work supports this requirement",
                }
                for i, _ in enumerate(slot.requirements, 1)
            ],
            "stretch_goals": [
                {
                    "id": f"{slot.coordinate}/stretch/{i}",
                    "verdict": "not-yet",
                    "reason": "Optional stretch was not attempted",
                }
                for i, _ in enumerate(slot.stretch_goals, 1)
            ],
        }
        tutor.review_agent = Agent(policy_model(custom_output_args=args))
        state = decoded(
            await session.review("homework", "I wrote this goal and revised it after reflection.")
        )
        identity = state["review"]["id"]
        assert session.service.homework_check() == check
        with pytest.raises(TutorSessionError, match="Render"):
            await session.confirm_review(identity)
        await session.acknowledge_review(identity)
        await session.confirm_review(identity)
        assert session.service.homework_check().active is None
        await session.confirm_review(identity)

    asyncio.run(run())


def test_explicit_choices_and_acknowledged_presentation_have_distinct_origins(
    tmp_path, monkeypatch
):
    from skilling.session import ActionOrigin, FileSession

    origins = []
    original = FileSession.act

    def track(service, action):
        origins.append(action.origin)
        return original(service, action)

    monkeypatch.setattr(FileSession, "act", track)

    async def run():
        session = tutor_at(tmp_path).session(learner_id="a", course="hello")
        initial = decoded(await session.state())
        state = await collect(
            session, "continue", request_id="learner", display_id=initial["display_id"]
        )
        state = decoded(await session.acknowledge(state["display_id"]))
        await collect(
            session, "", request_id="presentation", continuation_id=state["continuation"]["id"]
        )
        assert origins == [ActionOrigin.LEARNER, ActionOrigin.PRESENTATION]

    asyncio.run(run())


def test_tool_heavy_history_compacts_to_real_conversation_instead_of_forgetting(tmp_path):
    from pydantic_ai.messages import ModelRequest, UserPromptPart

    observed = []

    async def provider(messages, info):
        observed.append((repr(messages), info.instructions))
        async for chunk in model_stream(messages, info):
            yield chunk

    async def run():
        session = tutor_at(tmp_path, stream=provider).session(learner_id="a", course="welcome")
        session._messages = [
            {"role": "learner", "text": "Let's use soccer as my everyday subject."},
            {"role": "tutor", "text": "Is the attacker offside when the ball is played?"},
            {"role": "learner", "text": "I tried the question and corrected my offside answer."},
        ]
        session._history = [
            ModelRequest(
                parts=[UserPromptPart("Let's use soccer as my everyday subject.")],
                instructions="LARGE_OLD_POLICY " * 18_000,
            )
        ]
        await collect(session, "Explain that a different way", request_id="large")
        compacted = repr(session._history)
        assert "soccer" in compacted and "corrected my offside answer" in compacted
        assert "LARGE_OLD_POLICY" not in compacted
        assert len(compacted) < 200_000
        observed.clear()
        await collect(session, "Nothing else, continue at the same pace", request_id="next")
        assert "soccer" in observed[0][0]
        assert "corrected my offside answer" in observed[0][0]
        assert "recent_conversation" in observed[0][1]

    asyncio.run(run())


def test_existing_empty_history_recovers_from_server_transcript(tmp_path):
    captured = []

    async def provider(messages, info):
        captured.append(repr(messages))
        async for chunk in model_stream(messages, info):
            yield chunk

    async def run():
        session = tutor_at(tmp_path, stream=provider).session(learner_id="a", course="welcome")
        session._messages = [
            {"role": "learner", "text": "My subject is soccer."},
            {"role": "tutor", "text": "Let's work through the offside question together."},
        ]
        assert not session._history
        await collect(session, "What about a defender?", request_id="recover")
        assert "My subject is soccer" in captured[0]
        assert "offside question" in captured[0]

    asyncio.run(run())


def test_controls_present_canonical_quizzes_and_feedback_in_order_without_model(tmp_path):
    model_calls = []

    async def provider(messages, info):
        model_calls.append(info.instructions)
        async for chunk in model_stream(messages, info):
            yield chunk

    async def run():
        session = tutor_at(tmp_path, stream=provider).session(learner_id="a", course="hello")
        state = await walk(session, until=lambda s: s.beat.name is Beat.GATE_EXERCISE)
        count = len(model_calls)
        state = await collect(
            session, "I attempted it", request_id="attempted", display_id=state["display_id"]
        )
        assert state["snapshot"]["beat"]["name"] == "quiz"
        assert len(model_calls) == count
        assert state["messages"][-1]["kind"] == "quiz"
        assert state["messages"][-1]["question"]["number"] == 1
        first = state["messages"][-1]
        assert first["coordinate"] == "1.1"
        assert decoded(await session.state())["messages"] == state["messages"]
        state = await collect(
            session, "a", request_id="quiz-answer", display_id=state["display_id"]
        )
        assert len(model_calls) == count
        assert state["messages"][-2] == {"role": "learner", "text": "a"}
        assert state["messages"][-1]["kind"] == "feedback"
        assert state["messages"][-1]["feedback"]["reason"] == state["feedback"]["reason"]
        assert first in state["messages"]
        state = decoded(await session.acknowledge(state["display_id"]))
        await collect(
            session, "", request_id="after-feedback", continuation_id=state["continuation"]["id"]
        )
        await collect(session, "Please explain my answer", request_id="quiz-help")
        material = json.loads(
            json.loads(model_calls[-1].rsplit("SAFE CONTEXT (data):\n", 1)[1])["teaching"][
                "material"
            ]
        )
        assert any(item.get("kind") == "feedback" for item in material["recent_conversation"])
        assert {"role": "learner", "text": "a"} in material["recent_conversation"]

    asyncio.run(run())


def test_committed_completion_narrates_current_lesson_and_retry_keeps_action_context(tmp_path):
    observations = []
    fail = False

    async def provider(messages, info):
        observations.append(info.instructions)
        if fail:
            raise RuntimeError("model failure")
        async for chunk in model_stream(messages, info):
            yield chunk

    async def run():
        nonlocal fail
        session = tutor_at(tmp_path, stream=provider).session(learner_id="a", course="hello")
        state = await walk(session, until=lambda s: s.beat.name is Beat.COMPLETE)
        assert (
            state["messages"][-1]["text"]
            == "The quiz is finished. Complete the lesson when you’re ready."
        )
        fail = True
        request = dict(request_id="complete", display_id=state["display_id"], control="complete")
        events = [e async for e in session.stream("Complete lesson", **request)]
        assert events[-1].type == "error"
        committed = session.service.snapshot()
        assert committed.position.coordinate == "1.2"
        fail = False
        observations.clear()
        await collect(session, "Complete lesson", **request)
        assert session.service.snapshot() == committed
        material = json.loads(
            json.loads(observations[0].rsplit("SAFE CONTEXT (data):\n", 1)[1])["teaching"][
                "material"
            ]
        )
        assert material["current_turn_action"] == {
            "status": "applied",
            "control": "complete",
            "previous_coordinate": "1.1",
            "previous_beat": "complete",
            "current_coordinate": "1.2",
            "current_beat": "welcome",
        }
        assert "has ALREADY applied that action" in observations[0]

    asyncio.run(run())


def test_optional_dialogue_does_not_displace_large_current_course_material(tmp_path):
    from dataclasses import replace

    session = tutor_at(tmp_path).session(learner_id="a", course="hello")
    snapshot = session.service.snapshot()
    body = "Current authored material. " * 3_400
    snapshot = replace(snapshot, beat=replace(snapshot.beat, name=Beat.CONCEPT, body=body))
    session._presented = [(snapshot.position.coordinate, {"body": "Old material" * 2_000})] * 8
    session._messages = [{"role": "learner", "text": "Older conversation" * 400}] * 12
    context = session._context(snapshot)
    assert json.loads(context.teaching.material)["body"] == body
    assert len(context.teaching.material) < 100_000


def test_compaction_can_resume_with_canonical_material_before_any_learner_text(tmp_path):
    from pydantic_ai.messages import ModelRequest, ModelResponse

    session = tutor_at(tmp_path).session(learner_id="a", course="hello")
    session._messages = [
        {
            "role": "tutor",
            "text": "",
            "kind": "quiz",
            "question": {
                "number": 1,
                "text": "Which?",
                "options": [{"label": "a", "text": "This"}],
            },
        }
    ]
    history = session._conversation_history()
    assert isinstance(history[0], ModelRequest)
    assert isinstance(history[1], ModelResponse)
    assert "not a new learner message or choice" in repr(history[0])
    assert "Which?" in repr(history[1])
