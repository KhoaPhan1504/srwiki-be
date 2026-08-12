import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user
from app.schemas import MarkAllReadResponse, NotificationOut
from app.supabase_client import user_client

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def list_notifications(current_user: dict = Depends(get_current_user)):
    client = user_client(current_user["access_token"])
    result = (
        client.table("notifications")
        .select("*")
        .eq("user_id", current_user["id"])
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    return [NotificationOut(**row) for row in result.data]


@router.patch("/{notification_id}/read", response_model=NotificationOut)
def mark_notification_read(
    notification_id: uuid.UUID, current_user: dict = Depends(get_current_user)
):
    client = user_client(current_user["access_token"])
    now = datetime.now(timezone.utc).isoformat()
    result = (
        client.table("notifications")
        .update({"read_at": now})
        .eq("id", str(notification_id))
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Notification not found")
    return NotificationOut(**result.data[0])


@router.patch("/read-all", response_model=MarkAllReadResponse)
def mark_all_notifications_read(current_user: dict = Depends(get_current_user)):
    client = user_client(current_user["access_token"])
    now = datetime.now(timezone.utc).isoformat()
    result = (
        client.table("notifications")
        .update({"read_at": now})
        .eq("user_id", current_user["id"])
        .is_("read_at", "null")
        .execute()
    )
    return MarkAllReadResponse(marked_count=len(result.data))
