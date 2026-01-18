from django.db import models

from etl_core.models.apps.bms.models.json import JSONNonBField


class FieldManager(models.Manager):
    def get_by_natural_key(self, name, template_name, tt_value):
        return self.using('bms').get(
            name=name,
            template__name=template_name,
            template__template_type__value=tt_value,
        )


class Field(models.Model):
    template = models.ForeignKey('Template', models.DO_NOTHING)
    field_type = models.ForeignKey('FieldType', models.DO_NOTHING)
    name = models.CharField(max_length=255, blank=True, null=True)
    description = models.CharField(max_length=255, blank=True, null=True)
    data_type = models.CharField(max_length=255, blank=True, null=True)
    # metadata = models.TextField(blank=True, null=True)  # This field type is a guess.
    metadata = JSONNonBField(blank=True, null=True)
    reporting_key = models.CharField(max_length=255)
    user_mention = models.BooleanField(null=True, blank=True)
    label = models.CharField(max_length=255, blank=True, null=True)
    objects = FieldManager()

    class Meta:
        managed = False
        db_table = 'field'

    def __str__(self):
        return str(self.name)

    def natural_key(self):
        return (self.name,) + self.template.natural_key()

    def short_label(self):
        return str(self.label)[:50]

    natural_key.dependencies = ['bms.template']


class FieldContext(models.Model):
    agency = models.ForeignKey('Agency', models.DO_NOTHING, blank=True, null=True)
    field = models.ForeignKey(Field, models.DO_NOTHING)
    entity_id = models.IntegerField(blank=True, null=True)
    entity_type = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'field_context'


class FieldOption(models.Model):
    sequence = models.IntegerField(blank=True, null=True)
    disabled = models.BooleanField(blank=True, null=True)
    # This field type is a guess.
    value = models.TextField(blank=True, null=True)
    field_option_version = models.ForeignKey('FieldOptionVersion', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'field_option'


class FieldOptionVersion(models.Model):
    field = models.ForeignKey(Field, models.DO_NOTHING)
    metadata = JSONNonBField(blank=True, null=True)  # This field type is a guess.
    system = models.BooleanField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'field_option_version'


class FieldTypeManager(models.Manager):
    def get_by_natural_key(self, value):
        return self.using('bms').get(value=value)


class FieldType(models.Model):
    name = models.CharField(max_length=255, blank=True, null=True)
    value = models.CharField(max_length=255, blank=True, null=True)
    description = models.CharField(max_length=255, blank=True, null=True)

    objects = FieldTypeManager()

    class Meta:
        managed = False
        db_table = 'field_type'

    def __str__(self):
        return f'{self.id}-{self.name}'

    def natural_key(self):
        return (self.value,)


class FieldValue(models.Model):
    agency = models.ForeignKey('Agency', models.DO_NOTHING, blank=True, null=True)
    form = models.ForeignKey('Form', models.DO_NOTHING)
    field = models.ForeignKey(Field, models.DO_NOTHING)
    correlative = models.IntegerField(blank=True, null=True)
    string_value = models.CharField(max_length=255, blank=True, null=True)
    number_value = models.DecimalField(
        max_digits=65535, decimal_places=10, blank=True, null=True
    )
    date_value = models.DateField(blank=True, null=True)
    boolean_value = models.BooleanField(blank=True, null=True)
    parent_key = models.CharField(max_length=255, blank=True, null=True)
    key = models.CharField(max_length=255, blank=True, null=True)
    index = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'field_value'


class FieldVersion(models.Model):
    field = models.ForeignKey(Field, models.DO_NOTHING)
    disable = models.BooleanField(blank=True, null=True)
    system = models.BooleanField(blank=True, null=True)
    reason = models.CharField(max_length=255, blank=True, null=True)
    # This field type is a guess.
    metadata = models.TextField(blank=True, null=True)
    created = models.DateTimeField(blank=True, null=True)
    updated = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'field_version'
