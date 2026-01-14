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

from observability.fingerprinting import compute_fingerprint, normalize_error_message
from observability.models import (
    JobOwnerOverride,
    OwnerResolution,
    Signal,
    SignalGroup,
    SignalGroupActivity,
    TenantOwner,
    UserSlackMap,
)


class SlackNotifier(Protocol):
    """Protocol describing Slack side-effects."""

    def post_group_opened(self, group: SignalGroup, signal: Signal) -> None:
        ...

    def update_group_acknowledged(self, group: SignalGroup, slack_user_id: Optional[str]) -> None:
        ...

    def send_owner_reminder(self, group: SignalGroup, slack_user_id: str) -> None:
        ...

    def post_digest(self, groups: List[SignalGroup], digest_date: date) -> None:
        ...


class NullSlackNotifier:
    """No-op Slack notifier used for tests or disabled environments."""

    def post_group_opened(self, group: SignalGroup, signal: Signal) -> None:  # noqa: D401
        return

    def update_group_acknowledged(self, group: SignalGroup, slack_user_id: Optional[str]) -> None:  # noqa: D401
        return

    def send_owner_reminder(self, group: SignalGroup, slack_user_id: str) -> None:  # noqa: D401
        return

    def post_digest(self, groups: List[SignalGroup], digest_date: date) -> None:  # noqa: D401
        return


@dataclass(frozen=True)
class SignalPayload:
    """Payload accepted by the ingestion service."""

    tenant_id: str
    tenant_code: str
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
        tenant_override = JobOwnerOverride.objects.filter(tenant_id=tenant_id, job_name=job_name).first()
        if tenant_override:
            return {
                "user_id": tenant_override.owner_user_id,
                "team_id": tenant_override.team_id,
            }

        global_override = JobOwnerOverride.objects.filter(tenant_id__isnull=True, job_name=job_name).first()
        if global_override:
            return {
                "user_id": global_override.owner_user_id,
                "team_id": global_override.team_id,
            }

        tenant_owner = TenantOwner.objects.filter(tenant_id=tenant_id).first()
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

    def ingest_signal(self, payload: SignalPayload) -> Tuple[Signal, SignalGroup]:
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
            signal = Signal.objects.create(
                occurred_at=occurred_at,
                source=payload.source,
                signal_type=payload.signal_type,
                severity=payload.severity,
                tenant_id=payload.tenant_id,
                tenant_code=payload.tenant_code,
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
        self, signal: Signal, payload: SignalPayload, normalized_message: str
    ) -> Tuple[SignalGroup, bool, bool]:
        now = timezone.now()
        reopen_window = timedelta(hours=getattr(settings, "REOPEN_WINDOW_HOURS", 24))
        active_group = (
            SignalGroup.objects.select_for_update()
            .filter(fingerprint=signal.fingerprint, status__in=self._active_statuses())
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
            SignalGroup.objects.select_for_update()
            .filter(fingerprint=signal.fingerprint)
            .order_by("-closed_at", "-last_seen_at")
            .first()
        )

        if latest_group and latest_group.status == SignalGroup.Status.CLOSED and latest_group.closed_at:
            if (now - latest_group.closed_at) <= reopen_window:
                latest_group.status = SignalGroup.Status.OPEN
                latest_group.closed_at = None
                self._update_group_from_signal(latest_group, signal, payload, normalized_message)
                latest_group.save()
                self._log_activity(latest_group, "reopened", {"severity": latest_group.current_severity})
                return latest_group, created, False

        owner = self.owner_router.resolve(payload.tenant_id, payload.job_name)
        group_id = uuid.uuid4()
        group = SignalGroup.objects.create(
            id=group_id,
            fingerprint=signal.fingerprint,
            status=SignalGroup.Status.OPEN,
            current_severity=signal.severity,
            tenant_id=payload.tenant_id,
            tenant_code=payload.tenant_code,
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
        self, group: SignalGroup, signal: Signal, payload: SignalPayload, normalized_message: str
    ) -> None:
        group.update_counts(signal.occurred_at)
        group.current_severity = min(group.current_severity, signal.severity)
        group.last_signal = signal
        group.tenant_code = payload.tenant_code
        group.job_name = payload.job_name
        group.signal_type = payload.signal_type
        group.count_24h = self._count_24h(signal)

    def acknowledge_group(self, group_id: str, actor_user_id: str) -> SignalGroup:
        now = timezone.now()
        updated = False
        with transaction.atomic():
            group = SignalGroup.objects.select_for_update().get(id=group_id)
            if group.status == SignalGroup.Status.OPEN:
                group.status = SignalGroup.Status.ACKNOWLEDGED
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

    def assign_group(self, group_id: str, user_id: Optional[str], team_id: Optional[str]) -> SignalGroup:
        with transaction.atomic():
            group = SignalGroup.objects.select_for_update().get(id=group_id)
            group.assigned_to_user_id = user_id
            group.assigned_team_id = team_id
            group.save()
            self._log_activity(group, "assigned", {"user_id": user_id, "team_id": team_id})
        return group

    def snooze_group(self, group_id: str, until: datetime, actor_user_id: Optional[str]) -> SignalGroup:
        with transaction.atomic():
            group = SignalGroup.objects.select_for_update().get(id=group_id)
            group.status = SignalGroup.Status.SNOOZED
            group.snoozed_until = until
            group.save()
            self._log_activity(group, "snoozed", {"until": until.isoformat(), "actor_user_id": actor_user_id})
        return group

    def close_group(self, group_id: str, actor_user_id: Optional[str]) -> SignalGroup:
        with transaction.atomic():
            group = SignalGroup.objects.select_for_update().get(id=group_id)
            group.status = SignalGroup.Status.CLOSED
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
    ) -> List[SignalGroup]:
        qs = SignalGroup.objects.all()
        if status:
            qs = qs.filter(status=status)
        if assigned_to:
            qs = qs.filter(assigned_to_user_id=assigned_to)
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        if job_name:
            qs = qs.filter(job_name=job_name)
        if severity is not None:
            qs = qs.filter(current_severity__lte=severity)
        if updated_since:
            qs = qs.filter(last_seen_at__gte=updated_since)
        if search:
            qs = qs.filter(
                Q(job_name__icontains=search)
                | Q(tenant_code__icontains=search)
                | Q(signal_type__icontains=search)
            )
        return list(qs.order_by("-last_seen_at"))

    def group_detail(self, group_id: str, recent_signal_count: int = 5) -> Dict[str, Any]:
        group = SignalGroup.objects.get(id=group_id)
        recent_signals = (
            Signal.objects.filter(fingerprint=group.fingerprint)
            .order_by("-occurred_at")[:recent_signal_count]
        )
        activities = group.activities.order_by("-created_at")[:20]
        return {
            "group": group,
            "recent_signals": list(recent_signals),
            "activities": list(activities),
        }

    def groups_requiring_reminder(self, as_of: Optional[datetime] = None) -> List[SignalGroup]:
        now = as_of or timezone.now()
        return [
            group
            for group in SignalGroup.objects.filter(status__in=[SignalGroup.Status.OPEN, SignalGroup.Status.ACKNOWLEDGED])
            if self._needs_reminder(group, now)
        ]

    def send_reminders(self, as_of: Optional[datetime] = None) -> List[SignalGroup]:
        now = as_of or timezone.now()
        reminded: List[SignalGroup] = []
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

    def send_daily_digest(self, digest_date: Optional[date] = None) -> List[SignalGroup]:
        today = digest_date or timezone.now().date()
        if SignalGroupActivity.objects.filter(action="digest_sent", created_at__date=today).exists():
            return []

        open_groups = list(
            SignalGroup.objects.filter(status__in=self._active_statuses()).order_by("current_severity", "-last_seen_at")
        )
        if not open_groups:
            return []

        self.notifier.post_digest(open_groups, today)
        for group in open_groups:
            self._log_activity(group, "digest_sent", {"date": str(today)})
        return open_groups

    def _needs_reminder(self, group: SignalGroup, as_of: datetime) -> bool:
        if group.snoozed_until and group.snoozed_until > as_of:
            return False
        if group.assigned_to_user_id is None:
            return False
        if group.last_daily_reminder_date == as_of.date():
            return False
        # Lower integers represent higher severity (S0/S1). Remind those faster.
        threshold_hours = (
            getattr(settings, "REMINDER_T2_HOURS", 2) if group.current_severity <= HIGH_SEVERITY_MAX else getattr(settings, "REMINDER_T8_HOURS", 8)
        )
        if group.last_reminded_at and (as_of - group.last_reminded_at) < timedelta(hours=threshold_hours):
            return False
        return True

    def _log_activity(self, group: SignalGroup, action: str, metadata: Dict[str, Any]) -> None:
        SignalGroupActivity.objects.create(
            signal_group=group,
            actor_type=SignalGroupActivity.ActorType.SYSTEM,
            actor_user_id=None,
            action=action,
            metadata_json=metadata,
        )

    @staticmethod
    def _active_statuses() -> List[str]:
        return [SignalGroup.Status.OPEN, SignalGroup.Status.ACKNOWLEDGED, SignalGroup.Status.SNOOZED]

    @staticmethod
    def _build_ui_url(group_id: str) -> str:
        base = getattr(settings, "APP_BASE_URL", "http://localhost:8000").rstrip("/")
        return f"{base}/notifications/{group_id}"

    @staticmethod
    def _count_24h(signal: Signal) -> int:
        window_start = signal.occurred_at - timedelta(hours=24)
        return Signal.objects.filter(fingerprint=signal.fingerprint, occurred_at__gte=window_start).count()

    @staticmethod
    def _slack_user_for_actor(actor_user_id: str) -> Optional[str]:
        if not actor_user_id:
            return None
        mapping = UserSlackMap.objects.filter(user_id=actor_user_id).first()
        return mapping.slack_user_id if mapping else None
HIGH_SEVERITY_MAX = 1
