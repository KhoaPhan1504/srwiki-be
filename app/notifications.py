from app.supabase_client import admin_client


def create_notification(
    user_id: str,
    notification_type: str,
    title: str,
    message: str,
    metadata: dict | None = None,
) -> None:
    admin_client().table("notifications").insert(
        {
            "user_id": user_id,
            "type": notification_type,
            "title": title,
            "message": message,
            "metadata": metadata or {},
        }
    ).execute()
