"""Initial migration for observability notification models."""
from __future__ import annotations

import uuid

from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Signal",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("occurred_at", models.DateTimeField(default=timezone.now)),
                ("source", models.CharField(max_length=64)),
                ("signal_type", models.CharField(max_length=128)),
                ("severity", models.PositiveSmallIntegerField()),
                ("tenant_id", models.CharField(max_length=64)),
                ("tenant_code", models.CharField(max_length=64)),
                ("job_name", models.CharField(max_length=255)),
                ("run_id", models.CharField(max_length=128, null=True, blank=True)),
                ("task_id", models.CharField(max_length=128, null=True, blank=True)),
                ("stage", models.CharField(max_length=128, null=True, blank=True)),
                ("error_class", models.CharField(max_length=255, null=True, blank=True)),
                ("error_message", models.TextField(null=True, blank=True)),
                ("fingerprint", models.CharField(max_length=128, db_index=True)),
                ("summary", models.CharField(max_length=255)),
                ("details_json", models.JSONField(default=dict)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["fingerprint", "-occurred_at"], name="idx_signal_fp_occ"),
                    models.Index(fields=["tenant_id", "-occurred_at"], name="idx_signal_tenant_occ"),
                    models.Index(fields=["job_name", "-occurred_at"], name="idx_signal_job_occ"),
                ]
            },
        ),
        migrations.CreateModel(
            name="SignalGroup",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("fingerprint", models.CharField(max_length=128, db_index=True)),
                ("status", models.CharField(max_length=16)),
                ("current_severity", models.PositiveSmallIntegerField()),
                ("tenant_id", models.CharField(max_length=64)),
                ("tenant_code", models.CharField(max_length=64)),
                ("job_name", models.CharField(max_length=255)),
                ("signal_type", models.CharField(max_length=128)),
                ("first_seen_at", models.DateTimeField()),
                ("last_seen_at", models.DateTimeField()),
                ("count_total", models.PositiveIntegerField(default=0)),
                ("count_24h", models.PositiveIntegerField(default=0)),
                ("assigned_to_user_id", models.CharField(max_length=64, null=True, blank=True)),
                ("assigned_team_id", models.CharField(max_length=64, null=True, blank=True)),
                ("acknowledged_at", models.DateTimeField(null=True, blank=True)),
                ("acknowledged_by_user_id", models.CharField(max_length=64, null=True, blank=True)),
                ("snoozed_until", models.DateTimeField(null=True, blank=True)),
                ("opened_notified_at", models.DateTimeField(null=True, blank=True)),
                ("last_reminded_at", models.DateTimeField(null=True, blank=True)),
                ("last_daily_reminder_date", models.DateField(null=True, blank=True)),
                ("last_escalated_at", models.DateTimeField(null=True, blank=True)),
                ("slack_channel_id", models.CharField(max_length=128, null=True, blank=True)),
                ("slack_root_ts", models.CharField(max_length=128, null=True, blank=True)),
                ("ui_url", models.CharField(max_length=512)),
                ("closed_at", models.DateTimeField(null=True, blank=True)),
                (
                    "last_signal",
                    models.ForeignKey(
                        blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="groups", to="observability.signal"
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["status", "current_severity", "-last_seen_at"], name="idx_group_status_sev_seen"
                    ),
                    models.Index(
                        fields=["assigned_to_user_id", "status", "-last_seen_at"],
                        name="idx_group_assignee_status_seen",
                    ),
                    models.Index(fields=["tenant_id", "status", "-last_seen_at"], name="idx_group_tenant_status_seen"),
                    models.Index(fields=["fingerprint", "status"], name="idx_group_fingerprint_status"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=["fingerprint"],
                        condition=models.Q(status__in=["open", "acknowledged", "snoozed"]),
                        name="uniq_active_group_per_fingerprint",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="JobOwnerOverride",
            fields=[
                ("id", models.BigAutoField(primary_key=True, auto_created=True, serialize=False, verbose_name="ID")),
                ("tenant_id", models.CharField(max_length=64, null=True, blank=True)),
                ("job_name", models.CharField(max_length=255)),
                ("owner_user_id", models.CharField(max_length=64, null=True, blank=True)),
                ("team_id", models.CharField(max_length=64, null=True, blank=True)),
            ],
            options={"unique_together": {("tenant_id", "job_name")}},
        ),
        migrations.CreateModel(
            name="TenantOwner",
            fields=[
                ("id", models.BigAutoField(primary_key=True, auto_created=True, serialize=False, verbose_name="ID")),
                ("tenant_id", models.CharField(max_length=64, unique=True)),
                ("primary_owner_user_id", models.CharField(max_length=64)),
                ("secondary_owner_user_id", models.CharField(max_length=64, null=True, blank=True)),
                ("owning_team_id", models.CharField(max_length=64, null=True, blank=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="UserSlackMap",
            fields=[
                ("id", models.BigAutoField(primary_key=True, auto_created=True, serialize=False, verbose_name="ID")),
                ("user_id", models.CharField(max_length=64, unique=True)),
                ("slack_user_id", models.CharField(max_length=64, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="SignalGroupActivity",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor_type", models.CharField(max_length=16)),
                ("actor_user_id", models.CharField(max_length=64, null=True, blank=True)),
                ("action", models.CharField(max_length=64)),
                ("metadata_json", models.JSONField(default=dict)),
                (
                    "signal_group",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE, related_name="activities", to="observability.signalgroup"
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["signal_group", "-created_at"], name="idx_activity_group_created_at")
                ]
            },
        ),
    ]
