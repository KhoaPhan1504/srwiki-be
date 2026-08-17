import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import require_permission
from app.permissions import RoleId
from app.schemas import (
    AdminOut,
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

SORTABLE_MEMBER_COLUMNS = {
    "fullName": "full_name",
    "email": "email",
    "membershipTier": "membership_tier",
    "createdAt": "created_at",
    "dateOfBirth": "date_of_birth",
}

require_members_read = require_permission("members.read")
require_members_create = require_permission("members.create")
require_members_update = require_permission("members.update")
require_members_delete = require_permission("members.delete")
require_admins_promote = require_permission("admins.promote")


def _to_member_row(row: dict) -> dict:
    return {**row, "role": row["roles"]["name"]}


def _fetch_member_row(admin, member_id: str) -> dict | None:
    result = (
        admin.table("profiles")
        .select("*, roles(name)")
        .eq("id", member_id)
        .eq("role_id", RoleId.MEMBER)
        .is_("deleted_at", "null")
        .maybe_single()
        .execute()
    )
    if not result or not result.data:
        return None
    return _to_member_row(result.data)


def _fetch_profile_by_id(admin, user_id: str) -> dict | None:
    """Unlike _fetch_member_row, doesn't filter by role_id — used right
    after a role change (promote), where the row no longer matches the
    role it had when the request came in."""
    result = (
        admin.table("profiles")
        .select("*, roles(name)")
        .eq("id", user_id)
        .is_("deleted_at", "null")
        .maybe_single()
        .execute()
    )
    if not result or not result.data:
        return None
    return _to_member_row(result.data)


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
    sort_by: str | None = Query(default=None, alias="sortBy"),
    sort_direction: str = Query(
        default="desc", alias="sortDirection", pattern="^(asc|desc)$"
    ),
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
    if sort_by is not None and sort_by not in SORTABLE_MEMBER_COLUMNS:
        raise HTTPException(status_code=400, detail="Invalid sortBy value")

    admin = admin_client()
    query = (
        admin.table("profiles")
        .select("*, roles(name)", count="exact")
        .eq("role_id", RoleId.MEMBER)
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

    order_column = SORTABLE_MEMBER_COLUMNS.get(sort_by, "created_at")
    order_desc = sort_direction == "desc" if sort_by else True

    offset = (page - 1) * page_size
    result = (
        query.order(order_column, desc=order_desc)
        .range(offset, offset + page_size - 1)
        .execute()
    )

    return MemberListResponse(
        items=[MemberOut(**_to_member_row(row)) for row in result.data],
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
        "role_id": RoleId.MEMBER,
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


@router.delete("/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_member(
    member_id: str,
    current_user: dict = Depends(require_members_delete),
):
    if member_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    admin = admin_client()
    existing = _fetch_member_row(admin, member_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Member not found")

    now = datetime.now(timezone.utc).isoformat()
    admin.table("profiles").update({"deleted_at": now}).eq("id", member_id).execute()


@router.post("/{member_id}/promote", response_model=AdminOut)
def promote_member(
    member_id: str,
    _current_user: dict = Depends(require_admins_promote),
):
    admin = admin_client()
    existing = _fetch_member_row(admin, member_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Member not found")

    admin.table("profiles").update(
        {"role_id": RoleId.ADMIN, "membership_tier": None}
    ).eq("id", member_id).execute()

    row = _fetch_profile_by_id(admin, member_id)
    if row is None:
        raise HTTPException(
            status_code=500, detail="Member promoted but could not be fetched"
        )
    return AdminOut(**row)
