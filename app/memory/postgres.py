"""Neon / PostgreSQL conversation persistence."""

import json
import logging
from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.memory.store import Conversation, ConversationSummary, Message

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS conversations (
    id VARCHAR(128) PRIMARY KEY,
    title VARCHAR(256) NOT NULL DEFAULT 'New conversation',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS messages (
    id BIGSERIAL PRIMARY KEY,
    conversation_id VARCHAR(128) NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tool_name VARCHAR(64),
    tool_input JSONB
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_conversations_updated_at ON conversations(updated_at DESC);

ALTER TABLE messages ADD COLUMN IF NOT EXISTS artifacts JSONB;
"""


class PostgresConversationStore:
    """Shared conversation store backed by Neon PostgreSQL."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def init_schema(self) -> None:
        with psycopg.connect(self.database_url) as conn:
            conn.execute(SCHEMA_SQL)
            conn.commit()
        logger.info("postgres_schema_ready")

    def get(self, conversation_id: str) -> Conversation | None:
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            row = conn.execute(
                "SELECT id, created_at, updated_at FROM conversations WHERE id = %s",
                (conversation_id,),
            ).fetchone()
            if not row:
                return None

            msg_rows = conn.execute(
                """
                SELECT role, content, timestamp, tool_name, tool_input, artifacts
                FROM messages
                WHERE conversation_id = %s
                ORDER BY timestamp ASC, id ASC
                """,
                (conversation_id,),
            ).fetchall()

        messages = [_row_to_message(r) for r in msg_rows]
        return Conversation(
            id=row["id"],
            messages=messages,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_or_create(self, conversation_id: str) -> Conversation:
        existing = self.get(conversation_id)
        if existing:
            return existing

        now = datetime.now(UTC)
        with psycopg.connect(self.database_url) as conn:
            conn.execute(
                """
                INSERT INTO conversations (id, title, created_at, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (conversation_id, "New conversation", now, now),
            )
            conn.commit()

        return Conversation(id=conversation_id, created_at=now, updated_at=now)

    def append(self, conversation_id: str, message: Message) -> Conversation:
        self.get_or_create(conversation_id)
        tool_input: Any = Jsonb(message.tool_input) if message.tool_input is not None else None
        artifacts: Any = Jsonb(message.artifacts) if message.artifacts is not None else None

        with psycopg.connect(self.database_url) as conn:
            conn.execute(
                """
                INSERT INTO messages (conversation_id, role, content, timestamp, tool_name, tool_input, artifacts)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    conversation_id,
                    message.role,
                    message.content,
                    message.timestamp,
                    message.tool_name,
                    tool_input,
                    artifacts,
                ),
            )
            if message.role == "user":
                conn.execute(
                    """
                    UPDATE conversations
                    SET title = CASE
                        WHEN title = 'New conversation' THEN %s
                        ELSE title
                    END,
                    updated_at = %s
                    WHERE id = %s
                    """,
                    (_title_from_message(message.content), message.timestamp, conversation_id),
                )
            else:
                conn.execute(
                    "UPDATE conversations SET updated_at = %s WHERE id = %s",
                    (message.timestamp, conversation_id),
                )
            conn.commit()

        result = self.get(conversation_id)
        assert result is not None
        return result

    def list_conversations(self, limit: int = 100) -> list[ConversationSummary]:
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            rows = conn.execute(
                """
                SELECT c.id, c.title, c.created_at, c.updated_at,
                       COUNT(m.id)::int AS message_count
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id
                GROUP BY c.id, c.title, c.created_at, c.updated_at
                HAVING COUNT(m.id) > 0
                ORDER BY c.updated_at DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()

        return [
            ConversationSummary(
                id=r["id"],
                title=r["title"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                message_count=r["message_count"],
            )
            for r in rows
        ]


def _title_from_message(content: str, max_len: int = 72) -> str:
    one_line = " ".join(content.split())
    if len(one_line) <= max_len:
        return one_line
    return one_line[: max_len - 1] + "…"


def _row_to_message(row: dict[str, Any]) -> Message:
    tool_input = row.get("tool_input")
    if isinstance(tool_input, str):
        tool_input = json.loads(tool_input)
    return Message(
        role=row["role"],
        content=row["content"],
        timestamp=row["timestamp"],
        tool_name=row.get("tool_name"),
        tool_input=tool_input,
        artifacts=row.get("artifacts"),
    )
