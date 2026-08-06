from fastapi import Header, HTTPException
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
