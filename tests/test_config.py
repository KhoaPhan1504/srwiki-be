from app.config import get_settings


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://foo.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173, http://localhost:3000")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.supabase_url == "https://foo.supabase.co"
    assert settings.cors_origins_list == [
        "http://localhost:5173",
        "http://localhost:3000",
    ]
    get_settings.cache_clear()
