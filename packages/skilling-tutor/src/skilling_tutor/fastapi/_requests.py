"""Bounded request boundaries; the browser never supplies authoritative history."""

from __future__ import annotations

from typing import Annotated, Literal, TypeVar

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, model_validator

Identifier = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.:\-]+$")]
MAX_BODY_BYTES = 65_536


class BrowserMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: Identifier
    role: Literal["user", "assistant", "system"]
    parts: list[dict[str, JsonValue]] = Field(max_length=128)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Identifier | None = None
    trigger: Literal["submit-message"] = "submit-message"
    messageId: Identifier | None = None
    messages: list[BrowserMessage] = Field(default_factory=list, max_length=128)
    request_id: Identifier | None = None
    message: str | None = Field(default=None, max_length=8_000)
    display_id: Identifier | None = None
    control: str | None = Field(default=None, max_length=128)
    continuation_id: Identifier | None = None

    @model_validator(mode="after")
    def latest_user_text(self) -> ChatRequest:
        if self.messages:
            if self.message is not None:
                raise ValueError("Supply messages or message, not both")
            latest = self.messages[-1]
            if latest.role != "user":
                raise ValueError("The latest message must be from the learner")
            if any(part.get("type") != "text" for part in latest.parts):
                raise ValueError("Only learner text is accepted")
            fragments = [part.get("text") for part in latest.parts]
            if any(not isinstance(text, str) for text in fragments):
                raise ValueError("Text parts require text")
            self.message = "\n".join(text for text in fragments if isinstance(text, str))
            self.request_id = self.request_id or latest.id
        if self.request_id is None:
            raise ValueError("A request_id or learner message id is required")
        if len(self.message or "") > 8_000:
            raise ValueError("Learner text is too long")
        if self.continuation_id is not None and (
            self.control is not None or (self.message or "").strip()
        ):
            raise ValueError("A continuation cannot also supply learner text or a control")
        if not (self.message or "").strip() and not self.control and not self.continuation_id:
            raise ValueError("Supply learner text, a control, or a continuation")
        return self


class AckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_id: Identifier


Body = TypeVar("Body", bound=BaseModel)


async def read_body(request: Request, schema: type[Body]) -> Body:
    if request.headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
        raise HTTPException(415, "Use application/json")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BODY_BYTES:
            raise HTTPException(413, "Request body exceeds 64 KiB")
        body.extend(chunk)
    try:
        return schema.model_validate_json(body)
    except ValidationError as error:
        raise HTTPException(422, "Invalid tutor request") from error


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["objectives", "homework"]
    explanation: str = Field(default="", max_length=8_000)


class ReviewAckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_id: Identifier


class ReviewConfirmRequest(ReviewAckRequest):
    objective_id: Identifier | None = None
