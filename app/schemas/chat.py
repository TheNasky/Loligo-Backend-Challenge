"""Pydantic request/response models — API contracts (like NestJS DTOs)."""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.config import get_settings
from app.memory.store import Conversation


class MessageSchema(BaseModel):
    role: Literal["user", "assistant", "tool"]
    content: str
    timestamp: datetime
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    artifacts: list[dict[str, Any]] | None = None


class ChatRequest(BaseModel):
    id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    lang: Literal["es", "en"] = "es"

    @field_validator("id", mode="before")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("must be a string")
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty or whitespace only")
        settings = get_settings()
        if len(stripped) > settings.conversation_id_max_length:
            raise ValueError(
                f"must be at most {settings.conversation_id_max_length} characters"
            )
        return stripped

    @field_validator("message", mode="before")
    @classmethod
    def validate_message(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("must be a string")
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty or whitespace only")
        settings = get_settings()
        if len(stripped) > settings.message_max_length:
            raise ValueError(f"must be at most {settings.message_max_length} characters")
        return stripped


class ToolCallSchema(BaseModel):
    name: str
    input: dict[str, Any]


class ChatResponse(BaseModel):
    id: str
    reply: str
    created_at: datetime
    tool_calls: list[ToolCallSchema] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)


class ConversationResponse(BaseModel):
    id: str
    messages: list[MessageSchema]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_conversation(cls, conversation: Conversation) -> "ConversationResponse":
        return cls(
            id=conversation.id,
            messages=[
                MessageSchema(
                    role=msg.role,
                    content=msg.content,
                    timestamp=msg.timestamp,
                    tool_name=msg.tool_name,
                    tool_input=msg.tool_input,
                    artifacts=msg.artifacts,
                )
                for msg in conversation.messages
            ],
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )


class ConversationSummarySchema(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int


class ConversationListResponse(BaseModel):
    conversations: list[ConversationSummarySchema]
