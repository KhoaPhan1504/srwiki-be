import logging

from fastapi import APIRouter, Depends, Query

from app.dependencies import require_permission
from app.schemas import MemberListResponse, MemberOut
from app.supabase_client import admin_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/members", tags=["admin-members"])

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

require_members_read = require_permission("members.read")


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
    _current_user: dict = Depends(require_members_read),
):
    query = (
        admin_client()
        .table("profiles")
        .select("*", count="exact")
        .eq("role", "member")
        .is_("deleted_at", "null")
    )
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
