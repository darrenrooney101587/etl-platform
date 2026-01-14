"""Minimal Django settings for the observability notification service."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Tuple
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent


def _parse_database_url(url: str) -> Dict[str, object]:
    parsed = urlparse(url)
    engine = parsed.scheme
    if engine.startswith("postgres"):
        engine_path = "django.db.backends.postgresql"
    elif engine.startswith("sqlite"):
        engine_path = "django.db.backends.sqlite3"
    else:
        engine_path = "django.db.backends.postgresql"

    return {
        "ENGINE": engine_path,
        "NAME": parsed.path.lstrip("/") or ":memory:",
        "USER": parsed.username or "",
        "PASSWORD": parsed.password or "",
        "HOST": parsed.hostname or "",
        "PORT": parsed.port or "",
    }


SECRET_KEY = os.getenv("SECRET_KEY", "unsafe-secret-key")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
ALLOWED_HOSTS: Tuple[str, ...] = ("*",)

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    DATABASES = {"default": _parse_database_url(DATABASE_URL)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.getenv("SQLITE_PATH", str(BASE_DIR / "db.sqlite3")),
        }
    }

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "observability.appconfig.ObservabilityConfig",
]

MIDDLEWARE: list[str] = []
ROOT_URLCONF = "observability.routes"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
]

USE_TZ = True
TIME_ZONE = "UTC"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")
INTERNAL_INGEST_TOKEN = os.getenv("INTERNAL_INGEST_TOKEN", "")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")
SLACK_SHARED_CHANNEL_ID = os.getenv("SLACK_SHARED_CHANNEL_ID", "")

REOPEN_WINDOW_HOURS = int(os.getenv("REOPEN_WINDOW_HOURS", "24"))
ACTIVE_WINDOW_MINUTES = int(os.getenv("ACTIVE_WINDOW_MINUTES", "120"))
REMINDER_T2_HOURS = int(os.getenv("REMINDER_T2_HOURS", "2"))
REMINDER_T8_HOURS = int(os.getenv("REMINDER_T8_HOURS", "8"))
DAILY_DIGEST_TIME = os.getenv("DAILY_DIGEST_TIME", "09:00")
AUTO_ASSIGN_ON_ACK = os.getenv("AUTO_ASSIGN_ON_ACK", "false").lower() == "true"
