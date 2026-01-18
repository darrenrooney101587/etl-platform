from django.db import models


class Reason(models.Model):
    name = models.CharField(max_length=128)
    description = models.CharField(max_length=255, blank=True, null=True)
    link = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    agency_id = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'reason'
