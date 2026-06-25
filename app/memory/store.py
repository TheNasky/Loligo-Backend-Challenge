"""Conversation memory — isolated per conversation id."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import RLock
from typing import Any, Literal


MessageRole = Literal["user", "assistant", "tool"]


@dataclass
class Message:
    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    artifacts: list[dict[str, Any]] | None = None


@dataclass
class Conversation:
    id: str
    messages: list[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ConversationSummary:
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int


class InMemoryConversationStore:
    """Thread-safe in-process store (fallback when DATABASE_URL is unset)."""

    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}
        self._titles: dict[str, str] = {}
        self._lock = RLock()

    def init_schema(self) -> None:
        return None

    def get(self, conversation_id: str) -> Conversation | None:
        with self._lock:
            return self._conversations.get(conversation_id)

    def get_or_create(self, conversation_id: str) -> Conversation:
        with self._lock:
            if conversation_id not in self._conversations:
                now = datetime.now(UTC)
                self._conversations[conversation_id] = Conversation(
                    id=conversation_id,
                    created_at=now,
                    updated_at=now,
                )
                self._titles[conversation_id] = "New conversation"
            return self._conversations[conversation_id]

    def append(self, conversation_id: str, message: Message) -> Conversation:
        with self._lock:
            conversation = self.get_or_create(conversation_id)
            if message.role == "user" and self._titles.get(conversation_id) == "New conversation":
                self._titles[conversation_id] = _title_from_message(message.content)
            conversation.messages.append(message)
            conversation.updated_at = datetime.now(UTC)
            return conversation

    def list_conversations(self, limit: int = 100) -> list[ConversationSummary]:
        with self._lock:
            summaries: list[ConversationSummary] = []
            for conv in self._conversations.values():
                if not conv.messages:
                    continue
                summaries.append(
                    ConversationSummary(
                        id=conv.id,
                        title=self._titles.get(conv.id, "New conversation"),
                        created_at=conv.created_at,
                        updated_at=conv.updated_at,
                        message_count=len(conv.messages),
                    )
                )
            summaries.sort(key=lambda s: s.updated_at, reverse=True)
            return summaries[:limit]


def _title_from_message(content: str, max_len: int = 72) -> str:
    one_line = " ".join(content.split())
    if len(one_line) <= max_len:
        return one_line
    return one_line[: max_len - 1] + "…"


_store: InMemoryConversationStore | None = None


def get_conversation_store():
    """Postgres (Neon) when DATABASE_URL is set; otherwise in-memory for local/tests."""
    global _store
    if _store is None:
        from app.config import get_settings

        settings = get_settings()
        if settings.database_url:
            from app.memory.postgres import PostgresConversationStore

            _store = PostgresConversationStore(settings.database_url)
            _store.init_schema()
        else:
            _store = InMemoryConversationStore()
    return _store


def reset_conversation_store() -> None:
    """Test helper — clear cached store instance."""
    global _store
    _store = None
