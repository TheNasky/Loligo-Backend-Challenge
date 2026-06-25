"""
Explicit agent control loop — core challenge requirement.

The LLM decides whether to call tools; this function owns the orchestration.
"""

import json
import logging
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool

from app.agent.prompts import get_system_prompt
from app.config import get_settings
from app.memory.store import Message
from app.services.resilience import run_with_resilience

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 5


@dataclass
class AgentLoopResult:
    """Outcome of one user turn through the agent loop."""

    reply: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_outputs: list[dict[str, Any]] = field(default_factory=list)


def _history_to_langchain(history: list[Message]) -> list:
    """Convert stored messages to LangChain format (user + assistant turns only)."""
    messages: list = []
    for msg in history:
        if msg.role == "user":
            messages.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            messages.append(AIMessage(content=msg.content))
    return messages


def _extract_text(response: AIMessage) -> str:
    content = response.content
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "\n".join(p for p in parts if p).strip()
    return str(content).strip()


def agent_loop(
    *,
    conversation_id: str,
    user_message: str,
    history: list[Message],
    llm: BaseChatModel,
    tools: list[BaseTool],
    lang: str = "es",
) -> AgentLoopResult:
    """
    Orchestrate one conversational turn:

    1. Build message list from history + new user message
    2. Bind tools to the LLM
    3. Loop (max MAX_ITERATIONS):
       a. Invoke LLM
       b. If no tool calls → return final assistant text
       c. Execute tool calls → append observations → continue
    4. If max iterations exceeded → safe fallback reply
    """
    tool_map = {t.name: t for t in tools}
    settings = get_settings()
    messages: list = [SystemMessage(content=get_system_prompt(lang))]
    messages.extend(_history_to_langchain(history))
    messages.append(HumanMessage(content=user_message))

    llm_with_tools = llm.bind_tools(tools)
    tool_calls_log: list[dict[str, Any]] = []
    tool_outputs_log: list[dict[str, Any]] = []

    for iteration in range(MAX_ITERATIONS):
        logger.info(
            "agent_loop iteration=%s conversation_id=%s",
            iteration + 1,
            conversation_id,
        )
        response = run_with_resilience(
            lambda: llm_with_tools.invoke(messages),
            timeout_seconds=settings.upstream_timeout_seconds,
            attempts=settings.upstream_max_retries,
            backoff_seconds=settings.upstream_retry_backoff_seconds,
            operation_name="llm.invoke",
        )
        if not isinstance(response, AIMessage):
            response = AIMessage(content=str(response))

        messages.append(response)

        if not response.tool_calls:
            reply = _extract_text(response) or "I don't have a response right now."
            return AgentLoopResult(
                reply=reply,
                tool_calls=tool_calls_log,
                tool_outputs=tool_outputs_log,
            )

        for tool_call in response.tool_calls:
            name = tool_call.get("name", "")
            args = tool_call.get("args", {}) or {}
            tool_call_id = tool_call.get("id", name)

            tool_calls_log.append({"name": name, "input": args})
            logger.info(
                "tool_call conversation_id=%s tool=%s input=%s",
                conversation_id,
                name,
                args,
            )

            tool = tool_map.get(name)
            if tool is None:
                observation = json.dumps({"error": f"Unknown tool: {name}"})
            else:
                try:
                    tool_started_at = perf_counter()
                    observation = run_with_resilience(
                        lambda: tool.invoke(args),
                        timeout_seconds=settings.upstream_timeout_seconds,
                        attempts=settings.upstream_max_retries,
                        backoff_seconds=settings.upstream_retry_backoff_seconds,
                        operation_name=f"tool.invoke({name})",
                    )
                    tool_elapsed_ms = (perf_counter() - tool_started_at) * 1000
                    logger.info(
                        "tool_call_ok conversation_id=%s tool=%s elapsed_ms=%.1f",
                        conversation_id,
                        name,
                        tool_elapsed_ms,
                    )
                    if not isinstance(observation, str):
                        observation = json.dumps(observation)
                except Exception as exc:
                    logger.exception("tool_failed tool=%s", name)
                    observation = json.dumps({"error": str(exc)})

            messages.append(
                ToolMessage(content=observation, tool_call_id=tool_call_id)
            )
            parsed = _parse_output(observation)
            if parsed is not None:
                tool_outputs_log.append(
                    {"name": name, "input": args, "output": parsed}
                )

    return AgentLoopResult(
        reply=(
            "I gathered some data but couldn't finish the analysis in one pass. "
            "Try asking about a single ticker or a smaller question."
        ),
        tool_calls=tool_calls_log,
        tool_outputs=tool_outputs_log,
    )


def _parse_output(raw: str | Any) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    return None
