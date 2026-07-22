import pytest
from pydantic import ValidationError

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


def test_llm_provider_default_is_gemini(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert Settings(_env_file=None).LLM_PROVIDER == "gemini"


def test_ollama_defaults_stay_on_loopback():
    settings = Settings(_env_file=None, LLM_PROVIDER="ollama")
    assert settings.OLLAMA_BASE_URL == "http://127.0.0.1:11434"
    assert settings.OLLAMA_MODEL == "llama3.2"
    assert settings.OLLAMA_EMBEDDING_MODEL == "nomic-embed-text"


def test_ollama_remote_url_is_rejected():
    with pytest.raises(ValidationError, match="loopback"):
        Settings(
            _env_file=None,
            LLM_PROVIDER="ollama",
            OLLAMA_BASE_URL="https://ollama.example.com",
        )


def test_github_default_branch_default():
    assert Settings(_env_file=None).GITHUB_DEFAULT_BRANCH == "main"


def test_settings_ok_without_github_app_config(monkeypatch):
    for var in ("GITHUB_APP_ID", "GITHUB_APP_PRIVATE_KEY_PATH", "GITHUB_APP_INSTALLATION_ID"):
        monkeypatch.delenv(var, raising=False)
    settings = Settings(_env_file=None)
    assert settings.GITHUB_APP_ID is None
    assert settings.GITHUB_APP_PRIVATE_KEY_PATH is None
    assert settings.GITHUB_APP_INSTALLATION_ID is None
