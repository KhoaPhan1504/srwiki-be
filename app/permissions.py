from enum import IntEnum


class RoleId(IntEnum):
    SUPER_ADMIN = 1
    ADMIN = 2
    MEMBER = 3


ROLE_PERMISSIONS: dict[str, set[str]] = {
    "super_admin": {
        "members.read",
        "members.create",
        "members.update",
        "members.delete",
        "admins.read",
        "admins.create",
        "admins.update",
        "admins.delete",
        "admins.promote",
        "admins.demote",
    },
    "admin": {
        "members.read",
        "members.create",
        "members.update",
        "members.delete",
        "admins.read",
    },
    "member": set(),
}
