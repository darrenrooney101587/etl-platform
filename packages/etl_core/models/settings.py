"""Minimal Django settings for reporting_seeder jobs.

This settings module is used when bootstrapping Django to support
etl_core.models ORM models during seed/refresh operations.
"""
import os

SECRET_KEY = os.environ.get("SECRET_KEY", "seeder-dev-insecure-key")
DEBUG = os.environ.get("DEBUG", "True") == "True"

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "etl_core.models.apps.bms",
    "etl_core.models.apps.bms_reporting",
    "etl_core.models.apps.account",
    "etl_core.models.apps.bms_security",
    "etl_core.models.apps.bms_organization",
]

# Configure database from environment variables (consistent with SeederConfig)
# We support specific DB_* vars or DATABASE_URL if parsed manually, but
# for simplicity in this minimal file we map the DB_* vars mostly used in dev.
db_default = {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": os.environ.get("DB_NAME", "postgres"),
    "USER": os.environ.get("DB_USER", "postgres"),
    "PASSWORD": os.environ.get("DB_PASSWORD", ""),
    "HOST": os.environ.get("DB_HOST", "localhost"),
    "PORT": os.environ.get("DB_PORT", "5432"),
}

# If DATABASE_URL is present, we could parse it, but let's stick to the broken-down
# vars which match the project's .env structure seen in SeederConfig.
# (If robust parsing is needed, we'd add dj_database_url dependency).

DATABASES = {
    "default": db_default
}

USE_TZ = True
TIME_ZONE = "UTC"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
