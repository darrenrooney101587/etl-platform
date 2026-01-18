from django.db import models

from etl_core.models.apps.bms.models.json import JSONNonBField


class Notification(models.Model):
    agency = models.ForeignKey('Agency', models.DO_NOTHING, blank=True, null=True)
    user = models.ForeignKey('BenchmarkUser', models.DO_NOTHING)
    title = models.CharField(max_length=255)
    body = models.TextField()
    data = JSONNonBField(blank=True, null=True)  # This field type is a guess.
    action = models.CharField(max_length=255)
    new = models.BooleanField()
    seen = models.DateField(blank=True, null=True)
    action_item = models.BooleanField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True, auto_now_add=True)
    updated_at = models.DateTimeField(blank=True, null=True, auto_now=True)
    is_dismissable = models.BooleanField(blank=True, null=True)
    type = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'notification'
