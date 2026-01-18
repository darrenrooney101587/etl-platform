from django.db import models

from etl_database_schema.apps.bms.models.benchmark_user import BenchmarkUser
from etl_database_schema.apps.bms.models.form import Form


class Share(models.Model):
    form = models.ForeignKey(Form, models.DO_NOTHING)
    share_from = models.ForeignKey(
        BenchmarkUser,
        models.DO_NOTHING,
        blank=True,
        null=True,
        related_name='share_sharefrom_set',
    )
    share_to = models.ForeignKey(
        BenchmarkUser,
        models.DO_NOTHING,
        blank=True,
        null=True,
        related_name='share_shareto_set',
    )
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    action = models.CharField(max_length=255, blank=True, null=True)
    share_grouping_id = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'share'
