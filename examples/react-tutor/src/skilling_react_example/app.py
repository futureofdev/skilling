"""Loopback-only React demo: bring an Agent, register a course, mount the tutor."""

import asyncio
import hashlib
import os
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent

from skilling.course import Course
from skilling.session import Session, SessionSnapshot
from skilling.store import SessionScope
from skilling_tutor import Evidence, Tutor
from skilling_tutor.fastapi import mount_tutor

from .deployment import BackendLease, ProducerConfig
from .deployment.note import GoalNote

HERE = Path(__file__).resolve().parent
DEMO_LEARNER = "local-demo-learner"
TRUSTED_ORIGINS = frozenset(
    f"http://{host}:{port}" for host in ("localhost", "127.0.0.1") for port in (5173, 8000)
)
NOTE_PATH = Path("showcase/welcome-skilling/goal.md")


async def current_user(request: Request) -> str:
    """Single-user local demo, deliberately unusable as deployed authentication."""
    if (
        request.client is None
        or request.client.host not in ("127.0.0.1", "::1", "testclient")
        or request.url.hostname not in ("127.0.0.1", "localhost", "::1", "testserver")
    ):
        raise HTTPException(403, "This demo is only available on loopback")
    origins = request.app.state.trusted_origins
    origin = request.headers.get("origin")
    if origin is not None and origin not in origins:
        raise HTTPException(403, "Untrusted demo origin")
    if request.headers.get("sec-fetch-site") == "cross-site" and origin not in origins:
        raise HTTPException(403, "Cross-site requests are not allowed")
    return DEMO_LEARNER


class NoteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=16_000)


class WorkStore:
    """Producer-bound learner work; the browser never supplies a filesystem path."""

    def __init__(self, workspace: Path, learner_id: str = DEMO_LEARNER):
        self.workspace = workspace.resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.learner_id = learner_id
        self.note = GoalNote.open(self.workspace)

    def target(self) -> Path:
        return self.note._check(create=True)

    def read(self) -> str:
        try:
            return self.note.inspect().text
        except FileNotFoundError:
            return ""

    def save(self, text: str) -> None:
        self.note.save(text)

    async def evidence(
        self, learner_id: str, course_alias: str, snapshot: SessionSnapshot
    ) -> Evidence | None:
        if learner_id != self.learner_id or course_alias != "welcome":
            return None
        try:
            observed = await asyncio.to_thread(self.note.inspect)
        except FileNotFoundError:
            return None
        if not observed.text.strip():
            return None
        return Evidence(
            text=f"Application inspected {observed.path}:\n{observed.text}",
            revision=hashlib.sha256(
                f"{observed.digest}:{observed.file_identity}".encode()
            ).hexdigest(),
            checked=(
                "Read the saved goal.md file and checked nonempty Goal, Takeaway, and Next action "
                "entries. The learner must still confirm authorship; the tutor reviews meaning."
                if observed.meaningful
                else None
            ),
            attested_by="react-tutor:file-inspector" if observed.meaningful else None,
        )


class DemoSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selector: str = Field(min_length=1, max_length=128)


def create_app(
    *,
    agent: Agent[None, str],
    data_dir: Path | None = None,
    course_path: Path | None = None,
    config: ProducerConfig | None = None,
    identity_dependency: Callable[..., str | Awaitable[str]] | None = None,
    allowed_origins: Sequence[str] = tuple(TRUSTED_ORIGINS),
) -> FastAPI:
    """Run one worker; replace demo identity with authenticated IDs for deployment."""
    if config is None:
        data_dir = (data_dir or Path.cwd() / ".data").expanduser().resolve()
        workspace = data_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        selected_course = course_path or HERE.parents[2] / "welcome-skilling"
        config = ProducerConfig.model_validate(
            {
                "namespace": "react-tutor",
                "backend": {"kind": "sqlite", "path": str(data_dir / "progress.sqlite3")},
                "courses": [{"id": "welcome-skilling", "path": str(selected_course.resolve())}],
                "learners": [
                    {
                        "selector": "local",
                        "label": "Local learner",
                        "learner_id": DEMO_LEARNER,
                        "work_root": str(workspace),
                        "courses": ["welcome-skilling"],
                    }
                ],
            }
        )
    config.validate_resources()
    learners = {item.learner_id: item for item in config.learners}
    works = {key: WorkStore(Path(item.work_root), key) for key, item in learners.items()}
    bindings: dict[str, str | None] = {}
    backend: BackendLease | None = None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        nonlocal backend
        backend = await asyncio.to_thread(BackendLease.open, config.backend)
        try:
            yield
        finally:
            await asyncio.to_thread(backend.close)
            backend = None
            bindings.clear()

    app = FastAPI(title="Skilling React tutor", lifespan=lifespan)
    origins = frozenset(allowed_origins)
    app.state.trusted_origins = origins

    async def demo_user(request: Request) -> str:
        await current_user(request)
        token = request.cookies.get("skilling_demo")
        identity = bindings.get(token) if token else None
        if identity is None and len(learners) == 1 and token is None:
            identity = next(iter(learners))
        if identity is None:
            raise HTTPException(401, "Select a configured local demo learner first")
        return identity

    user_dependency = identity_dependency or demo_user

    def permitted(identity: str, alias: str) -> bool:
        return (
            identity in learners
            and alias == "welcome"
            and "welcome-skilling" in learners[identity].courses
        )

    def session_factory(identity: str, alias: str, course: Course) -> Session:
        if not permitted(identity, alias):
            raise ValueError("Unauthorized learner or course")
        if backend is None:
            raise RuntimeError("Start the application lifespan before serving requests")
        scope = SessionScope(config.namespace, identity, course.id)
        return Session.open(
            course.root,
            store=backend.for_scope(scope),
            scope=scope,
            work_root=works[identity].workspace,
        )

    async def evidence(identity: str, alias: str, snapshot: SessionSnapshot) -> Evidence | None:
        return await works[identity].evidence(identity, alias, snapshot)

    tutor = Tutor(
        agent=agent,
        courses={"welcome": Path(config.courses[0].path)},
        session_factory=session_factory,
        evidence_provider=evidence,
    )
    app.state.tutor = tutor
    mount_tutor(
        app,
        tutor,
        current_user=user_dependency,
        authorize=permitted,
        allowed_origins=allowed_origins,
    )

    @app.get("/api/demo")
    async def demo(request: Request, response: Response) -> dict[str, object]:
        if identity_dependency is not None:
            return {"enabled": False}
        await current_user(request)
        token = request.cookies.get("skilling_demo")
        if token not in bindings:
            if len(bindings) >= 256:
                raise HTTPException(503, "Demo browser capacity reached")
            token = secrets.token_urlsafe(32)
            bindings[token] = next(iter(learners)) if len(learners) == 1 else None
            response.set_cookie("skilling_demo", token, httponly=True, samesite="strict")
        response.headers["Cache-Control"] = "no-store"
        selected = bindings[token]
        return {
            "enabled": True,
            "label": "Local demo identity — not production authentication",
            "selected": learners[selected].label if selected else None,
            "choices": [
                {"selector": item.selector, "label": item.label} for item in config.learners
            ],
        }

    @app.post("/api/demo/select")
    async def select(body: DemoSelection, request: Request) -> dict[str, str]:
        if identity_dependency is not None:
            raise HTTPException(404, "Demo identity is disabled")
        await current_user(request)
        token = request.cookies.get("skilling_demo")
        if token is None or token not in bindings:
            raise HTTPException(403, "Load the demo before selecting a learner")
        learner = next((item for item in config.learners if item.selector == body.selector), None)
        if learner is None:
            raise HTTPException(403, "Unknown configured demo learner")
        bindings[token] = learner.learner_id
        return {"selected": learner.label}

    def work_for(user: str) -> WorkStore:
        if not permitted(user, "welcome"):
            raise HTTPException(403, "Course access denied")
        return works[user]

    @app.get("/api/work")
    async def read_work(
        user: Annotated[str, Depends(user_dependency)], response: Response
    ) -> dict[str, str]:
        response.headers["Cache-Control"] = "no-store"
        try:
            text = await asyncio.to_thread(work_for(user).read)
            return {"text": text, "path": NOTE_PATH.as_posix()}
        except (OSError, ValueError) as error:
            raise HTTPException(409, "Saved work could not be read") from error

    @app.put("/api/work")
    async def save_work(
        body: NoteBody, request: Request, user: Annotated[str, Depends(user_dependency)]
    ) -> dict[str, str]:
        origin = request.headers.get("origin")
        expected = f"{request.url.scheme}://{request.url.netloc}"
        if origin and origin not in origins and origin != expected:
            raise HTTPException(403, "Cross-origin work writes are not allowed")
        if origin is None and request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Cross-site work writes are not allowed")
        if not body.text.strip():
            raise HTTPException(422, "Write your own note before saving")
        try:
            await asyncio.to_thread(work_for(user).save, body.text)
        except (OSError, ValueError) as error:
            raise HTTPException(409, "Your note could not be saved") from error
        return {"text": body.text, "path": NOTE_PATH.as_posix()}

    return app


def local_app() -> FastAPI:
    """Uvicorn factory; provider keys and storage credentials stay on the server."""
    model = os.environ.get("TUTOR_MODEL")
    if not model:
        raise RuntimeError("Set TUTOR_MODEL to your provider:model before starting the demo")
    agent = Agent(
        model,
        instructions=(
            "Be warm, concise, and curious. Adapt examples to the learner. "
            "Treat their goal note as their own work; never invent or rewrite it."
        ),
    )
    config_path = os.environ.get("TUTOR_CONFIG")
    course_path = os.environ.get("TUTOR_COURSE_DIR")
    return create_app(
        agent=agent,
        data_dir=Path(os.environ.get("TUTOR_DATA_DIR", ".data")),
        course_path=Path(course_path) if course_path else None,
        config=ProducerConfig.load(Path(config_path)) if config_path else None,
    )
