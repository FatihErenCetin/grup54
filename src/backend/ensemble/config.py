from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# .env her zaman repo kökünden yüklenir (cwd'den bağımsız — alt dizinden
# çalıştırınca sessizce varsayılana düşme tuzağı kapalı). Dosya yoksa atlanır.
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_REPO_ROOT / ".env"), extra="ignore")

    ENSEMBLE_MODE: Literal["local", "hosted"] = "local"

    # Tarayıcı CORS allowlist'i (#45) — asla "*". Env'de virgüllü tek satır
    # (CORS_ORIGINS=https://a.example,https://b.example). NoDecode: pydantic-settings
    # liste alanını JSON sanıp parse etmeye kalkmasın, ham string validator'a düşsün.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _decode_cors_origins(cls, v: object) -> object:
        # Env virgüllü tek satır gönderir (düz metin → liste); "*" hangi kaynaktan
        # gelirse gelsin güvenlik gereği açılışta reddedilir (#45).
        if isinstance(v, str):
            v = [parca.strip() for parca in v.split(",") if parca.strip()]
        if isinstance(v, (list, tuple)) and "*" in v:
            raise ValueError("CORS allowlist '*' içeremez (#45)")
        return v

    # Gemini (embeddings + judge) — key yoksa da Settings çökmemeli (fake adapter
    # key gerektirmez); key eksikliği yalnızca ResilientGeminiClient somutlaştırılırken kontrol edilir.
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-001"
    GEMINI_EMBEDDING_DIMENSIONS: int = 768
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
    GITHUB_BACKFILL_LIMIT: int = 50

    # Store — local: SQLite (repo kökünde, gitignored) · hosted: PostgreSQL DSN.
    # Varsayılan SQLite yolu: ensemble.db (repo kökü, .gitignore'da).
    DATABASE_URL: str = f"sqlite:///{_REPO_ROOT / 'ensemble.db'}"

    # Radar eşikleri (#151) — kalibrasyon (#29 threshold sweep) sonucu buraya
    # yazılır; şimdilik RadarService'in kendi nötr varsayılanlarıyla aynı.
    RADAR_WINDOW_DAYS: int = 14
    RADAR_MIN_JACCARD: float = 0.0
    RADAR_MIN_SIMILARITY: float = 0.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
