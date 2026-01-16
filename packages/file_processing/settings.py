"""Minimal Django settings for file_processing jobs and services.

Used to bootstrap Django when consuming `etl_database_schema` models.
"""
from __future__ import annotations

import os

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "etl_database_schema.apps.bms",
    "etl_database_schema.apps.bms_reporting",
]

db_default = {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": os.environ.get("DB_NAME", "postgres"),
    "USER": os.environ.get("DB_USER", "postgres"),
    "PASSWORD": os.environ.get("DB_PASSWORD", ""),
    "HOST": os.environ.get("DB_HOST", "localhost"),
    "PORT": os.environ.get("DB_PORT", "5432"),
}

DATABASES = {
    "default": db_default,
}

USE_TZ = True
TIME_ZONE = "UTC"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
