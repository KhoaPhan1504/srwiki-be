from fastapi import Depends, Header, HTTPException

from app.permissions import ROLE_PERMISSIONS
from app.supabase_client import admin_client


def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        response = admin_client().auth.get_user(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    user = getattr(response, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return {"id": user.id, "email": user.email, "access_token": token}


def get_current_user_with_role(current_user: dict = Depends(get_current_user)) -> dict:
    row = (
        admin_client()
        .table("profiles")
        .select("membership_tier, deleted_at, roles(name)")
        .eq("id", current_user["id"])
        .maybe_single()
        .execute()
    )
    data = row.data if row else None
    if not data or data["deleted_at"] is not None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {
        **current_user,
        "role": data["roles"]["name"],
        "membership_tier": data["membership_tier"],
    }


def require_permission(permission: str):
    def _dependency(user: dict = Depends(get_current_user_with_role)) -> dict:
        if permission not in ROLE_PERMISSIONS.get(user["role"], set()):
            raise HTTPException(status_code=403, detail="Forbidden")
        return user

    return _dependency
