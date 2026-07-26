import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from ensemble.config import Settings, get_settings

_REPO_ROOT = Path(__file__).resolve().parents[2]


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


# --- Hosted demo sertlestirme (#63) ---


def test_demo_mode_varsayilan_kapali(monkeypatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    assert Settings(_env_file=None).DEMO_MODE is False


def test_demo_ayarlari_varsayilan_degerler():
    settings = Settings(_env_file=None)
    assert settings.DEMO_RATE_WINDOW_S == 60
    assert settings.DEMO_AI_RATE_LIMIT == 10
    assert settings.DEMO_AI_GLOBAL_LIMIT == 60
    assert settings.DEMO_RATE_LIMIT == 120
    assert settings.DEMO_CACHE_TTL_S == 900
    assert settings.DEMO_CACHE_MAX_ENTRIES == 1024
    assert settings.demo_repo_full_name is None


def test_demo_ai_rate_limit_sifirsa_reddedilir():
    with pytest.raises(ValidationError, match="pozitif"):
        Settings(_env_file=None, DEMO_AI_RATE_LIMIT=0)


def test_demo_mode_acikken_repo_eksikse_acilista_hata():
    with pytest.raises(ValidationError, match="#63"):
        Settings(_env_file=None, DEMO_MODE=True)


def test_demo_mode_acikken_repo_doluysa_acilir():
    settings = Settings(
        _env_file=None, DEMO_MODE=True, GITHUB_REPO_OWNER="acme", GITHUB_REPO_NAME="demo"
    )
    assert settings.DEMO_MODE is True
    assert settings.demo_repo_full_name == "acme/demo"


# --- Dokuman <-> kod drift (#63 ISTENEN 3) ---
#
# docs/sprint3-kontratlar.md Ek F/F1'deki "DONMUS" kod blogu ile config.py'deki
# gercek varsayilan bu PR'de tam da BURADA (256 vs 1024) kaymisti. Regex satir
# numarasina degil "### F1" basligina baglanir - kirilgan olmasin diye.


def test_demo_cache_max_entries_dokuman_ile_ayni():
    doc_text = (_REPO_ROOT / "docs" / "sprint3-kontratlar.md").read_text(encoding="utf-8")

    f1_start = doc_text.index("### F1")
    f1_section = doc_text[f1_start:]
    code_block_match = re.search(r"```python\n(.*?)```", f1_section, re.DOTALL)
    assert code_block_match, "Ek F/F1 altinda ```python kod blogu bulunamadi"

    value_match = re.search(
        r"DEMO_CACHE_MAX_ENTRIES:\s*int\s*=\s*(\d+)", code_block_match.group(1)
    )
    assert value_match, "F1 kod blogunda DEMO_CACHE_MAX_ENTRIES tanimi bulunamadi"

    doc_value = int(value_match.group(1))
    code_value = Settings(_env_file=None).DEMO_CACHE_MAX_ENTRIES

    assert doc_value == code_value, (
        f"docs/sprint3-kontratlar.md Ek F/F1 DEMO_CACHE_MAX_ENTRIES={doc_value} "
        f"ile config.py varsayilani={code_value} birbirinden kaymis"
    )


# --- Kullanici girisi (#79 daraltilmis dilim) ---


def test_auth_varsayilan_alanlar_bos():
    settings = Settings(_env_file=None)
    assert settings.GITHUB_OAUTH_CLIENT_ID is None
    assert settings.GITHUB_OAUTH_CLIENT_SECRET is None
    assert settings.AUTH_SESSION_SECRET is None
    assert settings.AUTH_COOKIE_DOMAIN is None
    assert settings.AUTH_POST_LOGIN_URL == "/radar"


def test_auth_enabled_ucu_de_bos_ise_false():
    assert Settings(_env_file=None).auth_enabled is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"GITHUB_OAUTH_CLIENT_ID": "x"},
        {"GITHUB_OAUTH_CLIENT_SECRET": "y"},
        {"AUTH_SESSION_SECRET": "z"},
        {"GITHUB_OAUTH_CLIENT_ID": "x", "GITHUB_OAUTH_CLIENT_SECRET": "y"},
    ],
)
def test_auth_enabled_tek_biri_veya_ikisi_eksikse_false(kwargs):
    assert Settings(_env_file=None, **kwargs).auth_enabled is False


def test_auth_enabled_ucu_de_doluysa_true():
    settings = Settings(
        _env_file=None,
        GITHUB_OAUTH_CLIENT_ID="x",
        GITHUB_OAUTH_CLIENT_SECRET="y",
        AUTH_SESSION_SECRET="z",
    )
    assert settings.auth_enabled is True
