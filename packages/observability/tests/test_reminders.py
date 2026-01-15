"""Reminder and digest scheduling tests."""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from observability.bootstrap import bootstrap

bootstrap()

from observability.models import (  # noqa: E402
    NotificationSignalGroup,
    NotificationAgencyOwner,
    NotificationUserSlackMap,
)
from observability.services.grouping import NullSlackNotifier, SignalPayload, SignalService
from observability.tests.base import ObservabilityTestCase


class ReminderTests(ObservabilityTestCase):
    def _service(self) -> SignalService:
        return SignalService(notifier=NullSlackNotifier())

    def _payload(self) -> SignalPayload:
        return SignalPayload(
            tenant_id="agency-reminder",
            tenant_code="TEN-R",
            job_name="job-reminder",
            source="airflow",
            signal_type="job_failed",
            severity=1,
            summary="failure",
            details_json={},
        )

    def test_reminder_rate_limit(self) -> None:
        NotificationAgencyOwner.objects.create(agency_id="agency-reminder", primary_owner_user_id="owner-1")
        NotificationUserSlackMap.objects.create(user_id="owner-1", slack_user_id="U123")
        service = self._service()
        _, group = service.ingest_signal(self._payload())
        earlier = timezone.now() - timedelta(hours=3)
        group.last_seen_at = earlier
        group.first_seen_at = earlier
        group.save(update_fields=["last_seen_at", "first_seen_at"])

        first = service.send_reminders()
        self.assertEqual(len(first), 1)
        refreshed = NotificationSignalGroup.objects.get(id=group.id)
        self.assertIsNotNone(refreshed.last_reminded_at)
        second = service.send_reminders()
        self.assertEqual(len(second), 0)

    def test_daily_digest_once_per_day(self) -> None:
        service = self._service()
        service.ingest_signal(self._payload())
        first = service.send_daily_digest()
        self.assertGreaterEqual(len(first), 1)
        second = service.send_daily_digest()
        self.assertEqual(len(second), 0)
