"""Django bootstrap helper for standalone jobs and tests."""
from __future__ import annotations

import os
from typing import Optional

import django
from django.conf import settings


def bootstrap(settings_module: Optional[str] = None) -> None:
    """Configure and initialize Django once."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module or "observability.django_settings")
    if not settings.configured:
        django.setup()
    else:
        try:
            django.setup()
        except RuntimeError:
            # Already configured; ignore
            return
