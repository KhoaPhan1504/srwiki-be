from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_current_user
from app.schemas import (
    AppendMessagesRequest,
    AppendMessagesResponse,
    ConversationCreateRequest,
    ConversationDetail,
    ConversationMessageOut,
    ConversationRenameRequest,
    ConversationSummary,
)
from app.supabase_client import user_client

router = APIRouter(prefix="/ai/conversations", tags=["ai-conversations"])


@router.get("", response_model=list[ConversationSummary])
def list_conversations(current_user: dict = Depends(get_current_user)):
    client = user_client(current_user["access_token"])
    result = (
        client.table("ai_conversations")
        .select("*")
        .eq("user_id", current_user["id"])
        .order("updated_at", desc=True)
        .execute()
    )
    return [ConversationSummary(**row) for row in result.data]


@router.post(
    "", status_code=status.HTTP_201_CREATED, response_model=ConversationSummary
)
def create_conversation(
    payload: ConversationCreateRequest, current_user: dict = Depends(get_current_user)
):
    client = user_client(current_user["access_token"])
    result = (
        client.table("ai_conversations")
        .insert({"user_id": current_user["id"], "title": payload.title})
        .execute()
    )
    return ConversationSummary(**result.data[0])


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: str, current_user: dict = Depends(get_current_user)
):
    client = user_client(current_user["access_token"])
    conversation = (
        client.table("ai_conversations")
        .select("*")
        .eq("id", conversation_id)
        .eq("user_id", current_user["id"])
        .maybe_single()
        .execute()
    )
    if not conversation or not conversation.data:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages_result = (
        client.table("ai_conversation_messages")
        .select("*")
        .eq("conversation_id", conversation_id)
        .eq("user_id", current_user["id"])
        .order("seq")
        .execute()
    )
    return ConversationDetail(
        **conversation.data,
        messages=[ConversationMessageOut(**row) for row in messages_result.data],
    )


@router.patch("/{conversation_id}", response_model=ConversationSummary)
def rename_conversation(
    conversation_id: str,
    payload: ConversationRenameRequest,
    current_user: dict = Depends(get_current_user),
):
    client = user_client(current_user["access_token"])
    now = datetime.now(timezone.utc).isoformat()
    result = (
        client.table("ai_conversations")
        .update({"title": payload.title, "updated_at": now})
        .eq("id", conversation_id)
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationSummary(**result.data[0])


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: str, current_user: dict = Depends(get_current_user)
):
    client = user_client(current_user["access_token"])
    result = (
        client.table("ai_conversations")
        .delete()
        .eq("id", conversation_id)
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Conversation not found")


@router.post(
    "/{conversation_id}/messages",
    status_code=status.HTTP_201_CREATED,
    response_model=AppendMessagesResponse,
)
def append_messages(
    conversation_id: str,
    payload: AppendMessagesRequest,
    current_user: dict = Depends(get_current_user),
):
    client = user_client(current_user["access_token"])
    conversation = (
        client.table("ai_conversations")
        .select("id")
        .eq("id", conversation_id)
        .eq("user_id", current_user["id"])
        .maybe_single()
        .execute()
    )
    if not conversation or not conversation.data:
        raise HTTPException(status_code=404, detail="Conversation not found")

    now = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "conversation_id": conversation_id,
            "user_id": current_user["id"],
            "payload": message.model_dump(mode="json", by_alias=True),
        }
        for message in payload.messages
    ]
    result = client.table("ai_conversation_messages").insert(rows).execute()

    client.table("ai_conversations").update({"updated_at": now}).eq(
        "id", conversation_id
    ).eq("user_id", current_user["id"]).execute()

    return AppendMessagesResponse(
        messages=[ConversationMessageOut(**row) for row in result.data]
    )
