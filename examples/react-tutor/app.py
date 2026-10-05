"""Loopback-only React demo: bring an Agent, register a course, mount the tutor."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent

from skilling.session import SessionSnapshot
from skilling_tutor import Evidence, Tutor
from skilling_tutor.fastapi import mount_tutor

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
        or request.url.hostname not in ("127.0.0.1", "localhost", "testserver")
    ):
        raise HTTPException(403, "This demo is only available on loopback")
    origin = request.headers.get("origin")
    if origin is not None and origin not in TRUSTED_ORIGINS:
        raise HTTPException(403, "Untrusted demo origin")
    if request.headers.get("sec-fetch-site") == "cross-site" and origin not in TRUSTED_ORIGINS:
        raise HTTPException(403, "Cross-site requests are not allowed")
    return DEMO_LEARNER


class NoteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=16_000)


class WorkStore:
    """One fixed learner-authored file; no client-supplied filesystem paths."""

    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)

    def target(self) -> Path:
        parent = self.workspace
        for part in NOTE_PATH.parts[:-1]:
            parent /= part
            if parent.is_symlink():
                raise ValueError("Work folders must not be symlinks")
            parent.mkdir(exist_ok=True)
        target = parent / NOTE_PATH.name
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise ValueError("Work must be a regular file")
        return target

    def read(self) -> str:
        target = self.target()
        if not target.exists():
            return ""
        descriptor = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("Work must be a regular file")
            data = stream.read(64_001)
        if len(data) > 64_000:
            raise ValueError("Saved work exceeds the demo limit")
        return data.decode("utf-8")

    def save(self, text: str) -> None:
        target = self.target()
        descriptor, temporary = tempfile.mkstemp(dir=target.parent, prefix=".goal-")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)

    async def evidence(
        self, learner_id: str, course_alias: str, snapshot: SessionSnapshot
    ) -> Evidence | None:
        if learner_id != DEMO_LEARNER or course_alias != "welcome":
            return None
        text = self.read()
        if not text.strip():
            return None
        meaningful = True
        for label in ("Goal", "Takeaway", "Next action"):
            pattern = rf"(?im)^[ \t]*(?:[-*][ \t]*)?(?:\*\*)?{label}"
            pattern += r"(?::(?:\*\*)?|(?:\*\*)?:)[ \t]*(\S.*)$"
            entries = re.finditer(pattern, text)
            meaningful = meaningful and any(len(entry.group(1).strip()) >= 3 for entry in entries)
        return Evidence(
            text=f"Application inspected {NOTE_PATH.as_posix()}:\n{text}",
            revision=hashlib.sha256(text.encode()).hexdigest(),
            checked=(
                "Read the saved goal.md file and checked nonempty Goal, Takeaway, and Next action "
                "entries. The learner must still confirm authorship; the tutor reviews meaning."
                if meaningful
                else None
            ),
            attested_by="react-tutor-demo:file-inspector" if meaningful else None,
        )


def create_app(*, agent: Agent[None, str], data_dir: Path) -> FastAPI:
    """Use a real authenticated dependency and producer storage when deploying."""
    app = FastAPI(title="Skilling React tutor — local demo")
    work = WorkStore(data_dir / "workspace")
    tutor = Tutor(
        agent=agent,
        courses={"welcome": HERE.parent / "welcome-skilling"},
        state_dir=data_dir / "learning",
        evidence_provider=work.evidence,
    )
    mount_tutor(app, tutor, current_user=current_user, allowed_origins=tuple(TRUSTED_ORIGINS))

    @app.get("/api/work")
    async def read_work(user: Annotated[str, Depends(current_user)]) -> dict[str, str]:
        try:
            return {"text": work.read(), "path": NOTE_PATH.as_posix()}
        except (OSError, ValueError) as error:
            raise HTTPException(409, "Saved work could not be read") from error

    @app.put("/api/work")
    async def save_work(
        body: NoteBody, user: Annotated[str, Depends(current_user)]
    ) -> dict[str, str]:
        if not body.text.strip():
            raise HTTPException(422, "Write your own note before saving")
        try:
            work.save(body.text)
        except (OSError, ValueError) as error:
            raise HTTPException(409, "Your note could not be saved") from error
        return {"text": body.text, "path": NOTE_PATH.as_posix()}

    return app


def local_app() -> FastAPI:
    """Uvicorn factory; API keys stay in server environment variables."""
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
    return create_app(agent=agent, data_dir=Path(os.environ.get("TUTOR_DATA_DIR", HERE / ".data")))
