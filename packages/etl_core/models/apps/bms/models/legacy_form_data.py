from django.db import models

from etl_database_schema.apps.bms.models.form import Form
from etl_database_schema.apps.bms.models.agency import Agency


class LegacyFormData(models.Model):
    form = models.ForeignKey(Form, models.DO_NOTHING)
    agency = models.ForeignKey(Agency, models.DO_NOTHING)
    # This field type is a guess.
    data = models.TextField(blank=True, null=True)
    migrated = models.BooleanField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'legacy_form_data'
