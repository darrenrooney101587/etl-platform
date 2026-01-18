from django.db import models

from etl_core.models.apps.bms.models.agency import Agency
from etl_core.models.apps.bms.models.benchmark_user import BenchmarkUser
from etl_core.models.apps.bms.models.form import Form


class TrainingTask(models.Model):
    agency = models.ForeignKey(Agency, models.DO_NOTHING)
    name = models.CharField(max_length=128)
    description = models.CharField(max_length=255, blank=True, null=True)
    attachment = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'training_task'


class TrainingTaskTracking(models.Model):
    user = models.ForeignKey(BenchmarkUser, models.DO_NOTHING)
    form = models.ForeignKey(Form, models.DO_NOTHING)
    training_task = models.ForeignKey(TrainingTask, models.DO_NOTHING)
    task_value = models.CharField(max_length=255)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    increase_value = models.IntegerField()
    timestamp = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'training_task_tracking'
