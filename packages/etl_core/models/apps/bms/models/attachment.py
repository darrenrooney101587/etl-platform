from django.db import models


class Attachment(models.Model):
    filename = models.CharField(max_length=255, blank=True, null=True)
    mime_type = models.CharField(max_length=255, blank=True, null=True)
    byte_size = models.BigIntegerField(blank=True, null=True)
    metadata = models.TextField(blank=True, null=True)
    deleted = models.BooleanField(blank=True, null=True)
    # This field type is a guess.
    fields = models.TextField(blank=True, null=True)
    benchmark_user_id = models.CharField(max_length=255, blank=True, null=True)
    original_filename = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    processed = models.BooleanField(blank=True, null=True)
    cancelled = models.BooleanField(blank=True, null=True)
    container = models.CharField(max_length=255, blank=True, null=True)
    attachable_id = models.IntegerField(blank=True, null=True)
    attachable_type = models.CharField(max_length=255, blank=True, null=True)
    created = models.DateTimeField(blank=True, null=True)
    updated = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'attachment'
