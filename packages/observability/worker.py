"""Lightweight worker loop for reminders and daily digest."""
from __future__ import annotations

import argparse
import time
from datetime import date, time as time_cls
from typing import Optional

from django.conf import settings
from django.utils import timezone

from observability.bootstrap import bootstrap
from observability.services.grouping import SignalService
from observability.services.slack_connector import SlackConnector


def _parse_digest_time(value: str) -> time_cls:
    try:
        hours, minutes = value.split(":")
        return time_cls(int(hours), int(minutes))
    except Exception:
        return time_cls(9, 0)


def run_worker(interval_minutes: int) -> None:
    bootstrap()
    service = SignalService(notifier=SlackConnector())
    digest_target = _parse_digest_time(getattr(settings, "DAILY_DIGEST_TIME", "09:00"))
    now = timezone.now()
    if now.time() >= digest_target:
        service.send_daily_digest(now.date())
    service.send_reminders(now)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run observability worker loop.")
    parser.add_argument("--interval-minutes", type=int, default=15, help="Reminder interval in minutes.")
    args = parser.parse_args()
    run_worker(args.interval_minutes)


if __name__ == "__main__":
    main()
