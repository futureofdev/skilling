"""Replaceable trusted identity boundary and explicitly local demo browser bindings."""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from skilling.store import SessionScope
from skilling_tutor import SkillingRunner

from .._controller import ControllerError, ProducerController
from .._tutor import BrowserTutor
from ._config import ProducerConfig, safe_directory
from ._stores import BackendLease


@dataclass(frozen=True)
class AuthorizedLearner:
    scope: SessionScope
    work_root: Path
    course_path: Path
    label: str


@dataclass
class BrowserBinding:
    token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    csrf: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    controller: ProducerController | None = None
    authorized: AuthorizedLearner | None = None


class Deployment:
    def __init__(
        self, config: ProducerConfig, runner_factory: Callable[[], SkillingRunner | BrowserTutor]
    ) -> None:
        config.validate_resources()
        self.config = config
        self.runner_factory = runner_factory
        self.backend: BackendLease | None = None
        self.bindings: dict[str, BrowserBinding] = {}

    @classmethod
    def configure(
        cls, config: ProducerConfig, runner_factory: Callable[[], SkillingRunner | BrowserTutor]
    ) -> Deployment:
        return cls(config, runner_factory)

    def start(self) -> None:
        if self.backend is not None:
            raise RuntimeError("Deployment is already running")
        self.backend = BackendLease.open(self.config.backend)

    def close(self) -> None:
        if self.backend is not None:
            self.backend.close()
            self.backend = None
        self.bindings.clear()

    def binding(self, cookie: str | None, *, create: bool) -> BrowserBinding:
        if cookie is not None and cookie in self.bindings:
            return self.bindings[cookie]
        if not create or len(self.bindings) >= 256:
            raise ControllerError("session", "Load a new local demo session first", 403)
        binding = BrowserBinding()
        self.bindings[binding.token] = binding
        return binding

    def authorize_demo(self, selector: str, course_id: str) -> AuthorizedLearner:
        learner = next(
            (value for value in self.config.learners if value.selector == selector), None
        )
        course = next((value for value in self.config.courses if value.id == course_id), None)
        if learner is None or course is None or course_id not in learner.courses:
            raise ControllerError("identity", "Selection is not authorized", 403)
        return AuthorizedLearner(
            SessionScope(self.config.namespace, learner.learner_id, course_id),
            safe_directory(learner.work_root),
            safe_directory(course.path),
            learner.label,
        )

    def select(self, binding: BrowserBinding, selector: str, course_id: str) -> None:
        authorized = self.authorize_demo(selector, course_id)
        if self.backend is None:
            raise ControllerError("backend", "Persistence backend is not running", 503)
        controller = ProducerController.open_scoped(
            authorized.course_path,
            authorized.work_root,
            self.backend.for_scope(authorized.scope),
            authorized.scope,
            self.runner_factory(),
        )
        binding.csrf = secrets.token_urlsafe(32)
        controller.csrf_token = binding.csrf
        controller.browser_session = binding.token
        binding.controller, binding.authorized = controller, authorized
        controller.demo = self.demo(authorized.label)

    def state(self, binding: BrowserBinding) -> dict[str, object]:
        result = (
            binding.controller.state()
            if binding.controller
            else {
                "csrf_token": binding.csrf,
                "display_id": "",
                "snapshot": None,
                "controls": [],
                "messages": [],
                "objectives": [],
                "homework": None,
                "note": None,
                "review": None,
                "feedback": None,
                "history_notice": "Local demonstration only. Select a configured learner to begin.",
            }
        )
        result["demo"] = self.demo(binding.authorized.label if binding.authorized else None)
        return result

    def demo(self, selected: str | None) -> dict[str, object]:
        return {
            "label": "Local demo identity · not production authentication",
            "selected": selected,
            "choices": [
                {"selector": user.selector, "label": user.label, "courses": user.courses}
                for user in self.config.learners
            ],
        }
