"""Slack connector implementing the SlackNotifier protocol."""
from __future__ import annotations

import logging
from datetime import date
from typing import List, Optional

from django.conf import settings
from django.utils import timezone
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from observability.models import (
    NotificationSignal,
    NotificationSignalGroup,
    NotificationSignalGroupActivity,
)
from observability.services.grouping import SlackNotifier

logger = logging.getLogger(__name__)


class SlackConnector(SlackNotifier):
    """Concrete Slack notifier using slack_sdk."""

    def __init__(self, token: Optional[str] = None, shared_channel_id: Optional[str] = None) -> None:
        slack_token = token or getattr(settings, "SLACK_BOT_TOKEN", "")
        self.client = WebClient(token=slack_token) if slack_token else None
        self.shared_channel_id = shared_channel_id or getattr(settings, "SLACK_SHARED_CHANNEL_ID", "")

    def post_group_opened(self, group: NotificationSignalGroup, signal: NotificationSignal) -> None:
        if not self.client or not self.shared_channel_id:
            return
        if group.slack_root_ts and group.slack_channel_id:
            try:
                self.client.chat_update(
                    channel=group.slack_channel_id,
                    ts=group.slack_root_ts,
                    text=self._fallback_text(group),
                    blocks=self._build_blocks(group, include_ack_button=True),
                )
            except SlackApiError:
                logger.warning("Failed to update Slack message for group %s", group.id, exc_info=True)
            return
        try:
            response = self.client.chat_postMessage(
                channel=self.shared_channel_id,
                text=self._fallback_text(group),
                blocks=self._build_blocks(group, include_ack_button=True),
            )
            group.slack_channel_id = response.get("channel")
            group.slack_root_ts = response.get("ts")
            group.opened_notified_at = timezone.now()
            group.last_slack_updated_at = timezone.now()
            group.save(update_fields=["slack_channel_id", "slack_root_ts", "opened_notified_at", "last_slack_updated_at"])
            self._log_activity(group, "slack_posted", {"channel": group.slack_channel_id, "ts": group.slack_root_ts})
        except SlackApiError:
            logger.warning("Failed to post Slack message for group %s", group.id, exc_info=True)

    def update_group_acknowledged(self, group: NotificationSignalGroup, slack_user_id: Optional[str]) -> None:
        if not self.client or not group.slack_root_ts or not group.slack_channel_id:
            return
        if group.last_slack_updated_at and (timezone.now() - group.last_slack_updated_at).total_seconds() < 300:
            return
        try:
            context = self._ack_context(slack_user_id)
            blocks = self._build_blocks(group, include_ack_button=False, status_context=context)
            self.client.chat_update(
                channel=group.slack_channel_id,
                ts=group.slack_root_ts,
                text=self._fallback_text(group),
                blocks=blocks,
            )
            group.last_slack_updated_at = timezone.now()
            group.slack_message_hash = context
            group.save(update_fields=["last_slack_updated_at", "slack_message_hash"])
            self._log_activity(
                group,
                "slack_updated",
                {"channel": group.slack_channel_id, "ts": group.slack_root_ts, "context": context},
            )
        except SlackApiError:
            logger.warning("Failed to update Slack message for group %s", group.id, exc_info=True)

    def send_owner_reminder(self, group: NotificationSignalGroup, slack_user_id: str) -> None:
        if not self.client:
            return
        try:
            channel_resp = self.client.conversations_open(users=slack_user_id)
            channel_id = channel_resp.get("channel", {}).get("id")
            if not channel_id:
                logger.warning("Slack DM channel not returned for user %s: %s", slack_user_id, channel_resp)
                return
            self.client.chat_postMessage(
                channel=channel_id,
                text=self._fallback_text(group),
                blocks=self._build_blocks(group, include_ack_button=False),
            )
        except SlackApiError:
            logger.warning("Failed to send reminder for group %s to user %s", group.id, slack_user_id, exc_info=True)

    def post_digest(self, groups: List[NotificationSignalGroup], digest_date: date) -> None:
        if not self.client or not self.shared_channel_id:
            return
        lines = [
            f"S{group.current_severity} - {group.tenant_code} - {group.job_name} ({group.status})"
            for group in groups
        ]
        text = "Daily digest\n" + "\n".join(lines)
        try:
            self.client.chat_postMessage(channel=self.shared_channel_id, text=text)
        except SlackApiError:
            logger.warning("Failed to post digest", exc_info=True)

    def _build_blocks(self, group: SignalGroup, include_ack_button: bool, status_context: Optional[str] = None) -> list:
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*S{group.current_severity}* - {group.tenant_code} / {group.job_name} - {group.signal_type}",
                },
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"Last seen: {group.last_seen_at.isoformat()}"},
                    {"type": "mrkdwn", "text": f"Count: {group.count_total}"},
                ],
            },
        ]
        if include_ack_button:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Acknowledge"},
                            "action_id": "signal_group_ack",
                            "value": str(group.id),
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Open in Notifications"},
                            "url": group.ui_url,
                        },
                    ],
                }
            )
        else:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Open in Notifications"},
                            "url": group.ui_url,
                        }
                    ],
                }
            )
        if status_context:
            blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": status_context}]})
        return blocks

    @staticmethod
    def _ack_context(slack_user_id: Optional[str]) -> str:
        if slack_user_id:
            return f"Acknowledged by <@{slack_user_id}>"
        return "Acknowledged"

    @staticmethod
    def _fallback_text(group: SignalGroup) -> str:
        return f"S{group.current_severity} {group.job_name} {group.signal_type}"

    @staticmethod
    def _log_activity(group: SignalGroup, action: str, metadata: dict) -> None:
        SignalGroupActivity.objects.create(
            signal_group=group,
            actor_type=SignalGroupActivity.ActorType.SYSTEM,
            actor_user_id=None,
            action=action,
            metadata_json=metadata,
        )
