from django.db import models


class Agency(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255, blank=True)

    class Meta:
        managed = False
        db_table = '"reporting"."agency"'


class MonitoringFileSchemaDefinition(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255, blank=False, unique=True)
    description = models.TextField(blank=True, null=True)
    definition = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = '"reporting"."monitoring_file_schema_definition"'


class MonitoringFile(models.Model):
    id = models.AutoField(primary_key=True)
    s3_url = models.CharField(max_length=250, blank=True)
    file_name = models.CharField(max_length=250, blank=False)
    range = models.CharField(max_length=20, blank=False)
    is_active = models.BooleanField(default=False, blank=True)
    agency = models.ForeignKey(Agency, models.PROTECT, null=True)
    agency_slug = models.CharField(max_length=255, null=False)
    notify_slack = models.BooleanField(default=False)
    is_missing = models.BooleanField(default=False)
    latest_data_quality_score = models.IntegerField(null=True, blank=True)
    schema_definition = models.ForeignKey(
        MonitoringFileSchemaDefinition, on_delete=models.SET_NULL, null=True
    )

    class Meta:
        managed = False
        db_table = '"reporting"."monitoring_file"'


class MonitoringFileRun(models.Model):
    id = models.AutoField(primary_key=True)
    monitoring_file = models.ForeignKey(
        MonitoringFile,
        on_delete=models.CASCADE,
        related_name="monitoring_file_runs",
        db_column="monitoring_file_id",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    file_size = models.BigIntegerField(blank=True)
    run_date = models.DateField(blank=True)
    run_hour = models.IntegerField(blank=False)

    class Meta:
        managed = False
        db_table = '"reporting"."monitoring_file_run"'


class MonitoringFileDataQuality(models.Model):
    id = models.AutoField(primary_key=True)
    monitoring_file_run = models.OneToOneField(
        MonitoringFileRun,
        on_delete=models.CASCADE,
        related_name="data_quality",
        db_column="monitoring_file_run_id",
    )
    score = models.IntegerField()
    passed = models.BooleanField(default=False)
    metrics = models.JSONField(default=dict)
    deductions = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = '"reporting"."monitoring_file_data_quality"'
