from django.db import models

from etl_database_schema.apps.bms.models.form import Form
from etl_database_schema.apps.bms.models.benchmark_user import BenchmarkUser


class Link(models.Model):
    linked_from = models.ForeignKey(Form, models.DO_NOTHING)
    linked_to = models.ForeignKey(Form, models.DO_NOTHING, related_name='link_to_set')
    user = models.ForeignKey(BenchmarkUser, models.DO_NOTHING)
    link_type = models.ForeignKey('LinkType', models.DO_NOTHING)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'link'


class LinkType(models.Model):
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    name = models.CharField(max_length=128)
    description = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'link_type'

    def __str__(self):
        return self.name
