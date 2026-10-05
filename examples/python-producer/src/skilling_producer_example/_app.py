"""Loopback-only example HTTP boundary with one browser binding and bounded JSON."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from skilling.session import SessionRefusal
from skilling.store import StoreError
from skilling_tutor import TutorError

from ._controller import ControllerError, ProducerController, ReviewKind
from ._deployment import Deployment

MAX_BODY_BYTES = 40_000
COOKIE = "skilling_producer_session"


class ActionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_id: str = Field(min_length=1, max_length=128)
    event_id: str = Field(min_length=1, max_length=128)


class DisplayBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_id: str = Field(min_length=1, max_length=128)


class ChatBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=8_000)
    display_id: str | None = Field(default=None, min_length=1, max_length=128)


class ContinuationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    continuation_id: str = Field(min_length=1, max_length=128)


class NoteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(max_length=24_000)


class ReviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence: str = Field(min_length=1, max_length=6_000)


class ConfirmationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_id: str = Field(min_length=1, max_length=128)
    objective_id: str | None = Field(default=None, max_length=256)


class ArtifactBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)


class SelectionBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    selector: str = Field(min_length=1, max_length=128)
    course_id: str = Field(min_length=1, max_length=128)


def validate_bind(host: str, port: int) -> None:
    try:
        address = ipaddress.ip_address(host)
    except ValueError as error:
        raise ValueError("bind to a numeric loopback address, such as 127.0.0.1") from error
    if not address.is_loopback or not 1 <= port <= 65535:
        raise ValueError("only loopback bind and a valid port are supported")


def create_app(
    controller: ProducerController | Deployment, *, host: str = "127.0.0.1", port: int = 8765
) -> FastAPI:
    validate_bind(host, port)
    authority = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
    origin = f"http://{authority}"
    deployment = controller if isinstance(controller, Deployment) else None
    legacy = controller if isinstance(controller, ProducerController) else None
    cookie_name = (
        COOKIE
        if deployment is None
        else COOKIE
        + "_"
        + hashlib.sha256((deployment.config.namespace + authority).encode()).hexdigest()[:16]
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if deployment is not None:
            await asyncio.to_thread(deployment.start)
        try:
            yield
        finally:
            if deployment is not None:
                await asyncio.to_thread(deployment.close)

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    def selected(request: Request) -> ProducerController:
        value = request.state.controller
        if not isinstance(value, ProducerController):
            raise ControllerError("identity", "Select an authorized local demo identity first", 403)
        return value

    static = Path(__file__).parent / "static"

    @app.middleware("http")
    async def browser_boundary(request: Request, call_next):
        def refusal(code: str, message: str, status: int = 403) -> JSONResponse:
            return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)

        if request.headers.get("host") != authority:
            return refusal("host", "Unexpected loopback Host.")
        supplied_origin = request.headers.get("origin")
        if supplied_origin is not None and supplied_origin != origin:
            return refusal("origin", "Unexpected Origin.")
        if request.headers.get("sec-fetch-site") == "cross-site":
            return refusal("origin", "Cross-site requests are refused.")
        cookie = request.cookies.get(cookie_name)
        binding = None
        active = legacy
        if deployment is not None and request.url.path.startswith("/api/"):
            try:
                binding = deployment.binding(
                    cookie, create=request.method == "GET" and request.url.path == "/api/state"
                )
            except ControllerError as error:
                return refusal(error.code, str(error), error.status)
            active = binding.controller
            if active is None and request.url.path not in ("/api/state", "/api/demo/select"):
                return refusal("identity", "Select an authorized local demo identity first")
        elif legacy is not None:
            if request.method == "GET" and request.url.path == "/api/state":
                if legacy.browser_session is None:
                    legacy.browser_session = secrets.token_urlsafe(32)
                elif cookie != legacy.browser_session:
                    return refusal(
                        "session", "This producer is already bound to another browser session."
                    )
            elif request.url.path.startswith("/api/") and (
                legacy.browser_session is None or cookie != legacy.browser_session
            ):
                return refusal("session", "Load the course in its bound browser session first.")
        request.state.controller = active
        request.state.binding = binding
        csrf = binding.csrf if binding is not None else legacy.csrf_token if legacy else ""
        if request.method not in ("GET", "HEAD"):
            if supplied_origin != origin:
                return refusal("origin", "An exact loopback Origin is required.")
            if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), csrf):
                return refusal("csrf", "Missing or invalid CSRF token.")
            if request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
                return refusal("content-type", "Only application/json is accepted.", 415)
            length = request.headers.get("content-length")
            if length is not None and (not length.isdecimal() or int(length) > MAX_BODY_BYTES):
                return refusal("body-size", "Request body is too large.", 413)
            data = bytearray()
            async for chunk in request.stream():
                data.extend(chunk)
                if len(data) > MAX_BODY_BYTES:
                    return refusal("body-size", "Request body is too large.", 413)
            try:
                decoded = json.loads(data)
            except (ValueError, UnicodeError):
                return refusal("json", "Expected valid UTF-8 JSON.", 400)
            if not isinstance(decoded, dict):
                return refusal("json", "Expected a JSON object.", 400)
            request.state.body = decoded
        lock = (
            binding.lock
            if binding is not None
            else legacy.lock
            if legacy is not None
            else asyncio.Lock()
        )
        async with lock:
            # Selection may have rotated identity while this request waited behind it.
            # Revalidate custody at execution, before any controller/store access.
            if binding is not None:
                if request.method not in ("GET", "HEAD") and csrf != binding.csrf:
                    return refusal("csrf", "Identity changed; refresh before continuing.")
                request.state.controller = binding.controller
            try:
                response = await call_next(request)
            except ControllerError as error:
                response = refusal(error.code, str(error), error.status)
            except SessionRefusal as error:
                response = refusal(error.code, str(error), 409)
            except StoreError:
                response = refusal(
                    "persistence",
                    "Persistence unavailable or state changed; refresh and reconcile.",
                    409,
                )
            except TutorError:
                response = refusal(
                    "tutor", "Tutor unavailable; no review or confirmation was recorded.", 502
                )
            except (ValidationError, ValueError, UnicodeError):
                response = refusal(
                    "invalid-request",
                    "Invalid input or unsafe note; refresh and review again.",
                    400,
                )
            except OSError:
                response = refusal(
                    "filesystem", "Cannot safely access the fixed learner note.", 409
                )
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; "
                "style-src 'self'; connect-src 'self'; img-src 'none'; object-src 'none'; "
                "frame-ancestors 'none'; base-uri 'none'",
                "Referrer-Policy": "no-referrer",
            }
        )
        token = binding.token if binding is not None else legacy.browser_session if legacy else None
        if request.url.path in ("/api/state", "/api/demo/select") and token is not None:
            response.set_cookie(cookie_name, token, httponly=True, samesite="strict")
        return response

    @app.get("/")
    def index():
        return FileResponse(static / "index.html", media_type="text/html")

    @app.get("/static/{filename}")
    def asset(filename: Literal["app.js", "styles.css"]):
        return FileResponse(static / filename)

    @app.get("/api/state")
    def state(request: Request):
        if deployment is not None:
            return deployment.state(request.state.binding)
        return selected(request).state()

    @app.post("/api/demo/select")
    def choose_identity(request: Request):
        if deployment is None or request.state.binding is None:
            raise ControllerError("identity", "Demo selection is unavailable", 403)
        body = SelectionBody.model_validate(request.state.body)
        deployment.select(request.state.binding, body.selector, body.course_id)
        return deployment.state(request.state.binding)

    @app.post("/api/actions/{control_id}")
    def action(control_id: str, request: Request):
        body = ActionBody.model_validate(request.state.body)
        return selected(request).action(control_id, body.display_id, body.event_id)

    @app.post("/api/feedback/ack")
    def feedback(request: Request):
        body = DisplayBody.model_validate(request.state.body)
        return selected(request).acknowledge_feedback(body.display_id)

    @app.post("/api/chat")
    async def chat(request: Request):
        body = ChatBody.model_validate(request.state.body)
        return await selected(request).chat(body.message, display_id=body.display_id)

    @app.post("/api/continue")
    async def continue_chat(request: Request):
        body = ContinuationBody.model_validate(request.state.body)
        return await selected(request).continue_chat(body.continuation_id)

    @app.post("/api/note/save")
    def note(request: Request):
        body = NoteBody.model_validate(request.state.body)
        return selected(request).save_note(body.text)

    @app.post("/api/review/ack")
    def review_ack(request: Request):
        body = ConfirmationBody.model_validate(request.state.body)
        return selected(request).acknowledge_review(body.review_id)

    @app.post("/api/review/confirm")
    def confirm(request: Request):
        body = ConfirmationBody.model_validate(request.state.body)
        return selected(request).confirm_review(body.review_id, body.objective_id)

    @app.post("/api/review/{kind}")
    async def review(kind: ReviewKind, request: Request):
        body = ReviewBody.model_validate(request.state.body)
        return await selected(request).review_work(kind, body.evidence)

    @app.post("/api/artifact")
    def artifact(request: Request):
        body = ArtifactBody.model_validate(request.state.body)
        return selected(request).artifact(body.title)

    return app
