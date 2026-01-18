from django.db import models

from etl_core.models.apps.bms.models.benchmark_user import BenchmarkUser


class IntegrationError(models.Model):
    user = models.ForeignKey(BenchmarkUser, models.DO_NOTHING)
    message = models.TextField(blank=True, null=True)
    email = models.TextField(blank=True, null=True)
    date = models.DateTimeField(blank=True, null=True)
    error_severity = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'integration_error'
        verbose_name = 'KMI Integration Error'
        verbose_name_plural = 'KMI Integration Errors'
