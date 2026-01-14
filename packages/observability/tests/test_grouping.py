"""Grouping and routing tests."""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from observability.models import SignalGroup, TenantOwner, JobOwnerOverride
from observability.services.grouping import NullSlackNotifier, SignalPayload, SignalService
from observability.tests.base import ObservabilityTestCase


class TrackingNotifier(NullSlackNotifier):
    def __init__(self) -> None:
        self.opened_calls: list[str] = []
        self.ack_calls: list[str] = []

    def post_group_opened(self, group: SignalGroup, signal) -> None:  # type: ignore[override]
        self.opened_calls.append(str(group.id))

    def update_group_acknowledged(self, group: SignalGroup, slack_user_id):  # type: ignore[override]
        self.ack_calls.append(str(group.id))


class GroupingTests(ObservabilityTestCase):
    def _payload(self, severity: int = 2) -> SignalPayload:
        return SignalPayload(
            tenant_id="tenant-1",
            tenant_code="TEN",
            job_name="demo-job",
            source="airflow",
            signal_type="job_failed",
            severity=severity,
            summary="Example failure",
            details_json={},
        )

    def test_create_and_update_existing_group(self) -> None:
        notifier = TrackingNotifier()
        service = SignalService(notifier=notifier)

        _, group_first = service.ingest_signal(self._payload(severity=2))
        _, group_second = service.ingest_signal(self._payload(severity=3))

        self.assertEqual(group_first.id, group_second.id)
        refreshed = SignalGroup.objects.get(id=group_first.id)
        self.assertEqual(refreshed.count_total, 2)
        self.assertEqual(refreshed.current_severity, 2)
        self.assertEqual(len(notifier.opened_calls), 1)

    def test_reopen_within_window(self) -> None:
        service = SignalService(notifier=NullSlackNotifier())
        _, group = service.ingest_signal(self._payload(severity=1))
        service.close_group(str(group.id), actor_user_id=None)
        group.refresh_from_db()
        group.closed_at = timezone.now() - timedelta(hours=1)
        group.save()

        _, reopened_group = service.ingest_signal(self._payload(severity=1))
        reopened_group.refresh_from_db()
        self.assertEqual(reopened_group.status, SignalGroup.Status.OPEN)
        self.assertEqual(reopened_group.count_total, 2)

    def test_routing_prefers_job_override(self) -> None:
        TenantOwner.objects.create(
            tenant_id="tenant-1", primary_owner_user_id="tenant-owner", owning_team_id="team-1"
        )
        JobOwnerOverride.objects.create(tenant_id="tenant-1", job_name="demo-job", owner_user_id="override-user")

        service = SignalService(notifier=NullSlackNotifier())
        _, group = service.ingest_signal(self._payload())

        self.assertEqual(group.assigned_to_user_id, "override-user")
        self.assertIsNone(group.assigned_team_id)

    def test_acknowledgement_idempotent(self) -> None:
        notifier = TrackingNotifier()
        service = SignalService(notifier=notifier)
        _, group = service.ingest_signal(self._payload())

        service.acknowledge_group(str(group.id), "user-1")
        service.acknowledge_group(str(group.id), "user-1")
        group.refresh_from_db()

        self.assertEqual(group.status, SignalGroup.Status.ACKNOWLEDGED)
        self.assertEqual(len(notifier.ack_calls), 1)
