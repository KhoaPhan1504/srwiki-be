import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.config import get_settings
from app.dependencies import get_current_user
from app.notifications import create_notification
from app.otp import generate_code
from app.phone import InvalidPhoneNumberError, validate_phone_e164
from app.schemas import (
    ProfileOut,
    ProfileUpdateRequest,
    SendOtpRequest,
    SendOtpResponse,
    VerifyOtpRequest,
)
from app.supabase_client import admin_client, user_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profile", tags=["profile"])


def _fetch_profile_row(client, user_id: str) -> dict:
    result = (
        client.table("profiles").select("*").eq("id", user_id).maybe_single().execute()
    )
    # postgrest-py returns None (not a response object) when zero rows match.
    if result is None or not result.data:
        raise HTTPException(status_code=404, detail="Profile not found")
    return result.data


@router.get("", response_model=ProfileOut)
def get_profile(current_user: dict = Depends(get_current_user)):
    client = user_client(current_user["access_token"])
    row = _fetch_profile_row(client, current_user["id"])
    return ProfileOut(email=current_user["email"], **row)


@router.put("", response_model=ProfileOut)
def update_profile(
    payload: ProfileUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    client = user_client(current_user["access_token"])
    updates = payload.model_dump(exclude_unset=True, mode="json")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    client.table("profiles").update(updates).eq("id", current_user["id"]).execute()
    row = _fetch_profile_row(client, current_user["id"])
    return ProfileOut(email=current_user["email"], **row)


@router.post("/avatar", response_model=ProfileOut)
def upload_avatar(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    if file.content_type not in ALLOWED_AVATAR_CONTENT_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported image type")

    content = file.file.read()
    if len(content) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=422, detail="Image exceeds 2MB limit")

    client = user_client(current_user["access_token"])
    path = f"{current_user['id']}/avatar"
    client.storage.from_("avatars").upload(
        path, content, {"content-type": file.content_type, "upsert": "true"}
    )
    avatar_url = client.storage.from_("avatars").get_public_url(path)

    now = datetime.now(timezone.utc).isoformat()
    client.table("profiles").update({"avatar_url": avatar_url, "updated_at": now}).eq(
        "id", current_user["id"]
    ).execute()
    try:
        create_notification(
            current_user["id"],
            "avatar_updated",
            "Ảnh đại diện đã được cập nhật",
            "Bạn vừa đổi ảnh đại diện mới.",
        )
    except Exception:
        logger.exception(
            "create_notification failed for user_id=%s (avatar_updated)",
            current_user["id"],
        )

    row = _fetch_profile_row(client, current_user["id"])
    return ProfileOut(email=current_user["email"], **row)


OTP_TTL_MINUTES = 5
ALLOWED_AVATAR_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_AVATAR_BYTES = 2 * 1024 * 1024


@router.post(
    "/phone/send-otp", response_model=SendOtpResponse, response_model_exclude_none=True
)  # Exclude None so debugOtp doesn't leak into response when debug mode is off
def send_otp(payload: SendOtpRequest, current_user: dict = Depends(get_current_user)):
    try:
        phone = validate_phone_e164(payload.phone)
    except InvalidPhoneNumberError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    client = admin_client()
    client.table("otp_codes").update({"consumed": True}).eq(
        "user_id", current_user["id"]
    ).eq("consumed", False).execute()

    code = generate_code()
    expires_at = (
        datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES)
    ).isoformat()
    client.table("otp_codes").insert(
        {
            "user_id": current_user["id"],
            "phone": phone,
            "code": code,
            "expires_at": expires_at,
        }
    ).execute()

    response = SendOtpResponse(message="OTP sent")
    if get_settings().otp_debug_mode:
        print(f"[OTP DEBUG] phone={phone} code={code}")
        response.debug_otp = code
    return response


@router.post("/phone/verify-otp", response_model=ProfileOut)
def verify_otp(
    payload: VerifyOtpRequest, current_user: dict = Depends(get_current_user)
):
    try:
        phone = validate_phone_e164(payload.phone)
    except InvalidPhoneNumberError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    admin = admin_client()
    now = datetime.now(timezone.utc).isoformat()
    result = (
        admin.table("otp_codes")
        .select("*")
        .eq("user_id", current_user["id"])
        .eq("phone", phone)
        .eq("code", payload.code)
        .eq("consumed", False)
        .gte("expires_at", now)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=400, detail="Invalid or expired code")

    otp_row = result.data[0]
    admin.table("otp_codes").update({"consumed": True}).eq(
        "id", otp_row["id"]
    ).execute()

    client = user_client(current_user["access_token"])
    client.table("profiles").update(
        {"phone": phone, "phone_verified": True, "updated_at": now}
    ).eq("id", current_user["id"]).execute()
    try:
        create_notification(
            current_user["id"],
            "phone_verified",
            "Xác minh số điện thoại thành công",
            f"Số điện thoại {phone} đã được xác minh.",
        )
    except Exception:
        logger.exception(
            "create_notification failed for user_id=%s (phone_verified)",
            current_user["id"],
        )

    row = _fetch_profile_row(client, current_user["id"])
    return ProfileOut(email=current_user["email"], **row)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(current_user: dict = Depends(get_current_user)):
    admin_client().auth.admin.delete_user(current_user["id"])
