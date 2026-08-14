ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {"members.read", "members.create", "members.update", "members.delete"},
    "member": set(),
}
