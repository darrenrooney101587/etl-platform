from django.db import models


class Vendor(models.Model):
    name = models.TextField()
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    is_deleted = models.BooleanField()
    deleted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'vendor'


class VendorKey(models.Model):
    vendor = models.ForeignKey(Vendor, models.DO_NOTHING)
    key = models.TextField()
    methods = models.CharField(max_length=255)
    ttl = models.BigIntegerField()
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    is_deleted = models.BooleanField()
    deleted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'vendor_key'
