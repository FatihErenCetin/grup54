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


@lru_cache
def get_settings() -> Settings:
    return Settings()
