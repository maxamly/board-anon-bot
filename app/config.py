from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str = Field(default="", alias="BOT_TOKEN")
    database_url: str = Field(default="sqlite:///database.db", alias="DATABASE_URL")
    superadmin_ids: list[int] = Field(default_factory=list, alias="SUPERADMIN_IDS")
    default_rate_limit_seconds: int = Field(default=120, alias="DEFAULT_RATE_LIMIT_SECONDS")
    default_max_text_length: int = Field(default=300, alias="DEFAULT_MAX_TEXT_LENGTH")
    polling_timeout: int = Field(default=10, alias="POLLING_TIMEOUT")
    default_locale: str = Field(default="ru", alias="DEFAULT_LOCALE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("superadmin_ids", mode="before")
    @classmethod
    def _parse_superadmin_ids(cls, value: object) -> list[int]:
        if value is None:
            return []
        if isinstance(value, int):
            return [value]
        if isinstance(value, str):
            return [int(item.strip()) for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            parsed: list[int] = []
            for item in value:
                if isinstance(item, (str, int)):
                    parsed.append(int(item))
            return parsed
        return []


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
