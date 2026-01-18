from django.db import models

from etl_core.models.apps.bms.models.agency import Agency
from etl_core.models.apps.bms.models.benchmark_user import BenchmarkUser


class Import(models.Model):
    file_name = models.CharField(max_length=255, blank=True, null=True)
    file_hash_id = models.CharField(max_length=255, blank=True, null=True)
    url = models.CharField(max_length=255, blank=True, null=True)
    # This field type is a guess.
    progress = models.TextField(blank=True, null=True)
    conflicts_resolved = models.BooleanField(blank=True, null=True)
    conflict_errors = models.BooleanField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    agency = models.ForeignKey(Agency, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'import'


class ImportConflict(models.Model):
    # This field type is a guess.
    new_object = models.TextField(blank=True, null=True)
    # This field type is a guess.
    change = models.TextField(blank=True, null=True)
    approved = models.DateTimeField(blank=True, null=True)
    finished = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    # This field type is a guess.
    error = models.TextField(blank=True, null=True)
    agency = models.ForeignKey(Agency, models.DO_NOTHING, blank=True, null=True)
    import_field = models.ForeignKey(
        Import, models.DO_NOTHING, db_column='import_id', blank=True, null=True
    )  # Field renamed because it was a Python reserved word.
    user = models.ForeignKey(BenchmarkUser, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'import_conflict'
