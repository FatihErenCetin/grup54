from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# .env her zaman repo kökünden yüklenir (cwd'den bağımsız — alt dizinden
# çalıştırınca sessizce varsayılana düşme tuzağı kapalı). Dosya yoksa atlanır.
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_REPO_ROOT / ".env"), extra="ignore")

    ENSEMBLE_MODE: Literal["local", "hosted"] = "local"

    # Gemini (embeddings + judge) — key yoksa da Settings çökmemeli (fake adapter
    # key gerektirmez); key eksikliği yalnızca ResilientGeminiClient somutlaştırılırken kontrol edilir.
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_TIMEOUT_S: float = 10.0
    GEMINI_MAX_RETRIES: int = 3

    # GitHub App (machine auth - ingest, #16). Hepsi opsiyonel - FakeGitHubAdapter
    # gerektirmez; eksikse GitHubAdapter/InstallationTokenCache somutlastirilirken
    # GitHubConfigError firlatilir.
    GITHUB_APP_ID: str | None = None
    GITHUB_APP_PRIVATE_KEY_PATH: str | None = None
    GITHUB_APP_INSTALLATION_ID: str | None = None
    GITHUB_REPO_OWNER: str | None = None
    GITHUB_REPO_NAME: str | None = None
    GITHUB_DEFAULT_BRANCH: str = "main"


@lru_cache
def get_settings() -> Settings:
    return Settings()
