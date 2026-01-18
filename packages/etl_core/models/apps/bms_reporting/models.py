import uuid
from django.utils import timezone

from django.conf import settings
from django.db import models

from etl_core.models.apps.bms.models import Agency


# -----------------------------
# Monitoring schema models
# -----------------------------
class MonitoringFileSchemaDefinition(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255, blank=False, unique=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        managed = True
        db_table = '"reporting"."monitoring_file_schema_definition"'
        verbose_name = "Monitoring File Schema Definition"
        verbose_name_plural = "Monitoring File Schema Definitions"


class MonitoringFileSchemaDefinitionVersion(models.Model):
    """
    Versioned snapshot of a schema definition. Each change to the JSON schema
    creates a new version linked back to the parent MonitoringFileSchemaDefinition.
    """

    id = models.AutoField(primary_key=True)
    schema_definition = models.ForeignKey(
        MonitoringFileSchemaDefinition,
        on_delete=models.PROTECT,
        related_name='versions',
        db_column='schema_definition_id',
    )
    version = models.PositiveIntegerField()
    definition = models.JSONField(
        default=dict, help_text="Versioned JSON schema definition"
    )
    status = models.CharField(
        max_length=32,
        default='active',
        help_text="Status of this version (e.g., active, draft, deprecated)",
    )
    created_by = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text='User or system that created this version',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = '"reporting"."monitoring_file_schema_definition_version"'
        verbose_name = "Monitoring File Schema Version"
        verbose_name_plural = "Monitoring File Schema Versions"
        unique_together = ('schema_definition', 'version')
        ordering = ['schema_definition_id', '-version']


class MonitoringFileSchemaAssignmentHistory(models.Model):
    """Audit history for schema assignment changes on a MonitoringFile.

    This tracks changes to the *mapping* between a monitoring file and a schema
    definition/version. It does not track edits to the schema definition JSON
    itself (those are handled by MonitoringFileSchemaDefinitionVersion).
    """

    id = models.AutoField(primary_key=True)
    monitoring_file = models.ForeignKey(
        "MonitoringFile",
        db_column="monitoring_file_id",
        on_delete=models.CASCADE,
        related_name="schema_assignment_history",
    )

    previous_schema_definition = models.ForeignKey(
        MonitoringFileSchemaDefinition,
        db_column="previous_schema_definition_id",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    previous_schema_definition_version = models.ForeignKey(
        "MonitoringFileSchemaDefinitionVersion",
        db_column="previous_schema_definition_version_id",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    new_schema_definition = models.ForeignKey(
        MonitoringFileSchemaDefinition,
        db_column="new_schema_definition_id",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    new_schema_definition_version = models.ForeignKey(
        "MonitoringFileSchemaDefinitionVersion",
        db_column="new_schema_definition_version_id",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    changed_by = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Username that changed the mapping",
    )
    change_reason = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True
        db_table = '"reporting"."monitoring_file_schema_assignment_history"'
        verbose_name = "Monitoring File Schema Assignment History"
        verbose_name_plural = "Monitoring File Schema Assignment Histories"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["monitoring_file"],
                name="idx_mf_schema_assign_hist_file",
            ),
        ]


# -----------------------------
# Monitoring file models
# -----------------------------
class MonitoringFile(models.Model):
    id = models.AutoField(primary_key=True)
    s3_url = models.CharField(max_length=250, blank=True, help_text="")
    file_name = models.CharField(max_length=250, blank=False)
    range = models.CharField(
        max_length=20,
        blank=False,
        help_text="Range format: < interval >.< time interval >.  I.e. 1.d = 1 Day.  Acceptable time intervals (s, m, d, w, mth)",
    )
    is_active = models.BooleanField(default=False, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(null=True, blank=True, editable=False)
    agency = models.ForeignKey(
        Agency,
        models.PROTECT,
        unique=False,
        blank=False,
        null=True,
        help_text='The Agency in the core BMS App',
        related_name='clover_run_versions_agency_id',
    )
    agency_slug = models.CharField(max_length=255, null=False)
    has_wildcard = models.BooleanField(null=True, default=False, blank=True)
    wildcard_mask = models.CharField(max_length=100, blank=True)
    notify_slack = models.BooleanField(default=False, blank=False)
    is_missing = models.BooleanField(default=False, blank=False)
    is_file_change_excluded = models.BooleanField(default=False, blank=False)
    created_by = models.CharField(blank=True, max_length=512)
    is_suppressed = models.BooleanField(default=False)
    secret = models.CharField(
        max_length=400,
        blank=True,
        null=True,
        help_text='Password for the zip file, is applicable',
    )
    latest_data_quality_score = models.IntegerField(
        null=True, blank=True, help_text="Cached latest data quality score (0-100)"
    )
    schema_definition = models.ForeignKey(
        'MonitoringFileSchemaDefinition',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="The schema definition used for validation",
        related_name='monitoring_files',
    )
    schema_definition_version = models.ForeignKey(
        'MonitoringFileSchemaDefinitionVersion',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Specific version of the schema definition used for validation",
        related_name='monitoring_files',
    )

    def __str__(self):
        return self.file_name

    @property
    def agency_s3_slug(self):
        return self.agency_slug

    class Meta:
        managed = True
        db_table = '"reporting"."monitoring_file"'
        verbose_name = "Monitoring Files"
        verbose_name_plural = "Monitoring Files"


class MonitoringFileRun(models.Model):
    id = models.AutoField(primary_key=True)
    agency = models.ForeignKey(
        Agency,
        models.PROTECT,
        unique=False,
        blank=True,
        null=True,
        db_column='agency_id',
        help_text='The Agency in the core BMS App',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(null=True, blank=True, editable=False)
    file_last_modified = models.DateTimeField(blank=True, null=True)
    file_range_lower_limit = models.DateTimeField(blank=True, null=True)
    file_size = models.BigIntegerField(blank=True)
    monitoring_file = models.ForeignKey(
        MonitoringFile,
        null=False,
        db_column='monitoring_file_id',
        on_delete=models.CASCADE,
        related_name='monitoring_file_runs',
    )
    run_date = models.DateField(blank=True)
    run_hour = models.IntegerField(blank=False)

    def monitor_file_name(self):
        return self.monitoring_file.file_name

    def agency_slug(self):
        return self.agency.identifier

    def file_name(self):
        return self.monitoring_file.file_name

    def get_fields(self):
        return [
            (field.name, field.value_to_string(self))
            for field in MonitoringFileRun._meta.fields
        ]

    class Meta:
        managed = True
        db_table = '"reporting"."monitoring_file_run"'
        verbose_name = 'Monitoring File Runs'
        verbose_name_plural = 'Monitoring File Runs'
        constraints = [
            models.UniqueConstraint(
                fields=['monitoring_file', 'run_date', 'run_hour'],
                name='uk_monitoring_file_run_monitoring_file_run_date_run_hour',
            )
        ]


class MonitoringFileDataProfile(models.Model):
    """
    Stores data profiling metrics for a specific file run.
    """

    id = models.AutoField(primary_key=True)
    monitoring_file = models.ForeignKey(
        MonitoringFile,
        db_column='monitoring_file_id',
        on_delete=models.CASCADE,
        related_name='data_profiles',
        null=True,
        blank=True,
    )
    monitoring_file_run = models.OneToOneField(
        MonitoringFileRun,
        on_delete=models.CASCADE,
        related_name='data_profile',
        db_column='monitoring_file_run_id',
    )

    statistical_summary = models.JSONField(default=list)
    completeness_overview = models.JSONField(default=list)
    type_format_issues = models.JSONField(default=list)
    uniqueness_overview = models.JSONField(default=list)
    value_distributions = models.JSONField(default=list)
    bounds_anomalies = models.JSONField(default=list)
    sample_data = models.JSONField(default=dict, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = '"reporting"."monitoring_file_data_profile"'
        verbose_name = "Monitoring File Data Profile"
        verbose_name_plural = "Monitoring File Data Profiles"
        indexes = [
            models.Index(fields=["monitoring_file"], name="idx_mfdp_monitor_file"),
        ]


class MonitoringFileDataQuality(models.Model):
    """
    Stores detailed data quality metrics for a specific file run.
    """

    id = models.AutoField(primary_key=True)
    monitoring_file = models.ForeignKey(
        MonitoringFile,
        db_column='monitoring_file_id',
        on_delete=models.CASCADE,
        related_name='data_qualities',
        null=True,
        blank=True,
    )
    monitoring_file_run = models.OneToOneField(
        MonitoringFileRun,
        on_delete=models.CASCADE,
        related_name='data_quality',
        db_column='monitoring_file_run_id',
    )
    score = models.IntegerField(help_text="Overall quality score (0-100)")
    passed = models.BooleanField(default=False, help_text="Did the run pass quality thresholds?")

    metrics = models.JSONField(default=dict, help_text="Detailed breakdown of quality metrics")
    deductions = models.JSONField(default=dict, help_text="Points deducted per category")

    failed_validation_message = models.TextField(null=True, blank=True)
    failed_validation_rules = models.JSONField(null=True, blank=True, help_text="List of specific rules that failed")

    acknowledgment_status = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        choices=[
            ('operational', 'Operational'),
            ('non-operational', 'Non-Operational'),
            ('under-review', 'Under Review'),
        ],
        help_text="Status of the acknowledgment",
    )
    acknowledged_by_id = models.IntegerField(null=True, blank=True, help_text="ID of the user who acknowledged")
    acknowledged_by_username = models.CharField(max_length=255, null=True, blank=True, help_text="Username/Name of the user who acknowledged")
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledgment_notes = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = '"reporting"."monitoring_file_data_quality"'
        verbose_name = "Monitoring File Data Quality"
        verbose_name_plural = "Monitoring File Data Quality"
        indexes = [
            models.Index(fields=["monitoring_file"], name="idx_mfdq_monitor_file"),
        ]


# -----------------------------
# Navigation models
# -----------------------------
class NavigationGroup(models.Model):
    name = models.CharField(max_length=64, help_text="Display name of the group (e.g. Monitoring)")
    order = models.IntegerField(default=0, help_text="Sort order of the group")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        ordering = ['order', 'name']
        db_table = '"reporting"."website_react_navigation_group"'
        verbose_name = "Navigation Group"
        verbose_name_plural = "Navigation Groups"
        app_label = 'backend_react'

    def __str__(self):
        return self.name


class NavigationItem(models.Model):
    BADGE_TYPE_CHOICES = (
        ('none', 'No Badge'),
        ('static', 'Static Text'),
        ('dynamic', 'Dynamic Count'),
    )

    BADGE_COLOR_CHOICES = (
        ('default', 'Default (Blue/Info)'),
        ('success', 'Success (Green)'),
        ('warning', 'Warning (Yellow)'),
        ('danger', 'Danger (Red)'),
    )

    group = models.ForeignKey(NavigationGroup, on_delete=models.CASCADE, related_name='items')
    title = models.CharField(max_length=64, help_text="Display title")
    url = models.CharField(max_length=255, help_text="Frontend URL path (e.g. /file-monitoring)")
    icon_name = models.CharField(max_length=64, help_text="Lucide icon name (e.g. Activity, FolderOpen)")
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    badge_type = models.CharField(max_length=16, choices=BADGE_TYPE_CHOICES, default='none')
    badge_value = models.CharField(max_length=32, blank=True, null=True, help_text="Static text (e.g. NEW) or Dynamic Key (e.g. missing_files_count)")
    badge_color = models.CharField(max_length=16, choices=BADGE_COLOR_CHOICES, default='default')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = '"reporting"."website_react_navigation_item"'
        ordering = ['group__order', 'order', 'title']
        verbose_name = "Navigation Item"
        verbose_name_plural = "Navigation Items"
        app_label = 'backend_react'

    def __str__(self):
        return f"{self.group.name} - {self.title}"


# -----------------------------
# Seeder models
# -----------------------------
class SeederCannedReport(models.Model):
    id = models.AutoField(primary_key=True)
    table_name = models.TextField()
    report_name = models.TextField()
    query = models.TextField()
    database_id = models.IntegerField(null=True, blank=True)

    class Meta:
        managed = True
        db_table = '"reporting"."seeder_canned_report"'
        verbose_name = 'Seeder Canned Report'
        verbose_name_plural = 'Seeder Canned Reports'

    def __str__(self):
        return self.report_name


class SeederCannedReportManifest(models.Model):
    id = models.AutoField(primary_key=True)
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, db_column='agency_id', related_name='seeder_canned_report_manifests')
    agency_slug = models.CharField(max_length=255)
    canned_report = models.ForeignKey(SeederCannedReport, on_delete=models.CASCADE, db_column='canned_report_id', related_name='manifests')

    class Meta:
        managed = True
        db_table = '"reporting"."seeder_canned_report_manifest"'
        verbose_name = 'Seeder Canned Report Manifest'
        verbose_name_plural = 'Seeder Canned Report Manifests'

    def __str__(self):
        return f"{self.canned_report} for {self.agency_slug}"


class SeederCustomReportManifest(models.Model):
    id = models.AutoField(primary_key=True)
    table_name = models.TextField()
    report_name = models.TextField()
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, db_column='agency_id', related_name='seeder_custom_report_manifests')
    agency_slug = models.CharField(max_length=255)
    query = models.TextField()
    database_id = models.IntegerField(null=True, blank=True)
    enabled = models.BooleanField(default=True)

    class Meta:
        managed = True
        db_table = '"reporting"."seeder_custom_report_manifest"'
        verbose_name = 'Seeder Custom Report Manifest'
        verbose_name_plural = 'Seeder Custom Report Manifests'

    def __str__(self):
        return f"{self.report_name} ({self.agency_slug})"


class SeederJobStatus(models.Model):
    table_name = models.TextField(primary_key=True)
    manifest = models.ForeignKey(SeederCustomReportManifest, on_delete=models.CASCADE, db_column='manifest_id', related_name='job_statuses')
    report_name = models.TextField(null=True, blank=True)
    report_type = models.CharField(max_length=64, null=True, blank=True)
    agency = models.ForeignKey(Agency, on_delete=models.SET_NULL, null=True, blank=True, db_column='agency_id', related_name='+')
    agency_slug = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=64, null=True, blank=True)
    duration_seconds = models.IntegerField(default=0)
    start_time = models.DateTimeField(null=True, blank=True)
    consecutive_failures = models.IntegerField(default=0)
    last_run_id = models.CharField(max_length=255, null=True, blank=True)
    last_errors = models.TextField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = '"reporting"."seeder_job_status"'
        verbose_name = 'Seeder Job Status'
        verbose_name_plural = 'Seeder Job Statuses'

    def __str__(self):
        return f"{self.table_name} -> {self.status}"


class SeederRunHistory(models.Model):
    id = models.BigAutoField(primary_key=True)
    run_id = models.CharField(max_length=255)
    manifest = models.ForeignKey(SeederCustomReportManifest, on_delete=models.CASCADE, db_column='manifest_id', related_name='run_histories')
    table_name = models.TextField()
    report_name = models.TextField()
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, db_column='agency_id', related_name='seeder_run_histories')
    agency_slug = models.CharField(max_length=255)
    report_type = models.CharField(max_length=64)
    status = models.CharField(max_length=64)
    start_time = models.DateTimeField(default=timezone.now)
    finish_time = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.IntegerField(null=True, blank=True)
    records_processed = models.BigIntegerField(default=0)
    bytes_processed = models.BigIntegerField(default=0)
    memory_usage_mb = models.IntegerField(null=True, blank=True)
    cpu_percentage = models.IntegerField(null=True, blank=True)
    consecutive_failures = models.IntegerField(default=0)
    errors = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = '"reporting"."seeder_run_history"'
        verbose_name = 'Seeder Run History'
        verbose_name_plural = 'Seeder Run Histories'

    def __str__(self):
        return f"Run {self.run_id} - {self.table_name} ({self.status})"


# -----------------------------
# Signal models and enums
# -----------------------------
class SignalSeverity(models.IntegerChoices):
    CRITICAL = 0, 'S0 - Critical'
    HIGH = 1, 'S1 - High'
    MEDIUM = 2, 'S2 - Medium'
    LOW = 3, 'S3 - Low'


class SignalGroupStatus(models.TextChoices):
    OPEN = 'open', 'Open'
    ACKNOWLEDGED = 'acknowledged', 'Acknowledged'
    SNOOZED = 'snoozed', 'Snoozed'
    CLOSED = 'closed', 'Closed'


class Signal(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    source = models.CharField(max_length=64)  # e.g., airflow, dq, manual
    signal_type = models.CharField(max_length=64)  # e.g., job_failed
    severity = models.SmallIntegerField(choices=SignalSeverity.choices)

    tenant = models.ForeignKey(Agency, on_delete=models.CASCADE, db_column='tenant_id', related_name='signals')
    tenant_code = models.CharField(max_length=128)  # Denormalized
    job_name = models.CharField(max_length=255)

    run_id = models.CharField(max_length=255, null=True, blank=True)
    task_id = models.CharField(max_length=255, null=True, blank=True)
    stage = models.CharField(max_length=128, null=True, blank=True)

    error_class = models.CharField(max_length=255, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    fingerprint = models.CharField(max_length=64, db_index=True)
    summary = models.CharField(max_length=255)
    details_json = models.JSONField(default=dict, blank=True)

    class Meta:
        managed = True
        db_table = '"reporting"."notification_signal"'
        indexes = [
            models.Index(fields=['fingerprint', '-occurred_at'], name='idx_signal_fp_occurred_at'),
            models.Index(fields=['tenant', '-occurred_at'], name='idx_signal_tenant_occurred_at'),
            models.Index(fields=['job_name', '-occurred_at'], name='idx_signal_job_occurred_at'),
        ]

    def __str__(self):
        return f"{self.job_name} - {self.fingerprint[:8]} ({self.occurred_at})"


class SignalGroup(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fingerprint = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=32, choices=SignalGroupStatus.choices, default=SignalGroupStatus.OPEN)
    current_severity = models.SmallIntegerField(choices=SignalSeverity.choices)

    tenant = models.ForeignKey(Agency, on_delete=models.CASCADE, db_column='tenant_id', related_name='signal_groups')
    tenant_code = models.CharField(max_length=128)
    job_name = models.CharField(max_length=255)
    signal_type = models.CharField(max_length=64)

    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    count_total = models.IntegerField(default=1)
    count_24h = models.IntegerField(default=0)

    last_signal = models.ForeignKey(Signal, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    assigned_to_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_signal_groups', db_column='assigned_to_user_id', db_constraint=False)
    assigned_team_id = models.UUIDField(null=True, blank=True)

    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='acknowledged_signal_groups', db_column='acknowledged_by_user_id', db_constraint=False)

    snoozed_until = models.DateTimeField(null=True, blank=True)

    opened_notified_at = models.DateTimeField(null=True, blank=True)
    last_reminded_at = models.DateTimeField(null=True, blank=True)
    last_daily_reminder_date = models.DateField(null=True, blank=True)
    last_escalated_at = models.DateTimeField(null=True, blank=True)

    slack_channel_id = models.CharField(max_length=64, null=True, blank=True)
    slack_root_ts = models.CharField(max_length=64, null=True, blank=True)

    ui_url = models.CharField(max_length=512, null=True, blank=True)

    class Meta:
        managed = True
        db_table = '"reporting"."notification_signal_group"'
        indexes = [
            models.Index(fields=['status', 'current_severity', '-last_seen_at'], name='idx_grp_stat_sev_last_seen'),
            models.Index(fields=['assigned_to_user', 'status', '-last_seen_at'], name='idx_grp_asn_stat_last_seen'),
            models.Index(fields=['tenant', 'status', '-last_seen_at'], name='idx_grp_tenant_stat_last_seen'),
            models.Index(fields=['fingerprint', 'status'], name='idx_grp_fingerprint_status'),
        ]

    def __str__(self):
        return f"Group {self.fingerprint[:8]} [{self.status}]"


class SignalGroupActivity(models.Model):
    class ActorType(models.TextChoices):
        SYSTEM = 'system', 'System'
        USER = 'user', 'User'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    signal_group = models.ForeignKey(SignalGroup, on_delete=models.CASCADE, related_name='activities')
    created_at = models.DateTimeField(auto_now_add=True)
    actor_type = models.CharField(max_length=16, choices=ActorType.choices)
    actor_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, db_column='actor_user_id', db_constraint=False)
    action = models.CharField(max_length=64)  # e.g. opened, acknowledged
    metadata_json = models.JSONField(default=dict, blank=True)

    class Meta:
        managed = True
        db_table = '"reporting"."notification_signal_group_activity"'
        indexes = [models.Index(fields=['signal_group', '-created_at'], name='idx_act_group_created_at')]


# -----------------------------
# Notification/team models
# -----------------------------
class Team(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    slack_channel_id = models.CharField(max_length=64, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = '"reporting"."notification_team"'


class TenantOwner(models.Model):
    agency = models.OneToOneField(Agency, on_delete=models.CASCADE, primary_key=True, db_column='agency_id')
    primary_owner_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+', db_column='primary_owner_user_id', db_constraint=False)
    secondary_owner_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+', db_column='secondary_owner_user_id', db_constraint=False)
    owning_team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True, related_name='+', db_column='owning_team_id')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = '"reporting"."notification_tenant_owner"'


class JobOwnerOverride(models.Model):
    tenant = models.ForeignKey(Agency, on_delete=models.CASCADE, null=True, blank=True, db_column='tenant_id')
    job_name = models.CharField(max_length=255)
    owner_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+', db_column='owner_user_id', db_constraint=False)
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True, related_name='+', db_column='team_id')

    class Meta:
        managed = True
        db_table = '"reporting"."notification_job_owner_override"'
        constraints = [models.UniqueConstraint(fields=['tenant', 'job_name'], name='uniq_job_owner_override')]


class UserSlackMap(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, primary_key=True, db_column='user_id', db_constraint=False)
    slack_user_id = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True
        db_table = '"reporting"."notification_user_slack_map"'


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
    # link to the core Agency model; keep db_column to preserve the existing column name
    agency = models.ForeignKey(
        Agency,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column='agency_id',
        db_constraint=False,
    )
    # denormalized slug kept for quick lookups/display; preserved for backward compatibility
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
        db_table = '"reporting.seeder_release_snapshot"'
        managed = True
        indexes = [
            models.Index(fields=["manifest_id", "-released_at"], name="idx_snap_manifest_release"),
            models.Index(fields=["table_name", "-released_at"], name="idx_snap_table_release"),
        ]
