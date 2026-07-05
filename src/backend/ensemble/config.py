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


@lru_cache
def get_settings() -> Settings:
    return Settings()
