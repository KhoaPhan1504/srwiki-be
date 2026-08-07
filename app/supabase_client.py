from functools import lru_cache
from supabase import create_client, Client, ClientOptions
from app.config import get_settings


@lru_cache
def anon_client() -> Client:
    """Shared anon client used for sign-up/sign-in/refresh calls.

    This backend is stateless per request: it always extracts tokens from the
    response and re-uses them explicitly, never relying on the SDK's own session
    management. Auto-refresh and session persistence are therefore disabled so
    that one user's auth events cannot mutate the shared client's state (its
    Authorization header) and leak into another user's request.
    """
    settings = get_settings()
    options = ClientOptions(auto_refresh_token=False, persist_session=False)
    return create_client(settings.supabase_url, settings.supabase_anon_key, options=options)


@lru_cache
def admin_client() -> Client:
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def user_client(access_token: str) -> Client:
    settings = get_settings()
    options = ClientOptions(headers={"Authorization": f"Bearer {access_token}"})
    return create_client(settings.supabase_url, settings.supabase_anon_key, options=options)
