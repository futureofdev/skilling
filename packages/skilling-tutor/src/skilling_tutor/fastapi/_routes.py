"""Same-origin, authenticated HTTP routes over the trusted Tutor session runtime."""

import inspect
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from contextlib import aclosing
from typing import Annotated, TypeVar
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path, Request, Response
from fastapi.responses import StreamingResponse
from pydantic_ai.ui.vercel_ai.response_types import (
    BaseChunk,
    DataChunk,
    ErrorChunk,
    FinishChunk,
    StartChunk,
    TextDeltaChunk,
    TextEndChunk,
    TextStartChunk,
)

from skilling.session import SessionRefusal

from .. import Tutor, TutorSession, TutorSessionError
from ._requests import (
    AckRequest,
    ChatRequest,
    ReviewAckRequest,
    ReviewConfirmRequest,
    ReviewRequest,
    read_body,
)

Principal = TypeVar("Principal")


def _frame(chunk: BaseChunk) -> str:
    return f"data: {chunk.encode(sdk_version=6)}\n\n"


async def _stream(session: TutorSession, body: ChatRequest) -> AsyncGenerator[str, None]:
    message_id = str(uuid4())
    text_id = str(uuid4())
    started_text = False
    failed = False
    yield _frame(StartChunk(message_id=message_id))
    try:
        assert body.request_id is not None
        async with aclosing(
            session.stream(
                body.message or "",
                request_id=body.request_id,
                display_id=body.display_id,
                control=body.control,
                continuation_id=body.continuation_id,
            )
        ) as events:
            async for event in events:
                if event.type == "text-delta" and event.text:
                    if not started_text:
                        yield _frame(TextStartChunk(id=text_id))
                        started_text = True
                    yield _frame(TextDeltaChunk(id=text_id, delta=event.text))
                elif event.type == "text-reset":
                    if started_text:
                        yield _frame(TextEndChunk(id=text_id))
                        text_id = str(uuid4())
                        started_text = False
                    yield _frame(DataChunk(type="data-skilling", data={"type": "text-reset"}))
                elif event.type == "state":
                    yield _frame(
                        DataChunk(
                            type="data-skilling", data={"type": "state", "state": event.state}
                        )
                    )
                elif event.type == "error":
                    failed = True
                    yield _frame(
                        DataChunk(
                            type="data-skilling",
                            data={
                                "type": "error",
                                "code": event.code,
                                "message": event.message,
                                "state": event.state,
                            },
                        )
                    )
                    yield _frame(ErrorChunk(error_text=event.message or "Tutor turn failed"))
    except (TutorSessionError, SessionRefusal) as error:
        failed = True
        yield _frame(
            DataChunk(
                type="data-skilling",
                data={
                    "type": "error",
                    "code": error.code,
                    "message": "Tutor request could not be applied; refresh the course.",
                },
            )
        )
        yield _frame(
            ErrorChunk(error_text="Tutor request could not be applied; refresh the course.")
        )
    except Exception:
        failed = True
        yield _frame(ErrorChunk(error_text="Tutor turn failed. Reload to recover saved progress."))
    if started_text:
        yield _frame(TextEndChunk(id=text_id))
    yield _frame(FinishChunk(finish_reason="error" if failed else "stop"))
    yield "data: [DONE]\n\n"


def mount_tutor(
    app: FastAPI,
    tutor: Tutor,
    *,
    current_user: Callable[..., Principal | Awaitable[Principal]],
    prefix: str = "/api/learn",
    learner_id: Callable[[Principal], str] | None = None,
    authorize: Callable[[Principal, str], bool | Awaitable[bool]] | None = None,
    allowed_origins: Sequence[str] = (),
) -> None:
    """Mount the Vercel AI SDK UI stream, state and render acknowledgement routes.

    ``current_user`` is a FastAPI dependency returning an authenticated stable learner ID.
    For application user objects, supply ``learner_id=lambda user: user.id``. No learner
    identity is accepted from request bodies. ``authorize`` optionally checks course access
    on every request. Cookie sessions should be HttpOnly/Secure/SameSite; mutations require
    JSON and reject cross-origin requests unless explicitly listed in ``allowed_origins``.
    Serve the frontend through the same origin (including the development proxy), or add
    the exact trusted origins here and configure CORS explicitly on your application.
    """
    router = APIRouter(prefix=prefix)
    trusted_origins = frozenset(origin.rstrip("/") for origin in allowed_origins)

    async def resolve(
        course: Annotated[str, Path(min_length=1, max_length=128)],
        request: Request,
        response: Response,
        user: Annotated[Principal, Depends(current_user)],
    ) -> TutorSession:
        response.headers["Cache-Control"] = "no-store"
        if request.method != "GET":
            origin = request.headers.get("origin")
            expected = f"{request.url.scheme}://{request.url.netloc}"
            if origin is not None and origin not in trusted_origins and origin != expected:
                raise HTTPException(403, "Cross-origin tutor writes are not allowed")
            if origin is None and request.headers.get("sec-fetch-site") == "cross-site":
                raise HTTPException(403, "Cross-site tutor writes are not allowed")
        identity = learner_id(user) if learner_id is not None else user
        if not isinstance(identity, str) or not identity.strip() or len(identity) > 512:
            raise HTTPException(401, "Authentication must supply a stable learner ID")
        if authorize is not None:
            permitted = authorize(user, course)
            if inspect.isawaitable(permitted):
                permitted = await permitted
            if not permitted:
                raise HTTPException(403, "Course access denied")
        try:
            return tutor.session(learner_id=identity, course=course)
        except SessionRefusal as error:
            raise HTTPException(409, error.code) from error
        except KeyError as error:
            raise HTTPException(404, "Unknown course") from error
        except TutorSessionError as error:
            raise HTTPException(error.status, error.code) from error
        except ValueError as error:
            raise HTTPException(400, "Invalid tutor session") from error

    @router.get("/{course}/state")
    async def state(session: Annotated[TutorSession, Depends(resolve)]) -> dict[str, object]:
        try:
            return await session.state()
        except TutorSessionError as error:
            raise HTTPException(error.status, error.code) from error

    @router.post("/{course}/ack")
    async def acknowledge(
        request: Request, session: Annotated[TutorSession, Depends(resolve)]
    ) -> dict[str, object]:
        body = await read_body(request, AckRequest)
        try:
            return await session.acknowledge(body.display_id)
        except TutorSessionError as error:
            raise HTTPException(error.status, error.code) from error
        except SessionRefusal as error:
            raise HTTPException(409, error.code) from error

    @router.post("/{course}/chat")
    async def chat(
        request: Request, session: Annotated[TutorSession, Depends(resolve)]
    ) -> StreamingResponse:
        body = await read_body(request, ChatRequest)
        return StreamingResponse(
            _stream(session, body),
            media_type="text/event-stream",
            headers={
                "x-vercel-ai-ui-message-stream": "v1",
                "Cache-Control": "no-cache, no-store",
                "X-Accel-Buffering": "no",
            },
        )

    @router.post("/{course}/review")
    async def review(
        request: Request, session: Annotated[TutorSession, Depends(resolve)]
    ) -> dict[str, object]:
        body = await read_body(request, ReviewRequest)
        try:
            return await session.review(body.kind, body.explanation)
        except TutorSessionError as error:
            raise HTTPException(error.status, error.code) from error
        except SessionRefusal as error:
            raise HTTPException(409, error.code) from error
        except Exception as error:
            raise HTTPException(503, "Review unavailable; saved progress is preserved") from error

    @router.post("/{course}/review/ack")
    async def acknowledge_review(
        request: Request, session: Annotated[TutorSession, Depends(resolve)]
    ) -> dict[str, object]:
        body = await read_body(request, ReviewAckRequest)
        try:
            return await session.acknowledge_review(body.review_id)
        except TutorSessionError as error:
            raise HTTPException(error.status, error.code) from error
        except SessionRefusal as error:
            raise HTTPException(409, error.code) from error

    @router.post("/{course}/review/confirm")
    async def confirm_review(
        request: Request, session: Annotated[TutorSession, Depends(resolve)]
    ) -> dict[str, object]:
        body = await read_body(request, ReviewConfirmRequest)
        try:
            return await session.confirm_review(body.review_id, body.objective_id)
        except TutorSessionError as error:
            raise HTTPException(error.status, error.code) from error
        except SessionRefusal as error:
            raise HTTPException(409, error.code) from error

    app.include_router(router)
