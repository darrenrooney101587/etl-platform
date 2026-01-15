"""Model proxies aligned to existing reporting notification tables.

These models mirror the upstream `reporting` schema and are kept `managed=True`
so local tests can create tables via `migrate --run-syncdb`. In production the
authoritative schema lives in the shared etl_database_schema package.
"""
from __future__ import annotations

import uuid
from typing import Dict, Optional

from django.db import models
from django.utils import timezone


class NotificationSignal(models.Model):
    """Append-only notification signals."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    source = models.CharField(max_length=64)
    signal_type = models.CharField(max_length=128)
    severity = models.PositiveSmallIntegerField()
    agency_id = models.CharField(max_length=64)
    agency_slug = models.CharField(max_length=64)
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
        db_table = "notification_signal"
        managed = True
        indexes = [
            models.Index(fields=["fingerprint", "-occurred_at"], name="idx_signal_fp_occ"),
            models.Index(fields=["agency_id", "-occurred_at"], name="idx_signal_agency_occ"),
            models.Index(fields=["job_name", "-occurred_at"], name="idx_signal_job_occ"),
        ]


class NotificationSignalGroup(models.Model):
    """Stateful rollup keyed by fingerprint and agency."""

    class Status(models.TextChoices):
        OPEN = "open", "open"
        ACKNOWLEDGED = "acknowledged", "acknowledged"
        SNOOZED = "snoozed", "snoozed"
        CLOSED = "closed", "closed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fingerprint = models.CharField(max_length=128, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices)
    current_severity = models.PositiveSmallIntegerField()
    agency_id = models.CharField(max_length=64)
    agency_slug = models.CharField(max_length=64)
    job_name = models.CharField(max_length=255)
    signal_type = models.CharField(max_length=128)
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    count_total = models.PositiveIntegerField(default=0)
    count_24h = models.PositiveIntegerField(default=0)
    last_signal = models.ForeignKey(
        NotificationSignal, on_delete=models.SET_NULL, null=True, blank=True, related_name="groups"
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
    last_slack_updated_at = models.DateTimeField(null=True, blank=True)
    slack_message_hash = models.CharField(max_length=64, null=True, blank=True)
    slack_channel_id = models.CharField(max_length=128, null=True, blank=True)
    slack_root_ts = models.CharField(max_length=128, null=True, blank=True)
    ui_url = models.CharField(max_length=512, null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notification_signal_group"
        managed = True
        indexes = [
            models.Index(
                fields=["status", "current_severity", "-last_seen_at"], name="idx_group_status_sev_seen"
            ),
            models.Index(
                fields=["assigned_to_user_id", "status", "-last_seen_at"],
                name="idx_group_assignee_status_seen",
            ),
            models.Index(fields=["agency_id", "status", "-last_seen_at"], name="idx_group_agency_status_seen"),
            models.Index(fields=["fingerprint", "status"], name="idx_group_fingerprint_status"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["agency_id", "fingerprint"],
                condition=models.Q(status__in=["open", "acknowledged", "snoozed"]),
                name="uniq_active_group_per_agency_fingerprint",
            )
        ]

    def update_counts(self, occurrence_time) -> None:
        self.last_seen_at = max(self.last_seen_at, occurrence_time)
        self.count_total = self.count_total + 1


class NotificationSignalGroupActivity(models.Model):
    """Audit trail of state changes and system actions."""

    class ActorType(models.TextChoices):
        SYSTEM = "system", "system"
        USER = "user", "user"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    signal_group = models.ForeignKey(NotificationSignalGroup, on_delete=models.CASCADE, related_name="activities")
    created_at = models.DateTimeField(auto_now_add=True)
    actor_type = models.CharField(max_length=16, choices=ActorType.choices)
    actor_user_id = models.CharField(max_length=64, null=True, blank=True)
    action = models.CharField(max_length=64)
    metadata_json = models.JSONField(default=dict)

    class Meta:
        db_table = "notification_signal_group_activity"
        managed = True
        indexes = [
            models.Index(
                fields=["signal_group", "-created_at"], name="idx_activity_group_created_at"
            )
        ]


class NotificationAgencyOwner(models.Model):
    """Primary ownership mapping per agency."""

    id = models.BigAutoField(primary_key=True)
    agency_id = models.CharField(max_length=64, unique=True)
    primary_owner_user_id = models.CharField(max_length=64)
    secondary_owner_user_id = models.CharField(max_length=64, null=True, blank=True)
    owning_team_id = models.CharField(max_length=64, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notification_agency_owner"
        managed = True


class NotificationJobOwnerOverride(models.Model):
    """Per-job ownership override."""

    id = models.BigAutoField(primary_key=True)
    agency_id = models.CharField(max_length=64, null=True, blank=True)
    job_name = models.CharField(max_length=255)
    owner_user_id = models.CharField(max_length=64, null=True, blank=True)
    team_id = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        db_table = "notification_job_owner_override"
        managed = True
        unique_together = ("agency_id", "job_name")


class NotificationUserSlackMap(models.Model):
    """Mapping between internal user ids and Slack user ids."""

    id = models.BigAutoField(primary_key=True)
    user_id = models.CharField(max_length=64, unique=True)
    slack_user_id = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notification_user_slack_map"
        managed = True


OwnerResolution = Dict[str, Optional[str]]
