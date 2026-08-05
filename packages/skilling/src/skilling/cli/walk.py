"""``skilling deliver`` — a Conforming Runtime with no language model in it.

It walks the real state machine, holds every gate open on real learner input, grades the
quiz from the lesson's inline answer lines, re-presents the concept on a wrong answer, and
writes a real progress record through the file store.

It re-*prints* rather than re-*explains*, and it cannot judge homework. Both are allowed:
the specification binds transitions and record writes, never prose, and offering homework
checks is optional. That is the point of this command existing — if a text walker can
conform, then conformance is machinery rather than vibes.
"""

from __future__ import annotations

from datetime import datetime

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.rule import Rule

from .. import ceremony as cer
from .. import lesson as md
from .. import machine, runtime
from ..hooks import NO_HOOKS, Dispatcher, EventName
from ..loader import Course, ResolvedLesson
from ..machine import Beat, Input, LessonShape, LessonState
from ..models import Record, SectionAbsence
from ..store.protocol import ProgressStore


class LearnerLeft(Exception):
    """Input ended. Not an error: a gate with nobody at it is simply still open."""


class Walker:
    def __init__(
        self,
        course: Course,
        store: ProgressStore,
        *,
        learner_id: str,
        console: Console,
        zone: str = "UTC",
        hooks: Dispatcher = NO_HOOKS,
        ask_consent: bool = True,
    ) -> None:
        self.course = course
        self.store = store
        self.learner_id = learner_id
        self.console = console
        self.zone = zone
        self.hooks = hooks
        self.ask_consent = ask_consent
        self.record: Record
        self.revision: str | None
        self.correct: dict[int, bool] = {}
        """Per-lesson quiz results, keyed by question number. Drives objectives_met."""
        self._outcome: runtime.CompletionOutcome | None = None

    # ------------------------------------------------------------------------ prompts

    def _ask(self, question: str, choices: list[str], default: str | None = None) -> str:
        try:
            return Prompt.ask(question, choices=choices, default=default or choices[0])
        except (EOFError, KeyboardInterrupt) as exc:
            raise LearnerLeft from exc

    def _confirm(self, question: str, *, default: bool = False) -> bool:
        try:
            return Confirm.ask(question, default=default)
        except (EOFError, KeyboardInterrupt) as exc:
            raise LearnerLeft from exc

    def _md(self, text: str) -> None:
        if text.strip():
            self.console.print(Markdown(text))
        self.console.print()

    def _persist_beat(self, beat: Beat) -> None:
        """Record beat-level position, so an interrupted gate resumes as the same gate."""
        if self.record.position.beat == str(beat):
            return
        updated = self.record.model_copy(
            update={"position": self.record.position.model_copy(update={"beat": str(beat)})}
        )
        self.revision = self.store.put_record(updated, self.revision)
        self.record = updated

    # ------------------------------------------------------------------------ telemetry

    def _telemetry_consent(self) -> None:
        """Ask once, on ``null``, with no dark default.

        The honest framing matters more than the wording: the learner is told what is sent,
        that it is anonymous, and that declining costs them nothing — because it does not.
        """
        if not self.ask_consent or not self.hooks.telemetry:
            return
        if self.record.telemetry.opt_in is not None:
            return

        self.console.print("[bold]Share anonymous progress data?[/]")
        self.console.print(
            "[dim]Which lessons you finish and which quiz answers you get right, under a "
            "random id. No names, no messages, nothing you write. It helps whoever wrote "
            "this course see how it is going.\n"
            "Declining changes nothing about the course you get.[/]"
        )
        # default=False: the honest default for a question the learner has not been asked before.
        agreed = self._confirm("Share anonymously?", default=False)
        self.record, self.revision = runtime.set_telemetry_consent(
            self.store, self.record, self.revision, agreed
        )
        self.console.print(
            "[dim]Thank you — sharing anonymously.[/]\n"
            if agreed
            else "[dim]Nothing will be sent.[/]\n"
        )

    # ---------------------------------------------------------------------------- run

    def run(self, *, now: datetime | None = None) -> int:
        self.record, self.revision = runtime.load_or_create(
            self.store, self.course, self.learner_id, zone=self.zone, now=now
        )

        self.console.print(
            Panel(
                f"[bold]{self.course.manifest.title}[/]\n"
                f"[dim]{self.course.completed_count(self.record.completed)} of "
                f"{self.course.lesson_count} lessons behind you · streak "
                f"{self.record.streak_days}[/]",
                border_style="cyan",
            )
        )

        try:
            self._telemetry_consent()
            while True:
                coordinate = self.record.position.coordinate
                lesson = self.course.lesson_at(coordinate)
                if lesson is None:
                    self.console.print(
                        f"[red]The record points at {coordinate}, which is not a lesson in "
                        "this course.[/]"
                    )
                    return 1
                if self.course.completed_count(self.record.completed) >= self.course.lesson_count:
                    self.console.print("[bold green]Course complete.[/] Nothing left to deliver.")
                    return 0

                self.deliver(lesson, now=now)

                if not self._confirm("Continue to the next lesson?", default=True):
                    break
                self.console.print()
        except LearnerLeft:
            self.console.print()
            self.console.print(
                "[dim]Progress saved. Your gate is still open — come back whenever.[/]"
            )
            return 0

        return 0

    # -------------------------------------------------------------------------- lesson

    def deliver(self, lesson: ResolvedLesson, *, now: datetime | None = None) -> None:
        parsed = md.parse_lesson(lesson.path)
        shape = LessonShape(
            has_exercise=parsed.section("exercise") is not None,
            is_phase_end=self.course.is_last_in_phase(lesson.coordinate),
        )

        recorded = self.record.position.beat
        state = (
            LessonState.resume(shape, recorded)
            if recorded and recorded in set(Beat)
            else LessonState.start(shape)
        )

        questions = []
        if quiz := parsed.section("quiz"):
            questions = md.parse_quiz(quiz.body, quiz.body_line)

        self.correct = {}
        while not state.terminal:
            state = self.beat(state, lesson, parsed, questions, now=now)

    def beat(
        self,
        state: LessonState,
        lesson: ResolvedLesson,
        parsed: md.ParsedLesson,
        questions: list[md.QuizQuestion],
        *,
        now: datetime | None = None,
    ) -> LessonState:
        phase = self.course.phase_of(lesson.coordinate)

        moment = now or runtime.utc_now()

        match state.beat:
            case Beat.WELCOME:
                self.console.print(Rule(f"[bold]{lesson.coordinate} — {lesson.title}[/]"))
                self.console.print(f"[dim]Phase {lesson.phase}: {phase.name if phase else ''}[/]\n")
                self.hooks.emit(
                    EventName.LESSON_STARTED,
                    self.record,
                    occurred_at=moment,
                    coordinate=lesson.coordinate,
                )
                return machine.advance(state, Input.NEXT)

            case Beat.OBJECTIVES:
                self._objectives(parsed)
                return machine.advance(state, Input.NEXT)

            case Beat.CONCEPT:
                if section := parsed.section("concept"):
                    self.console.print("[bold]The Concept[/]")
                    self._md(section.body)
                if terms := parsed.section("key_terms"):
                    self.console.print("[bold]Key Terms[/]")
                    self._md(terms.body)
                return machine.advance(state, Input.NEXT)

            case Beat.GATE_CONCEPT:
                self._persist_beat(state.beat)
                self._gate_opened(lesson, state.beat, moment)
                answer = self._ask(
                    "Go deeper on any of that, or move on?", ["deeper", "proceed"], "proceed"
                )
                if answer == "deeper":
                    return machine.advance(state, Input.GO_DEEPER)
                moved = machine.advance(state, Input.PROCEED)
                if moved.beat is Beat.QUIZ and not state.shape.has_exercise:
                    # The exercise beat and its gate are skipped, so the author's stated
                    # reason has to be surfaced here or it is never surfaced at all.
                    self._declared_absence(parsed)
                return moved

            case Beat.EXERCISE:
                if section := parsed.section("exercise"):
                    self.console.print("[bold]Hands-On Exercise[/]")
                    self._md(section.body)
                return machine.advance(state, Input.NEXT)

            case Beat.GATE_EXERCISE:
                self._persist_beat(state.beat)
                self._gate_opened(lesson, state.beat, moment)
                answer = self._ask(
                    "Let me know when you've given it a try, or ask for a hint",
                    ["done", "hint"],
                    "done",
                )
                return machine.advance(state, Input.ATTEMPTED if answer == "done" else Input.HINT)

            case Beat.QUIZ:
                self._persist_beat(state.beat)
                return self._quiz(state, lesson, questions, moment)

            case Beat.REMEDIATE:
                self._persist_beat(state.beat)
                return self._remediate(state, parsed, questions)

            case Beat.COMPLETE:
                return self._complete(state, lesson, now=now)

            case Beat.CEREMONY:
                return self._ceremony(state, lesson, now=now)

            case _:
                return machine.advance(state, Input.NEXT)

    def _gate_opened(self, lesson: ResolvedLesson, beat: Beat, moment: datetime) -> None:
        self.hooks.emit(
            EventName.GATE_OPENED,
            self.record,
            occurred_at=moment,
            coordinate=lesson.coordinate,
            beat=str(beat),
        )

    def _objectives(self, parsed: md.ParsedLesson) -> None:
        """Render objectives from whichever form the lesson used — never both, since the
        format makes them mutually exclusive."""
        fm = parsed.frontmatter
        if fm and fm.objectives:
            self.console.print("[bold]Learning Objectives[/]")
            self.console.print("By the end of this lesson, you will be able to:")
            for objective in fm.objectives:
                self.console.print(f"  • {objective.text}")
            self.console.print()
            return
        if section := parsed.section("objectives"):
            self.console.print("[bold]Learning Objectives[/]")
            self._md(section.body)

    def _declared_absence(self, parsed: md.ParsedLesson) -> None:
        """Surface the author's stated reason in place of the skipped exercise beat."""
        fm = parsed.frontmatter
        declaration = fm.declaration("exercise") if fm else None
        intent = declaration.intent if isinstance(declaration, SectionAbsence) else ""
        if intent:
            self.console.print(f"[dim]No exercise in this lesson — {intent}[/]\n")

    # ---------------------------------------------------------------------------- quiz

    def _quiz(
        self,
        state: LessonState,
        lesson: ResolvedLesson,
        questions: list[md.QuizQuestion],
        moment: datetime,
    ) -> LessonState:
        index = state.question_index
        if index >= len(questions):
            # A malformed quiz should not trap a learner in a lesson they cannot finish.
            self.console.print("[yellow]This lesson's quiz is incomplete; moving on.[/]")
            return machine.advance(state, Input.ANSWER_CORRECT)

        question = questions[index]
        self.console.print(f"[bold]Question {index + 1} of {state.shape.question_count}[/]")
        self.console.print(question.text)
        for option in question.options:
            self.console.print(f"   [cyan]{option.label})[/] {option.text}")
        self.console.print()

        given = self._ask("Your answer", [o.label for o in question.options])
        correct = given == question.answer_label
        # A question re-answered after remediation keeps its first verdict: an objective is
        # demonstrated by getting it right, not by being told the answer and agreeing.
        self.correct.setdefault(question.number, correct)

        self.hooks.emit(
            EventName.QUIZ_ANSWERED,
            self.record,
            occurred_at=moment,
            coordinate=lesson.coordinate,
            question=question.number,
            correct=correct,
        )

        if correct:
            self.console.print(f"[bold green]Correct.[/] {question.answer_reason}\n")
            return machine.advance(state, Input.ANSWER_CORRECT)

        expected = question.answer_label or "?"
        self.console.print(
            f"[bold yellow]Not quite.[/] The answer is [cyan]{expected})[/] — "
            f"{question.answer_reason}\n"
        )
        return machine.advance(state, Input.ANSWER_WRONG)

    def _implicated(
        self, parsed: md.ParsedLesson, state: LessonState, questions: list[md.QuizQuestion]
    ) -> str | None:
        """The objective the question just missed was testing, if the lesson said so.

        This is the payoff for making objectives addressable: naming what went wrong beats
        replaying the whole concept at someone.
        """
        fm = parsed.frontmatter
        if fm is None or not fm.objectives:
            return None
        index = state.question_index
        if index >= len(questions):
            return None
        matched = fm.objectives_for_question(questions[index].number)
        return matched[0].text if matched else None

    def _remediate(
        self, state: LessonState, parsed: md.ParsedLesson, questions: list[md.QuizQuestion]
    ) -> LessonState:
        if objective := self._implicated(parsed, state, questions):
            self.console.print(f"[dim]That one was about: {objective}.[/]")

        if machine.should_offer_revisit(state):
            self.console.print(
                "[dim]That's two we've missed. Worth going back over the concept properly "
                "before we finish?[/]"
            )
            if self._ask("Revisit the concept?", ["yes", "no"], "yes") == "yes":
                return machine.advance(state, Input.REVISIT_CONCEPT)
            return machine.advance(state, Input.CONTINUE)

        again = self._ask("Want me to go over that idea again?", ["yes", "no"], "no") == "yes"
        section = parsed.section("concept")
        if again and section:
            self.console.print("[bold]The Concept, again[/]")
            self._md(section.body)
        return machine.advance(state, Input.CONTINUE)

    # ---------------------------------------------------------------------- completion

    def _complete(
        self, state: LessonState, lesson: ResolvedLesson, *, now: datetime | None = None
    ) -> LessonState:
        # A quiz settles nothing: one four-option question is guessed right a quarter of the
        # time, and none can establish that software is installed. This walker holds no
        # capabilities, so it records no capability claims at all — which is the truth.
        outcome = runtime.complete_lesson(
            self.store, self.course, self.record, self.revision, lesson, now=now, hooks=self.hooks
        )
        self.record, self.revision = outcome.record, outcome.revision

        if outcome.already_completed:
            self.console.print(
                f"[dim]{lesson.coordinate} was already complete — nothing re-counted.[/]"
            )
        else:
            self.console.print(f"[bold green]Lesson complete:[/] {lesson.title}")
            self.console.print(
                f"[dim]{self.course.completed_count(self.record.completed)} of "
                f"{self.course.lesson_count} done · "
                f"{self.course.percent_complete(self.record.completed)}% · streak "
                f"{self.record.streak_days}[/]"
            )
            for badge in outcome.badges_awarded:
                self.console.print(f"[magenta]Badge earned:[/] {badge}")
        self.console.print()

        self._outcome = outcome
        return machine.advance(state, Input.NEXT)

    def _ceremony(
        self, state: LessonState, lesson: ResolvedLesson, *, now: datetime | None = None
    ) -> LessonState:
        phase = self.course.phase_of(lesson.coordinate)
        name = phase.name if phase else str(lesson.phase)
        self.console.print(
            Panel(
                f"[bold]Phase {lesson.phase} complete — {name}[/]",
                border_style="green",
            )
        )

        self._share(phase)

        outcome = self._outcome
        if outcome and outcome.homework_placed:
            self._homework(now=now)
        elif outcome and outcome.homework_queued:
            self.console.print(
                "[dim]A new assignment is queued behind the one already in your mailbox.[/]\n"
            )

        if teaser := self._next_teaser(lesson):
            self.console.print(f"[dim]Up next: {teaser}[/]\n")

        return machine.advance(state, Input.NEXT)

    def _share(self, phase) -> None:  # noqa: ANN001 - ResolvedPhase | None
        """Offer share copy, resolved in the order the specification gives.

        A model-free walker can only take the literal template, or assemble the declared facts
        flatly. It invents nothing — which is the whole reason the facts are in the manifest.
        """
        finished = self.course.completed_count(self.record.completed) >= self.course.lesson_count
        text = cer.share_text(self.course, self.record, phase, course_complete=finished)
        if not text:
            return
        self.console.print("[dim]Something to share, if you'd like to:[/]")
        self.console.print(Panel(text, border_style="dim"))
        self.console.print()

    def _next_teaser(self, lesson: ResolvedLesson) -> str | None:
        following = self.course.next_lesson(lesson.coordinate)
        if following is None:
            return None
        if following.path.is_file():
            parsed = md.parse_lesson(following.path)
            if section := parsed.section("next_up"):
                return " ".join(section.body.split())
        current = md.parse_lesson(lesson.path)
        if section := current.section("next_up"):
            return " ".join(section.body.split())
        return f"{following.title}"

    def _homework(self, *, now: datetime | None = None) -> None:
        slot, _ = self.store.get_homework(self.learner_id, self.course.id)
        if slot is None:
            return

        self.console.print(f"[bold magenta]Homework unlocked:[/] {slot.title}")
        self.console.print(f"[dim]{slot.objective}[/]\n")
        for requirement in slot.requirements:
            self.console.print(f"   [ ] {requirement.text}")
        if slot.stretch_goals:
            self.console.print("\n[dim]Stretch goals[/]")
            for goal in slot.stretch_goals:
                self.console.print(f"   [ ] {goal.text}")
        self.console.print(f"\n[dim]{slot.submission}[/]\n")
        self.console.print(
            "[dim]I can't check work — that needs a tutor with judgement. Your assignment "
            "stays in your mailbox until you submit it.[/]\n"
        )

        if not self._confirm("Do you want to submit this assignment now?", default=False):
            return
        # Submission needs its own confirmation, distinct from the input that asked for it.
        if not self._confirm(
            "Confirm: submitting archives the assignment and clears your mailbox", default=False
        ):
            self.console.print("[dim]Left in your mailbox.[/]\n")
            return

        entry = runtime.submit_homework(
            self.store,
            self.learner_id,
            self.course.id,
            slot.coordinate,
            now=now,
            hooks=self.hooks,
            record=self.record,
        )
        if entry:
            self.console.print(f"[bold green]Submitted[/] and archived: {entry.title}\n")
