"""Service layer implementing signal ingestion, grouping, and workflow actions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import uuid
from typing import Any, Dict, Iterable, List, Optional, Protocol, Tuple

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from etl_core.support.fingerprinting import compute_fingerprint, normalize_error_message
from observability.models import (
    NotificationJobOwnerOverride,
    NotificationSignal,
    NotificationSignalGroup,
    NotificationSignalGroupActivity,
    NotificationAgencyOwner,
    NotificationUserSlackMap,
    OwnerResolution,
)


class SlackNotifier(Protocol):
    """Protocol describing Slack side-effects."""

    def post_group_opened(self, group: NotificationSignalGroup, signal: NotificationSignal) -> None:
        ...

    def update_group_acknowledged(self, group: NotificationSignalGroup, slack_user_id: Optional[str]) -> None:
        ...

    def send_owner_reminder(self, group: NotificationSignalGroup, slack_user_id: str) -> None:
        ...

    def post_digest(self, groups: List[NotificationSignalGroup], digest_date: date) -> None:
        ...


class NullSlackNotifier:
    """No-op Slack notifier used for tests or disabled environments."""

    def post_group_opened(self, group: NotificationSignalGroup, signal: NotificationSignal) -> None:  # noqa: D401
        return

    def update_group_acknowledged(self, group: NotificationSignalGroup, slack_user_id: Optional[str]) -> None:  # noqa: D401
        return

    def send_owner_reminder(self, group: NotificationSignalGroup, slack_user_id: str) -> None:  # noqa: D401
        return

    def post_digest(self, groups: List[NotificationSignalGroup], digest_date: date) -> None:  # noqa: D401
        return


@dataclass(frozen=True)
class SignalPayload:
    """Payload accepted by the ingestion service."""

    tenant_id: str  # agency_id
    tenant_code: str  # agency_slug
    job_name: str
    source: str
    signal_type: str
    severity: int
    summary: str
    details_json: Dict[str, Any]
    occurred_at: Optional[datetime] = None
    run_id: Optional[str] = None
    task_id: Optional[str] = None
    stage: Optional[str] = None
    error_class: Optional[str] = None
    error_message: Optional[str] = None


class OwnerRouter:
    """Resolves ownership based on overrides and tenant defaults."""

    def resolve(self, tenant_id: str, job_name: str) -> OwnerResolution:
        tenant_override = NotificationJobOwnerOverride.objects.filter(agency_id=tenant_id, job_name=job_name).first()
        if tenant_override:
            return {
                "user_id": tenant_override.owner_user_id,
                "team_id": tenant_override.team_id,
            }

        global_override = NotificationJobOwnerOverride.objects.filter(agency_id__isnull=True, job_name=job_name).first()
        if global_override:
            return {
                "user_id": global_override.owner_user_id,
                "team_id": global_override.team_id,
            }

        tenant_owner = NotificationAgencyOwner.objects.filter(agency_id=tenant_id).first()
        if tenant_owner:
            if tenant_owner.primary_owner_user_id:
                return {"user_id": tenant_owner.primary_owner_user_id, "team_id": None}
            if tenant_owner.owning_team_id:
                return {"user_id": None, "team_id": tenant_owner.owning_team_id}

        return {"user_id": None, "team_id": None}


class SignalService:
    """Core business logic for signals, groups, and state changes."""

    def __init__(self, notifier: Optional[SlackNotifier] = None, owner_router: Optional[OwnerRouter] = None) -> None:
        self.notifier = notifier or NullSlackNotifier()
        self.owner_router = owner_router or OwnerRouter()

    def ingest_signal(self, payload: SignalPayload) -> Tuple[NotificationSignal, NotificationSignalGroup]:
        """Persist a signal and update or create its group."""
        occurred_at = payload.occurred_at or timezone.now()
        normalized_message = normalize_error_message(payload.error_message or payload.summary)
        fingerprint = compute_fingerprint(
            [
                payload.tenant_id,
                payload.signal_type,
                payload.job_name,
                payload.stage or "",
                payload.error_class or "",
                normalized_message,
            ]
        )

        with transaction.atomic():
            signal = NotificationSignal.objects.create(
                occurred_at=occurred_at,
                source=payload.source,
                signal_type=payload.signal_type,
                severity=payload.severity,
                agency_id=payload.tenant_id,
                agency_slug=payload.tenant_code,
                job_name=payload.job_name,
                run_id=payload.run_id,
                task_id=payload.task_id,
                stage=payload.stage,
                error_class=payload.error_class,
                error_message=payload.error_message,
                fingerprint=fingerprint,
                summary=payload.summary,
                details_json=payload.details_json,
            )
            group, created, severity_escalated = self._upsert_group(signal, payload, normalized_message)

        if created or severity_escalated:
            self.notifier.post_group_opened(group, signal)

        return signal, group

    def _upsert_group(
        self, signal: NotificationSignal, payload: SignalPayload, normalized_message: str
    ) -> Tuple[NotificationSignalGroup, bool, bool]:
        now = timezone.now()
        reopen_window = timedelta(hours=getattr(settings, "REOPEN_WINDOW_HOURS", 24))
        active_group = (
            NotificationSignalGroup.objects.select_for_update()
            .filter(agency_id=payload.tenant_id, fingerprint=signal.fingerprint, status__in=self._active_statuses())
            .first()
        )

        created = False
        severity_escalated = False
        if active_group:
            previous_severity = active_group.current_severity
            self._update_group_from_signal(active_group, signal, payload, normalized_message)
            severity_escalated = active_group.current_severity < previous_severity
            active_group.save()
            return active_group, created, severity_escalated

        latest_group = (
            NotificationSignalGroup.objects.select_for_update()
            .filter(agency_id=payload.tenant_id, fingerprint=signal.fingerprint)
            .order_by("-closed_at", "-last_seen_at")
            .first()
        )

        if latest_group and latest_group.status == NotificationSignalGroup.Status.CLOSED and latest_group.closed_at:
            if (now - latest_group.closed_at) <= reopen_window:
                latest_group.status = NotificationSignalGroup.Status.OPEN
                latest_group.closed_at = None
                self._update_group_from_signal(latest_group, signal, payload, normalized_message)
                latest_group.save()
                self._log_activity(latest_group, "reopened", {"severity": latest_group.current_severity})
                return latest_group, created, False

        owner = self.owner_router.resolve(payload.tenant_id, payload.job_name)
        group_id = uuid.uuid4()
        group = NotificationSignalGroup.objects.create(
            id=group_id,
            fingerprint=signal.fingerprint,
            status=NotificationSignalGroup.Status.OPEN,
            current_severity=signal.severity,
            agency_id=payload.tenant_id,
            agency_slug=payload.tenant_code,
            job_name=payload.job_name,
            signal_type=payload.signal_type,
            first_seen_at=signal.occurred_at,
            last_seen_at=signal.occurred_at,
            count_total=1,
            count_24h=self._count_24h(signal),
            last_signal=signal,
            assigned_to_user_id=owner.get("user_id"),
            assigned_team_id=owner.get("team_id"),
            ui_url=self._build_ui_url(str(group_id)),
        )
        created = True
        self._log_activity(group, "opened", {"normalized_error": normalized_message})
        return group, created, True

    def _update_group_from_signal(
        self, group: NotificationSignalGroup, signal: NotificationSignal, payload: SignalPayload, normalized_message: str
    ) -> None:
        group.update_counts(signal.occurred_at)
        group.current_severity = min(group.current_severity, signal.severity)
        group.last_signal = signal
        group.tenant_code = payload.tenant_code
        group.job_name = payload.job_name
        group.signal_type = payload.signal_type
        group.count_24h = self._count_24h(signal)

    def acknowledge_group(self, group_id: str, actor_user_id: str) -> NotificationSignalGroup:
        now = timezone.now()
        updated = False
        with transaction.atomic():
            group = NotificationSignalGroup.objects.select_for_update().get(id=group_id)
            if group.status == NotificationSignalGroup.Status.OPEN:
                group.status = NotificationSignalGroup.Status.ACKNOWLEDGED
                group.acknowledged_at = now
                group.acknowledged_by_user_id = actor_user_id
                if getattr(settings, "AUTO_ASSIGN_ON_ACK", False) and not group.assigned_to_user_id:
                    group.assigned_to_user_id = actor_user_id
                group.save()
                self._log_activity(group, "acknowledged", {"actor_user_id": actor_user_id})
                updated = True

        if updated:
            slack_user_id = self._slack_user_for_actor(actor_user_id)
            self.notifier.update_group_acknowledged(group, slack_user_id)
        return group

    def assign_group(self, group_id: str, user_id: Optional[str], team_id: Optional[str]) -> NotificationSignalGroup:
        with transaction.atomic():
            group = NotificationSignalGroup.objects.select_for_update().get(id=group_id)
            group.assigned_to_user_id = user_id
            group.assigned_team_id = team_id
            group.save()
            self._log_activity(group, "assigned", {"user_id": user_id, "team_id": team_id})
        return group

    def snooze_group(self, group_id: str, until: datetime, actor_user_id: Optional[str]) -> NotificationSignalGroup:
        with transaction.atomic():
            group = NotificationSignalGroup.objects.select_for_update().get(id=group_id)
            group.status = NotificationSignalGroup.Status.SNOOZED
            group.snoozed_until = until
            group.save()
            self._log_activity(group, "snoozed", {"until": until.isoformat(), "actor_user_id": actor_user_id})
        return group

    def close_group(self, group_id: str, actor_user_id: Optional[str]) -> NotificationSignalGroup:
        with transaction.atomic():
            group = NotificationSignalGroup.objects.select_for_update().get(id=group_id)
            group.status = NotificationSignalGroup.Status.CLOSED
            group.closed_at = timezone.now()
            group.save()
            self._log_activity(group, "closed", {"actor_user_id": actor_user_id})
        return group

    def list_groups(
        self,
        status: Optional[str] = None,
        assigned_to: Optional[str] = None,
        tenant_id: Optional[str] = None,
        job_name: Optional[str] = None,
        severity: Optional[int] = None,
        updated_since: Optional[datetime] = None,
        search: Optional[str] = None,
    ) -> List[NotificationSignalGroup]:
        qs = NotificationSignalGroup.objects.all()
        if status:
            qs = qs.filter(status=status)
        if assigned_to:
            qs = qs.filter(assigned_to_user_id=assigned_to)
        if tenant_id:
            qs = qs.filter(agency_id=tenant_id)
        if job_name:
            qs = qs.filter(job_name=job_name)
        if severity is not None:
            qs = qs.filter(current_severity__lte=severity)
        if updated_since:
            qs = qs.filter(last_seen_at__gte=updated_since)
        if search:
            qs = qs.filter(
                Q(job_name__icontains=search)
                | Q(agency_slug__icontains=search)
                | Q(signal_type__icontains=search)
            )
        return list(qs.order_by("-last_seen_at"))

    def group_detail(self, group_id: str, recent_signal_count: int = 5) -> Dict[str, Any]:
        group = NotificationSignalGroup.objects.get(id=group_id)
        recent_signals = (
            NotificationSignal.objects.filter(fingerprint=group.fingerprint)
            .order_by("-occurred_at")[:recent_signal_count]
        )
        activities = group.activities.order_by("-created_at")[:20]
        return {
            "group": group,
            "recent_signals": list(recent_signals),
            "activities": list(activities),
        }

    def groups_requiring_reminder(self, as_of: Optional[datetime] = None) -> List[NotificationSignalGroup]:
        now = as_of or timezone.now()
        return [
            group
            for group in NotificationSignalGroup.objects.filter(status__in=[NotificationSignalGroup.Status.OPEN, NotificationSignalGroup.Status.ACKNOWLEDGED])
            if self._needs_reminder(group, now)
        ]

    def send_reminders(self, as_of: Optional[datetime] = None) -> List[NotificationSignalGroup]:
        now = as_of or timezone.now()
        reminded: List[NotificationSignalGroup] = []
        for group in self.groups_requiring_reminder(now):
            slack_user_id = self._slack_user_for_actor(group.assigned_to_user_id or "")
            if not slack_user_id:
                continue
            self.notifier.send_owner_reminder(group, slack_user_id)
            group.last_reminded_at = now
            group.last_daily_reminder_date = now.date()
            group.save(update_fields=["last_reminded_at", "last_daily_reminder_date"])
            self._log_activity(group, "dm_reminded", {"slack_user_id": slack_user_id})
            reminded.append(group)
        return reminded

    def send_daily_digest(self, digest_date: Optional[date] = None) -> List[NotificationSignalGroup]:
        today = digest_date or timezone.now().date()
        if NotificationSignalGroupActivity.objects.filter(action="digest_sent", created_at__date=today).exists():
            return []

        open_groups = list(
            NotificationSignalGroup.objects.filter(status__in=self._active_statuses()).order_by("current_severity", "-last_seen_at")
        )
        if not open_groups:
            return []

        self.notifier.post_digest(open_groups, today)
        for group in open_groups:
            self._log_activity(group, "digest_sent", {"date": str(today)})
        return open_groups

    def _needs_reminder(self, group: NotificationSignalGroup, as_of: datetime) -> bool:
        if group.snoozed_until and group.snoozed_until > as_of:
            return False
        if group.assigned_to_user_id is None:
            return False

        age = as_of - group.first_seen_at
        last = group.last_reminded_at
        daily_done = group.last_daily_reminder_date == as_of.date()

        # Severity-based thresholds
        if group.current_severity <= HIGH_SEVERITY_MAX:
            if last is None and age >= timedelta(hours=getattr(settings, "REMINDER_T2_HOURS", 2)):
                return True
            if age >= timedelta(hours=getattr(settings, "REMINDER_T8_HOURS", 8)):
                if last is None or (as_of - last) >= timedelta(hours=getattr(settings, "REMINDER_T8_HOURS", 8)):
                    return True
        elif group.current_severity == 2:
            if age >= timedelta(hours=getattr(settings, "REMINDER_T8_HOURS", 8)):
                if last is None or (as_of - last) >= timedelta(hours=getattr(settings, "REMINDER_T8_HOURS", 8)):
                    return True

        # Daily cadence (S0/S1/S2/S3)
        if not daily_done and age >= timedelta(hours=24):
            return True

        return False

    def _log_activity(self, group: NotificationSignalGroup, action: str, metadata: Dict[str, Any]) -> None:
        NotificationSignalGroupActivity.objects.create(
            signal_group=group,
            actor_type=NotificationSignalGroupActivity.ActorType.SYSTEM,
            actor_user_id=None,
            action=action,
            metadata_json=metadata,
        )

    @staticmethod
    def _active_statuses() -> List[str]:
        return [
            NotificationSignalGroup.Status.OPEN,
            NotificationSignalGroup.Status.ACKNOWLEDGED,
            NotificationSignalGroup.Status.SNOOZED,
        ]

    @staticmethod
    def _build_ui_url(group_id: str) -> str:
        base = getattr(settings, "APP_BASE_URL", "http://localhost:8000").rstrip("/")
        return f"{base}/notifications/{group_id}"

    @staticmethod
    def _count_24h(signal: NotificationSignal) -> int:
        window_start = signal.occurred_at - timedelta(hours=24)
        return NotificationSignal.objects.filter(fingerprint=signal.fingerprint, occurred_at__gte=window_start, agency_id=signal.agency_id).count()

    @staticmethod
    def _slack_user_for_actor(actor_user_id: str) -> Optional[str]:
        if not actor_user_id:
            return None
        mapping = NotificationUserSlackMap.objects.filter(user_id=actor_user_id).first()
        return mapping.slack_user_id if mapping else None
HIGH_SEVERITY_MAX = 1
