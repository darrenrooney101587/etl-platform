"""Django ORM models for reporting seeder release snapshots."""
from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


class SeederReleaseSnapshot(models.Model):
    """Immutable release snapshot for a reporting materialized view."""

    class Status(models.TextChoices):
        """Enumerated status values for release snapshot execution."""

        SUCCESS = "success", "success"
        ERROR = "error", "error"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    manifest_id = models.BigIntegerField()
    table_name = models.CharField(max_length=255)
    report_name = models.CharField(max_length=255, null=True, blank=True)
    agency_id = models.BigIntegerField(null=True, blank=True)
    agency_slug = models.CharField(max_length=64, null=True, blank=True)
    release_tag = models.CharField(max_length=128)
    release_version = models.CharField(max_length=128, null=True, blank=True)
    released_at = models.DateTimeField(default=timezone.now)
    executed_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=16, choices=Status.choices)
    execution_duration_ms = models.PositiveIntegerField(default=0)
    total_rows = models.BigIntegerField(default=0)
    total_columns = models.PositiveIntegerField(default=0)
    schema_hash = models.CharField(max_length=128)
    columns = models.JSONField(default=list)
    column_stats = models.JSONField(default=list)

    class Meta:
        db_table = "reporting.seeder_release_snapshot"
        managed = True
        indexes = [
            models.Index(fields=["manifest_id", "-released_at"], name="idx_snap_manifest_release"),
            models.Index(fields=["table_name", "-released_at"], name="idx_snap_table_release"),
        ]
