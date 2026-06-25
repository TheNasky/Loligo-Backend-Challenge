from app.memory.store import InMemoryConversationStore, Message


def test_conversations_are_isolated_by_id() -> None:
    store = InMemoryConversationStore()

    store.append("session-a", Message(role="user", content="hello a"))
    store.append("session-b", Message(role="user", content="hello b"))

    conv_a = store.get("session-a")
    conv_b = store.get("session-b")

    assert conv_a is not None
    assert conv_b is not None
    assert len(conv_a.messages) == 1
    assert len(conv_b.messages) == 1
    assert conv_a.messages[0].content == "hello a"
    assert conv_b.messages[0].content == "hello b"


def test_list_conversations_returns_summaries() -> None:
    store = InMemoryConversationStore()
    store.append("session-a", Message(role="user", content="Analyze NVDA trend"))
    store.append("session-a", Message(role="assistant", content="NVDA is above MA20."))

    listed = store.list_conversations()
    assert len(listed) == 1
    assert listed[0].id == "session-a"
    assert "NVDA" in listed[0].title
    assert listed[0].message_count == 2
