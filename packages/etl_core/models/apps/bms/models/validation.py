from django.db import models

from etl_database_schema.apps.bms.models.field import FieldVersion


class Validation(models.Model):
    validation_option = models.ForeignKey(
        'ValidationOption', models.DO_NOTHING, blank=True, null=True
    )
    message = models.CharField(max_length=255, blank=True, null=True)
    # This field type is a guess.
    metadata = models.TextField(blank=True, null=True)
    disabled = models.BooleanField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'validation'


class ValidationCondition(models.Model):
    property = models.CharField(max_length=255, blank=True, null=True)
    operator = models.CharField(max_length=255, blank=True, null=True)
    # This field type is a guess.
    value = models.TextField(blank=True, null=True)
    disabled = models.BooleanField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'validation_condition'


class ValidationHelper(models.Model):
    name = models.CharField(max_length=255, blank=True, null=True)
    description = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'validation_helper'


class ValidationOption(models.Model):
    validation_helper = models.ForeignKey(ValidationHelper, models.DO_NOTHING)
    name = models.CharField(max_length=255, blank=True, null=True)
    description = models.CharField(max_length=255, blank=True, null=True)
    message = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'validation_option'


class ValidationVersion(models.Model):
    field_version = models.ForeignKey(FieldVersion, models.DO_NOTHING)
    validation = models.ForeignKey(Validation, models.DO_NOTHING, blank=True, null=True)
    validation_condition = models.ForeignKey(
        ValidationCondition, models.DO_NOTHING, blank=True, null=True
    )
    # This field type is a guess.
    value = models.TextField(blank=True, null=True)
    created = models.DateTimeField(blank=True, null=True)
    updated = models.DateTimeField(blank=True, null=True)
    disable = models.BooleanField(blank=True, null=True)
    # This field type is a guess.
    metadata = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'validation_version'
