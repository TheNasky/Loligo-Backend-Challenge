"""Chat HTTP routes — thin controllers; business logic lives in agent + store."""

import json
import logging
from datetime import UTC, datetime
from time import perf_counter

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.agent.llm import get_llm
from app.agent.loop import agent_loop
from app.agent.tools import get_agent_tools
from app.config import get_settings
from app.memory.store import Message, get_conversation_store
from app.services.artifacts import build_artifacts_from_tool_outputs
from app.services.idempotency import get_idempotency_cache
from app.services.rate_limit import get_chat_rate_limiter
from app.services.telemetry import get_telemetry
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationListResponse,
    ConversationResponse,
    ConversationSummarySchema,
    ToolCallSchema,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("", response_model=ConversationListResponse)
def list_chats() -> ConversationListResponse:
    """List all conversations (shared — no auth). Most recent first."""
    store = get_conversation_store()
    summaries = store.list_conversations()
    return ConversationListResponse(
        conversations=[
            ConversationSummarySchema(
                id=s.id,
                title=s.title,
                created_at=s.created_at,
                updated_at=s.updated_at,
                message_count=s.message_count,
            )
            for s in summaries
        ]
    )


@router.post("", response_model=ChatResponse, status_code=status.HTTP_200_OK)
def post_chat(body: ChatRequest, request: Request, response: Response) -> ChatResponse:
    """Send a message to a conversation thread and return the agent reply."""
    settings = get_settings()
    if not settings.llm_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM API key not configured. Set LLM_API_KEY in .env",
        )
    client_ip = request.client.host if request.client else "unknown"
    telemetry = get_telemetry()
    limiter = get_chat_rate_limiter()
    limit_key = f"{client_ip}:{body.id}"
    rate_limit_decision = limiter.allow(limit_key)
    response.headers["X-RateLimit-Remaining"] = str(rate_limit_decision.remaining)
    if not rate_limit_decision.allowed:
        telemetry.record_rate_limited()
        response.headers["Retry-After"] = str(rate_limit_decision.retry_after_seconds)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please retry shortly.",
        )
    idempotency_key = request.headers.get("Idempotency-Key", "").strip()
    if idempotency_key:
        cached = get_idempotency_cache().get(f"{body.id}:{idempotency_key}")
        if cached is not None:
            response.headers["X-Idempotency-Replayed"] = "true"
            return ChatResponse(**cached)

    store = get_conversation_store()
    conversation = store.get_or_create(body.id)
    history = list(conversation.messages)

    logger.info("chat_request conversation_id=%s client_ip=%s", body.id, client_ip)
    started_at = perf_counter()

    try:
        result = agent_loop(
            conversation_id=body.id,
            user_message=body.message,
            history=history,
            llm=get_llm(),
            tools=get_agent_tools(),
            lang=body.lang,
        )
    except Exception as exc:
        logger.exception("agent_loop_failed conversation_id=%s", body.id)
        telemetry.record_chat_error()
        status_code, detail = _map_agent_error(exc)
        raise HTTPException(
            status_code=status_code,
            detail=detail,
        ) from None

    artifacts = build_artifacts_from_tool_outputs(result.tool_outputs)

    now = datetime.now(UTC)
    store.append(body.id, Message(role="user", content=body.message, timestamp=now))
    for output in result.tool_outputs:
        store.append(
            body.id,
            Message(
                role="tool",
                content=json.dumps(output.get("output", {}), ensure_ascii=False),
                timestamp=datetime.now(UTC),
                tool_name=output.get("name"),
                tool_input=output.get("input"),
            ),
        )
    store.append(
        body.id,
        Message(
            role="assistant",
            content=result.reply,
            timestamp=datetime.now(UTC),
            artifacts=artifacts or None,
        ),
    )
    elapsed_ms = (perf_counter() - started_at) * 1000
    logger.info(
        "chat_response conversation_id=%s elapsed_ms=%.1f tool_calls=%s",
        body.id,
        elapsed_ms,
        len(result.tool_calls),
    )
    telemetry.record_chat_success(elapsed_ms)
    payload = ChatResponse(
        id=body.id,
        reply=result.reply,
        created_at=now,
        tool_calls=[ToolCallSchema(name=tc["name"], input=tc["input"]) for tc in result.tool_calls],
        artifacts=artifacts,
    )
    if idempotency_key:
        get_idempotency_cache().set(
            f"{body.id}:{idempotency_key}",
            payload.model_dump(),
        )
    return payload


@router.get("/{conversation_id}", response_model=ConversationResponse)
def get_chat(conversation_id: str) -> ConversationResponse:
    """Return full message history for a conversation id."""
    store = get_conversation_store()
    conversation = store.get(conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    return ConversationResponse.from_conversation(conversation)


def _map_agent_error(exc: Exception) -> tuple[int, str]:
    message = str(exc).lower()
    if isinstance(exc, TimeoutError) or "timeout" in message or "timed out" in message:
        return status.HTTP_504_GATEWAY_TIMEOUT, "Upstream timeout while processing the request"
    if "429" in message or "rate limit" in message:
        return status.HTTP_503_SERVICE_UNAVAILABLE, "Upstream rate limit reached, please retry"
    if "connection" in message or "network" in message:
        return status.HTTP_502_BAD_GATEWAY, "Upstream connectivity issue while processing request"
    return status.HTTP_500_INTERNAL_SERVER_ERROR, "Agent processing failed"
