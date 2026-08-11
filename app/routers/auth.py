import hashlib
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from postgrest.exceptions import APIError

from app.dependencies import get_current_user
from app.notifications import create_notification
from app.schemas import (
    AuthResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    UserOut,
)
from app.supabase_client import admin_client, anon_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest):
    client = anon_client()
    try:
        result = client.auth.sign_up(
            {
                "email": payload.email,
                "password": payload.password,
                "options": {"data": {"full_name": payload.full_name}},
            }
        )
    except Exception as exc:
        logger.exception("sign_up failed for %s", payload.email)
        raise HTTPException(status_code=400, detail="Registration failed") from exc

    user = result.user
    if user is None:
        raise HTTPException(status_code=400, detail="Registration failed")

    # When Supabase's "Confirm email" setting is on, GoTrue's anti-enumeration
    # protection answers a sign-up for an existing email with a 200 and a fake
    # user whose `identities` list is empty. That user was never created, so we
    # must not insert a profile for it or roll back by deleting its id.
    if not user.identities:
        raise HTTPException(status_code=409, detail="Email already registered")

    try:
        admin_client().table("profiles").insert(
            {"id": user.id, "full_name": payload.full_name}
        ).execute()
    except Exception as exc:
        logger.exception("profile insert failed for user_id=%s", user.id)
        try:
            admin_client().auth.admin.delete_user(user.id)
        except Exception:
            logger.exception("rollback delete_user failed for user_id=%s", user.id)
        raise HTTPException(
            status_code=500, detail="Registration failed while creating profile"
        ) from exc

    return {"id": user.id, "email": user.email}


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request):
    client = anon_client()
    try:
        result = client.auth.sign_in_with_password(
            {"email": payload.email, "password": payload.password}
        )
    except Exception as exc:
        raise HTTPException(
            status_code=401, detail="Invalid email or password"
        ) from exc

    session = result.session
    user = result.user
    if session is None or user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    _track_login_device(request, user.id)

    return AuthResponse(
        token=session.access_token,
        refreshToken=session.refresh_token,
        user=UserOut(id=user.id, email=user.email),
    )


def _track_login_device(request: Request, user_id: str) -> None:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    ip = forwarded_for.split(",")[0].strip() or (
        request.client.host if request.client else "unknown"
    )
    user_agent = request.headers.get("user-agent", "unknown")
    device_hash = hashlib.sha256(f"{ip}|{user_agent}".encode()).hexdigest()

    admin = admin_client()
    existing = (
        admin.table("known_logins")
        .select("id")
        .eq("user_id", user_id)
        .eq("device_hash", device_hash)
        .maybe_single()
        .execute()
    )
    now = datetime.now(timezone.utc).isoformat()
    if existing is None or not existing.data:
        try:
            admin.table("known_logins").insert(
                {
                    "user_id": user_id,
                    "device_hash": device_hash,
                    "ip_address": ip,
                    "user_agent": user_agent,
                }
            ).execute()
        except APIError as exc:
            if exc.code != "23505":
                # Not a unique-violation on (user_id, device_hash) — some other
                # failure (network blip, bad service-role key, schema drift).
                # Let it propagate instead of silently faking success.
                raise
            # Lost a race to a concurrent login from the same new device: the
            # unique (user_id, device_hash) constraint rejected our insert
            # because another in-flight request already created the row.
            # Treat this the same as an already-known device (update
            # last_seen_at, no notification) instead of surfacing a 500 for
            # what was otherwise a successful login.
            logger.info(
                "known_logins insert lost race for user_id=%s; falling back to update",
                user_id,
            )
            admin.table("known_logins").update({"last_seen_at": now}).eq(
                "user_id", user_id
            ).eq("device_hash", device_hash).execute()
            return
        create_notification(
            user_id,
            "new_device_login",
            "Đăng nhập từ thiết bị mới",
            f"Phát hiện đăng nhập mới từ địa chỉ IP {ip}.",
            metadata={"ip": ip, "userAgent": user_agent},
        )
    else:
        admin.table("known_logins").update({"last_seen_at": now}).eq(
            "id", existing.data["id"]
        ).execute()


@router.post("/refresh", response_model=AuthResponse)
def refresh(payload: RefreshRequest):
    client = anon_client()
    try:
        result = client.auth.refresh_session(payload.refreshToken)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid refresh token") from exc

    session = result.session
    user = result.user
    if session is None or user is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    return AuthResponse(
        token=session.access_token,
        refreshToken=session.refresh_token,
        user=UserOut(id=user.id, email=user.email),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(current_user: dict = Depends(get_current_user)):
    return None
