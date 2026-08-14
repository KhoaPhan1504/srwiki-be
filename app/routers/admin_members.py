import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import require_permission
from app.schemas import (
    MemberCreateRequest,
    MemberListResponse,
    MemberOut,
    MemberUpdateRequest,
)
from app.supabase_client import admin_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/members", tags=["admin-members"])

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

require_members_read = require_permission("members.read")
require_members_create = require_permission("members.create")
require_members_update = require_permission("members.update")


def _fetch_member_row(admin, member_id: str) -> dict | None:
    result = (
        admin.table("profiles")
        .select("*")
        .eq("id", member_id)
        .eq("role", "member")
        .is_("deleted_at", "null")
        .maybe_single()
        .execute()
    )
    return result.data if result else None


@router.get("", response_model=MemberListResponse)
def list_members(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(
        default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, alias="pageSize"
    ),
    membership_tier: str | None = Query(default=None, alias="membershipTier"),
    created_at_from: datetime | None = Query(default=None, alias="createdAtFrom"),
    created_at_to: datetime | None = Query(default=None, alias="createdAtTo"),
    address: str | None = Query(default=None),
    birthday_from: date | None = Query(default=None, alias="birthdayFrom"),
    birthday_to: date | None = Query(default=None, alias="birthdayTo"),
    _current_user: dict = Depends(require_members_read),
):
    if birthday_from and birthday_to and birthday_from > birthday_to:
        raise HTTPException(
            status_code=400, detail="birthdayFrom must be <= birthdayTo"
        )
    if created_at_from and created_at_to and created_at_from > created_at_to:
        raise HTTPException(
            status_code=400, detail="createdAtFrom must be <= createdAtTo"
        )

    query = (
        admin_client()
        .table("profiles")
        .select("*", count="exact")
        .eq("role", "member")
        .is_("deleted_at", "null")
    )
    if membership_tier:
        tiers = [t.strip() for t in membership_tier.split(",") if t.strip()]
        if tiers:
            query = query.in_("membership_tier", tiers)
    if created_at_from:
        query = query.gte("created_at", created_at_from.isoformat())
    if created_at_to:
        query = query.lt("created_at", created_at_to.isoformat())
    if address:
        query = query.ilike("address", f"%{address}%")
    if birthday_from:
        query = query.gte("date_of_birth", birthday_from.isoformat())
    if birthday_to:
        query = query.lte("date_of_birth", birthday_to.isoformat())

    offset = (page - 1) * page_size
    result = (
        query.order("created_at", desc=True)
        .range(offset, offset + page_size - 1)
        .execute()
    )

    return MemberListResponse(
        items=[MemberOut(**row) for row in result.data],
        total=result.count or 0,
        page=page,
        page_size=page_size,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=MemberOut)
def create_member(
    payload: MemberCreateRequest,
    _current_user: dict = Depends(require_members_create),
):
    admin = admin_client()
    try:
        result = admin.auth.admin.create_user(
            {
                "email": payload.email,
                "password": payload.password,
                "email_confirm": True,
                "user_metadata": {"full_name": payload.full_name},
            }
        )
    except Exception as exc:
        logger.exception("create_user failed for %s", payload.email)
        raise HTTPException(status_code=400, detail="Could not create member") from exc

    user = result.user
    if user is None:
        raise HTTPException(status_code=400, detail="Could not create member")

    profile = {
        "id": user.id,
        "email": user.email,
        "full_name": payload.full_name,
        "address": payload.address,
        "date_of_birth": (
            payload.date_of_birth.isoformat() if payload.date_of_birth else None
        ),
        "role": "member",
        "membership_tier": "regular",
    }
    try:
        admin.table("profiles").insert(profile).execute()
    except Exception as exc:
        logger.exception("profile insert failed for user_id=%s", user.id)
        try:
            admin.auth.admin.delete_user(user.id)
        except Exception:
            logger.exception("rollback delete_user failed for user_id=%s", user.id)
        raise HTTPException(
            status_code=500, detail="Could not create member profile"
        ) from exc

    row = _fetch_member_row(admin, user.id)
    if row is None:
        raise HTTPException(
            status_code=500, detail="Member created but could not be fetched"
        )
    return MemberOut(**row)


@router.put("/{member_id}", response_model=MemberOut)
def update_member(
    member_id: str,
    payload: MemberUpdateRequest,
    _current_user: dict = Depends(require_members_update),
):
    admin = admin_client()
    existing = _fetch_member_row(admin, member_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Member not found")

    changes = payload.model_dump(exclude_unset=True, mode="json")
    if changes:
        admin.table("profiles").update(changes).eq("id", member_id).execute()

    row = _fetch_member_row(admin, member_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Member not found")
    return MemberOut(**row)
