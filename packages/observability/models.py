"""Django models for the signal notification system."""
from __future__ import annotations

import uuid
from typing import Dict, Optional

from django.db import models
from django.utils import timezone


class Signal(models.Model):
    """Append-only record of each signal occurrence."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    source = models.CharField(max_length=64)
    signal_type = models.CharField(max_length=128)
    severity = models.PositiveSmallIntegerField()
    tenant_id = models.CharField(max_length=64)
    tenant_code = models.CharField(max_length=64)
    job_name = models.CharField(max_length=255)
    run_id = models.CharField(max_length=128, null=True, blank=True)
    task_id = models.CharField(max_length=128, null=True, blank=True)
    stage = models.CharField(max_length=128, null=True, blank=True)
    error_class = models.CharField(max_length=255, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    fingerprint = models.CharField(max_length=128, db_index=True)
    summary = models.CharField(max_length=255)
    details_json = models.JSONField(default=dict)

    class Meta:
        indexes = [
            models.Index(fields=["fingerprint", "-occurred_at"], name="idx_signal_fp_occ"),
            models.Index(fields=["tenant_id", "-occurred_at"], name="idx_signal_tenant_occ"),
            models.Index(fields=["job_name", "-occurred_at"], name="idx_signal_job_occ"),
        ]


class SignalGroup(models.Model):
    """Stateful rollup of signals keyed by fingerprint."""

    class Status(models.TextChoices):
        OPEN = "open", "open"
        ACKNOWLEDGED = "acknowledged", "acknowledged"
        SNOOZED = "snoozed", "snoozed"
        CLOSED = "closed", "closed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fingerprint = models.CharField(max_length=128, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices)
    current_severity = models.PositiveSmallIntegerField()
    tenant_id = models.CharField(max_length=64)
    tenant_code = models.CharField(max_length=64)
    job_name = models.CharField(max_length=255)
    signal_type = models.CharField(max_length=128)
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    count_total = models.PositiveIntegerField(default=0)
    count_24h = models.PositiveIntegerField(default=0)
    last_signal = models.ForeignKey(
        Signal, on_delete=models.SET_NULL, null=True, blank=True, related_name="groups"
    )
    assigned_to_user_id = models.CharField(max_length=64, null=True, blank=True)
    assigned_team_id = models.CharField(max_length=64, null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by_user_id = models.CharField(max_length=64, null=True, blank=True)
    snoozed_until = models.DateTimeField(null=True, blank=True)
    opened_notified_at = models.DateTimeField(null=True, blank=True)
    last_reminded_at = models.DateTimeField(null=True, blank=True)
    last_daily_reminder_date = models.DateField(null=True, blank=True)
    last_escalated_at = models.DateTimeField(null=True, blank=True)
    slack_channel_id = models.CharField(max_length=128, null=True, blank=True)
    slack_root_ts = models.CharField(max_length=128, null=True, blank=True)
    ui_url = models.CharField(max_length=512)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["status", "current_severity", "-last_seen_at"], name="idx_group_status_sev_seen"
            ),
            models.Index(
                fields=["assigned_to_user_id", "status", "-last_seen_at"],
                name="idx_group_assignee_status_seen",
            ),
            models.Index(fields=["tenant_id", "status", "-last_seen_at"], name="idx_group_tenant_status_seen"),
            models.Index(fields=["fingerprint", "status"], name="idx_group_fingerprint_status"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["fingerprint"],
                condition=models.Q(status__in=["open", "acknowledged", "snoozed"]),
                name="uniq_active_group_per_fingerprint",
            )
        ]

    def update_counts(self, occurrence_time) -> None:
        """Update counters and timestamps using the provided occurrence time."""
        self.last_seen_at = max(self.last_seen_at, occurrence_time)
        self.count_total = self.count_total + 1


class SignalGroupActivity(models.Model):
    """Audit trail of state changes and system actions."""

    class ActorType(models.TextChoices):
        SYSTEM = "system", "system"
        USER = "user", "user"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    signal_group = models.ForeignKey(SignalGroup, on_delete=models.CASCADE, related_name="activities")
    created_at = models.DateTimeField(auto_now_add=True)
    actor_type = models.CharField(max_length=16, choices=ActorType.choices)
    actor_user_id = models.CharField(max_length=64, null=True, blank=True)
    action = models.CharField(max_length=64)
    metadata_json = models.JSONField(default=dict)

    class Meta:
        indexes = [
            models.Index(
                fields=["signal_group", "-created_at"], name="idx_activity_group_created_at"
            )
        ]


class TenantOwner(models.Model):
    """Primary ownership mapping per tenant."""

    tenant_id = models.CharField(max_length=64, unique=True)
    primary_owner_user_id = models.CharField(max_length=64)
    secondary_owner_user_id = models.CharField(max_length=64, null=True, blank=True)
    owning_team_id = models.CharField(max_length=64, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class JobOwnerOverride(models.Model):
    """Per-job ownership override."""

    tenant_id = models.CharField(max_length=64, null=True, blank=True)
    job_name = models.CharField(max_length=255)
    owner_user_id = models.CharField(max_length=64, null=True, blank=True)
    team_id = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        unique_together = ("tenant_id", "job_name")


class UserSlackMap(models.Model):
    """Mapping between internal user ids and Slack user ids."""

    user_id = models.CharField(max_length=64, unique=True)
    slack_user_id = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)


OwnerResolution = Dict[str, Optional[str]]
