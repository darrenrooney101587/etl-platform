"""Job that dispatches DM reminders for active signal groups."""
from __future__ import annotations

from typing import List

from observability.bootstrap import bootstrap
from observability.services.grouping import SignalService
from observability.services.slack_connector import SlackConnector


def entrypoint(argv: List[str]) -> int:
    bootstrap()
    service = SignalService(notifier=SlackConnector())
    service.send_reminders()
    return 0


JOB = (entrypoint, "Dispatch owner reminders for active signal groups")
