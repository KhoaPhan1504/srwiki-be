import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user
from app.notifications import create_notification
from app.schemas import SettingsOut, SettingsUpdateRequest
from app.supabase_client import user_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])

DEFAULT_SETTINGS: dict = {
    "language": "vi",
    "timezone": "Asia/Ho_Chi_Minh",
    "theme": "system",
    "email_notifications": True,
}


def _fetch_stored_settings(client, user_id: str) -> dict:
    result = (
        client.table("user_settings")
        .select("settings")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if result is None or not result.data:
        return {}
    return result.data["settings"]


@router.get("", response_model=SettingsOut)
def get_user_settings(current_user: dict = Depends(get_current_user)):
    client = user_client(current_user["access_token"])
    stored = _fetch_stored_settings(client, current_user["id"])
    return SettingsOut(**{**DEFAULT_SETTINGS, **stored})


@router.put("", response_model=SettingsOut)
def update_user_settings(
    payload: SettingsUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    client = user_client(current_user["access_token"])
    stored = _fetch_stored_settings(client, current_user["id"])
    changes = payload.model_dump(exclude_unset=True)
    merged = {**stored, **changes}

    now = datetime.now(timezone.utc).isoformat()
    client.table("user_settings").upsert(
        {"user_id": current_user["id"], "settings": merged, "updated_at": now},
        on_conflict="user_id",
    ).execute()

    changed = any(stored.get(k) != v for k, v in changes.items())
    if changed:
        try:
            create_notification(
                current_user["id"],
                "settings_updated",
                "Cài đặt tài khoản đã được cập nhật",
                "Bạn vừa thay đổi cài đặt tài khoản.",
            )
        except Exception:
            logger.exception(
                "create_notification failed for user_id=%s (settings_updated)",
                current_user["id"],
            )

    return SettingsOut(**{**DEFAULT_SETTINGS, **merged})
