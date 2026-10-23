# backend/config.py
from functools import lru_cache
from urllib.parse import urlparse

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_VERSION = "1.0.0"


def _is_http_url(value: str | None) -> bool:
    if not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    make_webhook_url: str | None = None
    make_webhook_secret: str | None = None
    frontend_origin: str = "http://localhost:5500,http://127.0.0.1:5500"
    request_timeout_seconds: float = Field(default=120.0, gt=0, le=600)
    demo_mode: bool = False

    @property
    def frontend_origins(self) -> list[str]:
        origins: list[str] = []
        for raw in self.frontend_origin.split(","):
            origin = raw.strip().rstrip("/")
            if origin and origin != "*" and _is_http_url(origin):
                origins.append(origin)
        return origins

    @property
    def make_configured(self) -> bool:
        return _is_http_url(self.make_webhook_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()