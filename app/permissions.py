from fastapi import HTTPException

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {"members.read", "members.create", "members.update", "members.delete"},
    "member": set(),
}


def get_role_id(admin, role_name: str) -> str:
    result = (
        admin.table("roles").select("id").eq("name", role_name).maybe_single().execute()
    )
    data = result.data if result else None
    if not data:
        raise HTTPException(status_code=500, detail=f"Role '{role_name}' not found")
    return data["id"]
