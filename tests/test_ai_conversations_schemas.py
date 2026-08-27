from app.schemas import ConversationDetail, ConversationMessageOut


def test_conversation_message_out_parses_a_user_message_payload():
    message = ConversationMessageOut(
        id="msg-1",
        payload={"role": "user", "content": "hi"},
        created_at="2026-08-26T00:00:00+00:00",
    )

    assert message.payload.role == "user"
    assert message.payload.content == "hi"


def test_conversation_message_out_parses_an_assistant_message_payload():
    message = ConversationMessageOut(
        id="msg-2",
        payload={
            "role": "assistant",
            "turns": [{"type": "reply", "content": "hello"}],
        },
        created_at="2026-08-26T00:00:00+00:00",
    )

    assert message.payload.role == "assistant"
    assert message.payload.turns[0].content == "hello"


def test_conversation_message_out_parses_a_tool_result_message_payload():
    message = ConversationMessageOut(
        id="msg-3",
        payload={
            "role": "tool_result",
            "toolCallId": "call-1",
            "result": {"success": True, "data": {}},
        },
        created_at="2026-08-26T00:00:00+00:00",
    )

    assert message.payload.role == "tool_result"
    assert message.payload.tool_call_id == "call-1"


def test_conversation_detail_serializes_messages_as_camel_case():
    detail = ConversationDetail(
        id="conv-1",
        title="My chat",
        created_at="2026-08-26T00:00:00+00:00",
        updated_at="2026-08-26T00:00:00+00:00",
        messages=[
            ConversationMessageOut(
                id="msg-1",
                payload={"role": "user", "content": "hi"},
                created_at="2026-08-26T00:00:00+00:00",
            )
        ],
    )

    dumped = detail.model_dump(by_alias=True, mode="json")
    assert dumped["messages"][0]["payload"] == {"role": "user", "content": "hi"}
    assert dumped["createdAt"] == "2026-08-26T00:00:00Z"
