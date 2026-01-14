"""Entrypoint for running the Django API service."""
from __future__ import annotations

from django.core.management import execute_from_command_line

from observability.bootstrap import bootstrap


def main() -> None:
    bootstrap()
    execute_from_command_line(["manage.py", "runserver", "0.0.0.0:8000"])


if __name__ == "__main__":
    main()
