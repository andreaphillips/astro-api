from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class HouseSystem(StrEnum):
    PLACIDUS = "placidus"
    WHOLE_SIGN = "whole_sign"
    KOCH = "koch"
    EQUAL = "equal"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Auth
    astro_api_key: str = Field(..., description="Shared secret required on all /v1/* endpoints.")

    # Geocoding
    nominatim_user_agent: str = "astro-api/1.0 (aphillipsr@gmail.com)"
    nominatim_timeout_seconds: float = 5.0

    # Astrology defaults
    default_house_system: HouseSystem = HouseSystem.PLACIDUS
    default_locale: str = "en_US"

    # Server
    port: int = 8000
    log_level: Literal["debug", "info", "warning", "error", "critical"] = "info"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
