from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENSEMBLE_MODE: Literal["local", "hosted"] = "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
