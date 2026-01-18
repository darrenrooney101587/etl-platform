import logging

from django.db import models
from etl_database_schema.apps.bms.models.json import JSONNonBField


log = logging.getLogger(__name__)


class ConfigContext(models.Model):
    agency = models.ForeignKey('Agency', models.DO_NOTHING, blank=True, null=True)
    config_option = models.ForeignKey('ConfigOption', models.DO_NOTHING)
    config_scheme = models.ForeignKey('ConfigScheme', models.DO_NOTHING)
    enable = models.BooleanField(blank=True, null=True)
    scope = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True, auto_now_add=True)
    updated_at = models.DateTimeField(blank=True, null=True, auto_now=True)

    class Meta:
        managed = False
        db_table = 'config_context'

    def configoptionvalue_set(self):
        """ Returns the configoptionvalue that tie to this configcontext

        ConfigOptionValue and ConfigContext both are children of ConfigScheme.
        The Scope of ConfigContext will match the Scope of ConfigOptionValue
        So basically, ConfigCOntext identifies the setting specific to an agency
        """
        return ConfigOptionValue.objects.filter(
            config_scheme=self.config_scheme, scope=self.scope
        )


class ConfigOptionValue(models.Model):
    LINK_TEMPLATE = 'targetFormType'  # Value that allows linking templates

    config_scheme = models.ForeignKey('ConfigScheme', models.DO_NOTHING)
    value = JSONNonBField(blank=True, null=True)  # This field type is a guess.
    scope = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True, auto_now_add=True)
    updated_at = models.DateTimeField(blank=True, null=True, auto_now=True)

    class Meta:
        managed = False
        db_table = 'config_option_value'

    def configcontext_set(self):
        """ Returns the configcontext that tie to this optionvalue

        ConfigOptionValue and ConfigContext both are children of ConfigScheme.
        The Scope of ConfigContext will match the Scope of ConfigOptionValue
        So basically, ConfigCOntext identifies the setting specific to an agency
        """
        return ConfigContext.objects.filter(
            config_scheme=self.config_scheme, scope=self.scope
        ).select_related('agency')


class ConfigEntity(models.Model):
    name = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'config_entity'

    def __str__(self):
        return '{} ({})'.format(self.name, self.id)

    def configoptionvalue_set(self):
        """ This restructures the relationships to focus on the more logical options values

        Basically this will give you the fields rather than forcing you to descend through the enabled/disabled status
        """
        return (
            ConfigOptionValue.objects.filter(
                config_scheme__config_option__config_entity_id=self.id
            )
            .select_related('config_scheme', 'config_scheme__config_option')
            .order_by('scope')
        )


class ConfigOption(models.Model):
    config_entity = models.ForeignKey(ConfigEntity, models.DO_NOTHING)
    name = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True, auto_now_add=True)
    updated_at = models.DateTimeField(blank=True, null=True, auto_now=True)

    class Meta:
        managed = False
        db_table = 'config_option'

    def __str__(self):
        return '{} ({})'.format(self.name, self.config_entity.name)

    @property
    def configscheme_set_bysystem(self):
        return self.configscheme_set.all().order_by('system')


class ConfigScheme(models.Model):
    config_option = models.ForeignKey(ConfigOption, models.DO_NOTHING)
    system = models.BooleanField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'config_scheme'

    def __str__(self):
        return '{} ({})'.format(self.id, self.config_option)

    @property
    def associated_agencies(self):
        return self.configcontext_set.distinct('agency')


class ConfigOptionGroup(models.Model):
    config_option_value = models.ForeignKey('ConfigOptionValue', models.DO_NOTHING)
    group = models.ForeignKey('Group', models.DO_NOTHING)
    created_at = models.DateTimeField(blank=True, null=True, auto_now_add=True)
    updated_at = models.DateTimeField(blank=True, null=True, auto_now=True)

    class Meta:
        managed = False
        db_table = 'config_option_group'
