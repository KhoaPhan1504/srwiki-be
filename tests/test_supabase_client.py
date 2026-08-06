from unittest.mock import MagicMock
import app.supabase_client as sc
from app.config import get_settings


def test_anon_client_uses_anon_key(mocker):
    sc.anon_client.cache_clear()
    fake_client = MagicMock()
    mock_create = mocker.patch("app.supabase_client.create_client", return_value=fake_client)

    result = sc.anon_client()

    settings = get_settings()
    args, kwargs = mock_create.call_args
    assert args == (settings.supabase_url, settings.supabase_anon_key)
    assert result is fake_client
    sc.anon_client.cache_clear()


def test_anon_client_disables_session_state(mocker):
    sc.anon_client.cache_clear()
    mock_create = mocker.patch("app.supabase_client.create_client", return_value=MagicMock())

    sc.anon_client()

    options = mock_create.call_args.kwargs["options"]
    assert options.auto_refresh_token is False
    assert options.persist_session is False
    sc.anon_client.cache_clear()


def test_admin_client_uses_service_role_key(mocker):
    sc.admin_client.cache_clear()
    fake_client = MagicMock()
    mock_create = mocker.patch("app.supabase_client.create_client", return_value=fake_client)

    result = sc.admin_client()

    settings = get_settings()
    mock_create.assert_called_once_with(settings.supabase_url, settings.supabase_service_role_key)
    assert result is fake_client
    sc.admin_client.cache_clear()


def test_user_client_attaches_access_token(mocker):
    fake_client = MagicMock()
    mock_create = mocker.patch("app.supabase_client.create_client", return_value=fake_client)

    result = sc.user_client("token-123")

    settings = get_settings()
    # Must use the anon key, never the service-role key: RLS is what scopes
    # this client to the token's user.
    mock_create.assert_called_once_with(settings.supabase_url, settings.supabase_anon_key)
    fake_client.postgrest.auth.assert_called_once_with("token-123")
    assert result is fake_client
