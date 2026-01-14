"""Job that posts a daily digest to the shared Slack channel."""
from __future__ import annotations

from typing import List

from observability.bootstrap import bootstrap
from observability.services.grouping import SignalService
from observability.services.slack_connector import SlackConnector


def entrypoint(argv: List[str]) -> int:
    bootstrap()
    service = SignalService(notifier=SlackConnector())
    service.send_daily_digest()
    return 0


JOB = (entrypoint, "Post daily digest for open signal groups")
