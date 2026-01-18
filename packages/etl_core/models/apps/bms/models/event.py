from django.db import models
from etl_core.models.apps.bms.models.json import JSONNonBField


class EventConfigurationSchemeTemplateTypeManager(models.Manager):
    """ Selects the state and template type automatically"""

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related(
                'state',
                'template_type',
                'event_configuration_scheme',
                'event_configuration_scheme__event',
            )
        )


class EventConfigurationSchemeTemplateType(models.Model):
    event_configuration_scheme = models.ForeignKey(
        'EventConfigurationScheme', models.DO_NOTHING, related_query_name="ecstt"
    )
    template_type = models.ForeignKey('TemplateType', models.DO_NOTHING)
    state = models.ForeignKey('State', models.DO_NOTHING, blank=True, null=True)
    meta = models.TextField(blank=True, null=True)  # This field type is a guess.
    objects = EventConfigurationSchemeTemplateTypeManager()

    class Meta:
        managed = False
        db_table = 'event_configuration_scheme_template_type'


class EventSchemeHandler(models.Model):
    event_configuration_scheme_template_type = models.ForeignKey(
        EventConfigurationSchemeTemplateType, models.DO_NOTHING
    )
    handler = models.ForeignKey('Handler', models.DO_NOTHING)
    meta = JSONNonBField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'event_scheme_handler'

    def __str__(self):
        return f'{self.id}-{self.handler}'


class Event(models.Model):
    name = models.CharField(max_length=255, blank=True, null=True)
    description = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'event'

    def __str__(self):
        return self.name


class EventConfigurationContext(models.Model):
    agency = models.ForeignKey('Agency', models.DO_NOTHING, blank=True, null=True)
    event = models.ForeignKey(Event, models.DO_NOTHING)
    event_configuration_scheme = models.ForeignKey(
        'EventConfigurationScheme', models.DO_NOTHING
    )
    created = models.DateTimeField(blank=True, null=True)
    updated = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'event_configuration_context'


class EventConfigurationScheme(models.Model):
    event = models.ForeignKey(Event, models.DO_NOTHING)
    name = models.CharField(max_length=255, blank=True, null=True)
    description = models.CharField(max_length=255, blank=True, null=True)
    system = models.BooleanField(blank=True, null=True)
    created = models.DateTimeField(blank=True, null=True)
    updated = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'event_configuration_scheme'

    def __str__(self):
        return f'{self.id}-{self.name} ({self.event})'
