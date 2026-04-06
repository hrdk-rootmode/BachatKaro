from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    api_base_url: str
    request_timeout_seconds: float
    connect_timeout_seconds: float
    max_retries: int
    retry_base_delay_seconds: float
    admin_session_timeout_minutes: int
    admin_emails: tuple[str, ...]
    default_bearer_token: str
    firebase_api_key: str



def _parse_csv(value: str) -> tuple[str, ...]:
    if not value:
        return tuple()
    return tuple(item.strip().lower() for item in value.split(",") if item.strip())



def load_settings() -> Settings:
    return Settings(
        api_base_url=os.getenv("ADMIN_API_BASE_URL", "http://127.0.0.1:8000/api/v1").rstrip("/"),
        request_timeout_seconds=float(os.getenv("ADMIN_REQUEST_TIMEOUT_SECONDS", "10")),
        connect_timeout_seconds=float(os.getenv("ADMIN_CONNECT_TIMEOUT_SECONDS", "3")),
        max_retries=int(os.getenv("ADMIN_MAX_RETRIES", "3")),
        retry_base_delay_seconds=float(os.getenv("ADMIN_RETRY_BASE_DELAY_SECONDS", "0.6")),
        admin_session_timeout_minutes=int(os.getenv("ADMIN_SESSION_TIMEOUT_MINUTES", "60")),
        admin_emails=_parse_csv(os.getenv("ADMIN_EMAILS", "")),
        default_bearer_token=os.getenv("ADMIN_BEARER_TOKEN", "").strip(),
        firebase_api_key=os.getenv("FIREBASE_API_KEY", "").strip(),
    )
