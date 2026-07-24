from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# .env her zaman repo kökünden yüklenir (cwd'den bağımsız — alt dizinden
# çalıştırınca sessizce varsayılana düşme tuzağı kapalı). Dosya yoksa atlanır.
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_REPO_ROOT / ".env"), extra="ignore")

    ENSEMBLE_MODE: Literal["local", "hosted"] = "local"

    # LLM saglayicisi calisma modundan bagimsizdir (#78): local engine Gemini,
    # hosted engine Ollama (ayni makinede) kullanabilir. Varsayilan, geriye
    # uyumluluk icin Gemini'dir.
    LLM_PROVIDER: Literal["gemini", "ollama"] = "gemini"

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

    # Ollama tam-yerel modu (#78). Loopback zorunlulugu repo baglaminin yanlis
    # yapilandirma ile baska bir makineye tasinmasini engeller.
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_MODEL: str = "llama3.2"
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"
    OLLAMA_EMBEDDING_DIMENSIONS: int = 768
    OLLAMA_TIMEOUT_S: float = 60.0
    OLLAMA_MAX_RETRIES: int = 2

    @field_validator("OLLAMA_BASE_URL")
    @classmethod
    def _validate_local_ollama_url(cls, value: str) -> str:
        normalized = value.rstrip("/")
        parsed = urlparse(normalized)
        if parsed.scheme != "http" or parsed.hostname not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise ValueError("OLLAMA_BASE_URL yerel bir HTTP loopback adresi olmali (#78)")
        return normalized

    # GitHub App (machine auth - ingest, #16). Hepsi opsiyonel - FakeGitHubAdapter
    # gerektirmez; eksikse GitHubAdapter/InstallationTokenCache somutlastirilirken
    # GitHubConfigError firlatilir.
    GITHUB_APP_ID: str | None = None
    GITHUB_APP_PRIVATE_KEY_PATH: str | None = None
    # Hosted alternatifi (#186) - Fly/Render secret'lari env-STRING, mount'lu
    # dosya degil. PATH varsa PATH kazanir (mevcut local akis); PATH yoksa bu
    # alanin (PEM icerigi, ham metin) kullanilir.
    GITHUB_APP_PRIVATE_KEY: str | None = None
    GITHUB_APP_INSTALLATION_ID: str | None = None
    GITHUB_REPO_OWNER: str | None = None
    GITHUB_REPO_NAME: str | None = None
    GITHUB_DEFAULT_BRANCH: str = "main"
    GITHUB_BACKFILL_LIMIT: int = 50
    # Webhook receiver (#62) - X-Hub-Signature-256 HMAC dogrulamasi icin.
    # Yoksa receiver 503 doner (dogrulanamayan webhook kabul edilmez).
    GITHUB_WEBHOOK_SECRET: str | None = None

    # Store — local: SQLite (repo kökünde, gitignored) · hosted: PostgreSQL DSN.
    # Varsayılan SQLite yolu: ensemble.db (repo kökü, .gitignore'da).
    DATABASE_URL: str = f"sqlite:///{_REPO_ROOT / 'ensemble.db'}"

    # Radar eşikleri (#151, kalibre: #18) — 0.0/0.0 kalibrasyon SONUCU, placeholder
    # değil: sweep (#29) 60 kombinasyonun hiçbirinde FP eklemeden recall
    # kazandırmıyor — mevcut korpuste FP'yi engelleyen gate/judge katmanı,
    # jaccard/similarity değil. Detay + şerhler: eval/kalibrasyon-raporu.md
    RADAR_WINDOW_DAYS: int = 14
    RADAR_MIN_JACCARD: float = 0.0
    RADAR_MIN_SIMILARITY: float = 0.0

    # --- Hosted public demo sertlestirme (#63) — VARSAYILAN KAPALI ---
    # local/dev davranisi bu bayrak acilmadan HIC degismez.
    DEMO_MODE: bool = False
    DEMO_RATE_WINDOW_S: int = 60
    DEMO_AI_RATE_LIMIT: int = 10  # IP basina, KULLANICI-GIRDILI AI yollari (/query, /scope/check)
    DEMO_AI_GLOBAL_LIMIT: int = 60  # tum IP'ler toplami — asil fatura tavani
    DEMO_RATE_LIMIT: int = 120  # IP basina, diger (poll'lanan) yollar
    DEMO_CACHE_TTL_S: int = 900
    DEMO_CACHE_MAX_ENTRIES: int = 256

    @model_validator(mode="after")
    def _validate_demo_mode(self) -> "Settings":
        # Fail-closed acilis: DEMO_MODE acikken tek read-only repo'ya sabitlenme
        # ZORUNLU (#63) - yoksa uygulama hic ayaga kalkmaz (auth_blocked kanit
        # yerine tasarim-anı garanti).
        if self.DEMO_MODE and not (self.GITHUB_REPO_OWNER and self.GITHUB_REPO_NAME):
            raise ValueError(
                "DEMO_MODE tek repo'ya sabitlenmeden acilamaz (#63) — "
                "GITHUB_REPO_OWNER ve GITHUB_REPO_NAME zorunlu"
            )
        _positive_fields = (
            "DEMO_RATE_WINDOW_S",
            "DEMO_AI_RATE_LIMIT",
            "DEMO_AI_GLOBAL_LIMIT",
            "DEMO_RATE_LIMIT",
            "DEMO_CACHE_TTL_S",
            "DEMO_CACHE_MAX_ENTRIES",
        )
        for field in _positive_fields:
            if getattr(self, field) <= 0:
                raise ValueError(f"{field} pozitif olmali (#63)")
        return self

    @property
    def demo_repo_full_name(self) -> str | None:
        if not (self.GITHUB_REPO_OWNER and self.GITHUB_REPO_NAME):
            return None
        return f"{self.GITHUB_REPO_OWNER}/{self.GITHUB_REPO_NAME}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
