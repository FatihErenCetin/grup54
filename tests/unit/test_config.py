from ensemble.config import Settings, get_settings


def test_default_mode_is_local(monkeypatch):
    monkeypatch.delenv("ENSEMBLE_MODE", raising=False)
    assert Settings(_env_file=None).ENSEMBLE_MODE == "local"


def test_env_overrides_default(monkeypatch):
    monkeypatch.setenv("ENSEMBLE_MODE", "hosted")
    assert Settings(_env_file=None).ENSEMBLE_MODE == "hosted"


def test_get_settings_cached():
    assert get_settings() is get_settings()


def test_gemini_model_default(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert Settings(_env_file=None).GEMINI_MODEL == "gemini-2.5-flash"


def test_gemini_model_override(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-1.5-pro")
    assert Settings(_env_file=None).GEMINI_MODEL == "gemini-1.5-pro"


def test_settings_ok_without_gemini_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert Settings(_env_file=None).GEMINI_API_KEY is None
