"""Application-owned Agents, generic course registration and isolated learner sessions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from hashlib import sha256
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Generic, TypeVar

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from skilling.course import Course
from skilling.session import FileSession, Session, SessionSnapshot, load_course

from ._types import Evidence, RuntimeErrorCode, TutorSessionError

if TYPE_CHECKING:
    from ._session import TutorSession

DepsT = TypeVar("DepsT")
EvidenceProvider = Callable[[str, str, SessionSnapshot], Awaitable[Evidence | None]]


class Tutor(Generic[DepsT]):
    """Mount a producer's text Agent without replacing its configuration or dependencies.

    One Tutor owns a bounded in-process session registry. Run one application worker for
    this adapter. Durable learning state survives restart; chat and render receipts
    deliberately do not. A session_factory can supply a scoped Session backed by a
    producer-owned store. Browser conversations still require one application worker.
    """

    def __init__(
        self,
        *,
        agent: Agent[DepsT, str],
        courses: Mapping[str, Path],
        state_dir: Path | None = None,
        session_factory: Callable[[str, str, Course], Session] | None = None,
        deps_factory: Callable[[str, str], DepsT] | None = None,
        evidence_provider: EvidenceProvider | None = None,
        review_agent: Agent[DepsT, str] | None = None,
        max_sessions: int = 256,
        lock_timeout: float = 10,
        turn_timeout: float = 120,
        usage_limits: UsageLimits | None = None,
    ):
        if agent.output_type is not str:
            raise ValueError("Tutor requires a text-output Agent (output_type=str)")
        if max_sessions < 1 or lock_timeout <= 0 or turn_timeout <= 0:
            raise ValueError("Session capacity and timeouts must be positive")
        if not courses:
            raise ValueError("Register at least one course")
        self.agent = agent
        self.review_agent = review_agent or agent
        self.deps_factory = deps_factory
        self.evidence_provider = evidence_provider
        if (state_dir is None) == (session_factory is None):
            raise ValueError("Supply exactly one of state_dir or session_factory")
        self.state_dir = state_dir.expanduser().resolve() if state_dir is not None else None
        self.session_factory = session_factory
        self.max_sessions = max_sessions
        self.lock_timeout = lock_timeout
        self.turn_timeout = turn_timeout
        self.usage_limits = usage_limits or UsageLimits(request_limit=16)
        self.courses: dict[str, Course] = {}
        for alias, path in courses.items():
            if not alias or len(alias) > 128 or "/" in alias or "\\" in alias:
                raise ValueError("Course aliases must be nonempty route-safe names")
            self.courses[alias] = load_course(path.expanduser().resolve(strict=True))

        self._sessions: dict[str, TutorSession[DepsT]] = {}
        self._registry_lock = Lock()

    def session(self, *, learner_id: str, course: str) -> TutorSession[DepsT]:
        """Resolve trusted application identity; never accept identity from chat payloads."""
        if not isinstance(learner_id, str) or not learner_id or len(learner_id) > 1024:
            raise ValueError("A nonempty trusted learner identity is required")
        key = sha256(f"{len(learner_id)}:{learner_id}{len(course)}:{course}".encode()).hexdigest()
        existing = self._sessions.get(key)
        if existing is not None:
            return existing
        with self._registry_lock:
            return self._session(learner_id=learner_id, course=course)

    def _session(self, *, learner_id: str, course: str) -> TutorSession[DepsT]:
        from ._session import TutorSession

        if not isinstance(learner_id, str) or not learner_id or len(learner_id) > 1024:
            raise ValueError("A nonempty trusted learner identity is required")
        selected = self.courses[course]
        # Domain-separated length-prefixed values cannot collide through separators/paths.
        key = sha256(f"{len(learner_id)}:{learner_id}{len(course)}:{course}".encode()).hexdigest()
        existing = self._sessions.get(key)
        if existing is not None:
            return existing
        if len(self._sessions) >= self.max_sessions:
            raise TutorSessionError(
                RuntimeErrorCode.CAPACITY, "Tutor session capacity reached", 503
            )
        service: FileSession | Session
        state_root = self.state_dir / key if self.state_dir is not None else None
        if self.session_factory is not None:
            service = self.session_factory(learner_id, course, selected)
            if service.scope.learner_id != learner_id or service.scope.course_id != selected.id:
                raise ValueError("Session factory returned a different learner or course scope")
        else:
            assert state_root is not None
            service = FileSession.open(selected, state_root=state_root, learner_id=key)
        session = TutorSession(self, learner_id, course, selected, service, state_root)
        self._sessions[key] = session
        return session
