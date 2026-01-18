from django.db import models

from etl_database_schema.apps.bms.models.benchmark_user import BenchmarkUser
from etl_database_schema.apps.bms.models.reasons import Reason


class TimeTrack(models.Model):
    action = models.CharField(max_length=255, blank=True, null=True)
    from_date = models.DateTimeField(blank=True, null=True)
    to_date = models.DateTimeField(blank=True, null=True)
    notes = models.CharField(max_length=255, blank=True, null=True)
    author = models.ForeignKey(BenchmarkUser, models.DO_NOTHING, blank=True, null=True)
    reason = models.ForeignKey(Reason, models.DO_NOTHING, blank=True, null=True)
    time_tracking = models.ForeignKey('TimeTracking', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'time_track'


class TimeTracking(models.Model):
    is_paused = models.BooleanField(blank=True, null=True)
    active_time = models.IntegerField(blank=True, null=True)
    inactive_time = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'time_tracking'
