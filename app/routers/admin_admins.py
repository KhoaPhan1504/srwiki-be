import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import require_permission
from app.permissions import RoleId
from app.schemas import (
    AdminCreateRequest,
    AdminListResponse,
    AdminOut,
    AdminUpdateRequest,
    MemberOut,
)
from app.supabase_client import admin_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/admins", tags=["admin-admins"])

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

SORTABLE_ADMIN_COLUMNS = {
    "fullName": "full_name",
    "email": "email",
    "createdAt": "created_at",
}

require_admins_read = require_permission("admins.read")
require_admins_create = require_permission("admins.create")
require_admins_update = require_permission("admins.update")
require_admins_delete = require_permission("admins.delete")
require_admins_demote = require_permission("admins.demote")


def _to_admin_row(row: dict) -> dict:
    return {**row, "role": row["roles"]["name"]}


def _fetch_admin_row(admin, admin_id: str) -> dict | None:
    result = (
        admin.table("profiles")
        .select("*, roles(name)")
        .eq("id", admin_id)
        .eq("role_id", RoleId.ADMIN)
        .is_("deleted_at", "null")
        .maybe_single()
        .execute()
    )
    if not result or not result.data:
        return None
    return _to_admin_row(result.data)


def _fetch_profile_by_id(admin, user_id: str) -> dict | None:
    """Unlike _fetch_admin_row, doesn't filter by role_id — used right
    after a role change (demote), where the row no longer matches the
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
    return _to_admin_row(result.data)


@router.get("", response_model=AdminListResponse)
def list_admins(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(
        default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, alias="pageSize"
    ),
    sort_by: str | None = Query(default=None, alias="sortBy"),
    sort_direction: str = Query(
        default="desc", alias="sortDirection", pattern="^(asc|desc)$"
    ),
    address: str | None = Query(default=None),
    created_at_from: datetime | None = Query(default=None, alias="createdAtFrom"),
    created_at_to: datetime | None = Query(default=None, alias="createdAtTo"),
    _current_user: dict = Depends(require_admins_read),
):
    if sort_by is not None and sort_by not in SORTABLE_ADMIN_COLUMNS:
        raise HTTPException(status_code=400, detail="Invalid sortBy value")
    if created_at_from and created_at_to and created_at_from > created_at_to:
        raise HTTPException(
            status_code=400, detail="createdAtFrom must be <= createdAtTo"
        )

    admin = admin_client()
    query = (
        admin.table("profiles")
        .select("*, roles(name)", count="exact")
        .eq("role_id", RoleId.ADMIN)
        .is_("deleted_at", "null")
    )
    if address:
        query = query.ilike("address", f"%{address}%")
    if created_at_from:
        query = query.gte("created_at", created_at_from.isoformat())
    if created_at_to:
        query = query.lt("created_at", created_at_to.isoformat())

    order_column = SORTABLE_ADMIN_COLUMNS.get(sort_by, "created_at")
    order_desc = sort_direction == "desc" if sort_by else True

    offset = (page - 1) * page_size
    result = (
        query.order(order_column, desc=order_desc)
        .range(offset, offset + page_size - 1)
        .execute()
    )
    return AdminListResponse(
        items=[AdminOut(**_to_admin_row(row)) for row in result.data],
        total=result.count or 0,
        page=page,
        page_size=page_size,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=AdminOut)
def create_admin(
    payload: AdminCreateRequest,
    _current_user: dict = Depends(require_admins_create),
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
        raise HTTPException(status_code=400, detail="Could not create admin") from exc

    user = result.user
    if user is None:
        raise HTTPException(status_code=400, detail="Could not create admin")

    profile = {
        "id": user.id,
        "email": user.email,
        "full_name": payload.full_name,
        "address": payload.address,
        "date_of_birth": (
            payload.date_of_birth.isoformat() if payload.date_of_birth else None
        ),
        "role_id": RoleId.ADMIN,
        "membership_tier": None,
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
            status_code=500, detail="Could not create admin profile"
        ) from exc

    row = _fetch_admin_row(admin, user.id)
    if row is None:
        raise HTTPException(
            status_code=500, detail="Admin created but could not be fetched"
        )
    return AdminOut(**row)


@router.put("/{admin_id}", response_model=AdminOut)
def update_admin(
    admin_id: str,
    payload: AdminUpdateRequest,
    _current_user: dict = Depends(require_admins_update),
):
    admin = admin_client()
    existing = _fetch_admin_row(admin, admin_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Admin not found")

    changes = payload.model_dump(exclude_unset=True, mode="json")
    if changes:
        admin.table("profiles").update(changes).eq("id", admin_id).execute()

    row = _fetch_admin_row(admin, admin_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Admin not found")
    return AdminOut(**row)


@router.delete("/{admin_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_admin(
    admin_id: str,
    _current_user: dict = Depends(require_admins_delete),
):
    admin = admin_client()
    existing = _fetch_admin_row(admin, admin_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Admin not found")

    now = datetime.now(timezone.utc).isoformat()
    admin.table("profiles").update({"deleted_at": now}).eq("id", admin_id).execute()


@router.post("/{admin_id}/demote", response_model=MemberOut)
def demote_admin(
    admin_id: str,
    _current_user: dict = Depends(require_admins_demote),
):
    admin = admin_client()
    existing = _fetch_admin_row(admin, admin_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Admin not found")

    admin.table("profiles").update(
        {"role_id": RoleId.MEMBER, "membership_tier": "regular"}
    ).eq("id", admin_id).execute()

    row = _fetch_profile_by_id(admin, admin_id)
    if row is None:
        raise HTTPException(
            status_code=500, detail="Admin demoted but could not be fetched"
        )
    return MemberOut(**row)
