from django.db import models

from etl_core.models.apps.bms.models.field import Field


class Screen(models.Model):
    name = models.CharField(max_length=255, blank=True, null=True)
    description = models.CharField(max_length=255, blank=True, null=True)
    version = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'screen'


class ScreenComponent(models.Model):
    name = models.CharField(max_length=255, blank=True, null=True)
    description = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    order = models.IntegerField(blank=True, null=True)
    parent_screen_component = models.ForeignKey(
        'self', models.DO_NOTHING, blank=True, null=True
    )
    screen_component_type = models.ForeignKey('ScreenComponentType', models.DO_NOTHING)
    screen = models.ForeignKey(Screen, models.DO_NOTHING)
    field = models.ForeignKey(Field, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'screen_component'

    def __str__(self):
        return f'{self.name} ({self.id})'


class ScreenComponentCondition(models.Model):
    screen_component = models.ForeignKey(ScreenComponent, models.DO_NOTHING)
    every = models.BooleanField()
    behavior = models.CharField(max_length=255)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    source = models.CharField(max_length=255, blank=True, null=True)
    agency = models.ForeignKey('Agency', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'screen_component_condition'


class ScreenComponentOption(models.Model):
    name = models.CharField(max_length=255, blank=True, null=True)
    value = models.CharField(max_length=255, blank=True, null=True)
    description = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    screen_component = models.ForeignKey(ScreenComponent, models.DO_NOTHING)
    agency = models.ForeignKey('Agency', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'screen_component_option'


class ScreenComponentOverriddenOption(models.Model):
    name = models.CharField(max_length=255, blank=True, null=True)
    value = models.CharField(max_length=255, blank=True, null=True)
    description = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    screen_component = models.ForeignKey(ScreenComponent, models.DO_NOTHING)
    agency = models.ForeignKey('Agency', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'screen_component_overridden_option'


class ScreenComponentRule(models.Model):
    screen_component_condition = models.ForeignKey(
        ScreenComponentCondition, models.DO_NOTHING
    )
    property = models.CharField(max_length=255, blank=True, null=True)
    operator = models.CharField(max_length=255)
    content = models.TextField()  # This field type is a guess.
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'screen_component_rule'


class ScreenComponentType(models.Model):
    name = models.CharField(max_length=255, blank=True, null=True)
    value = models.CharField(max_length=255, blank=True, null=True)
    description = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'screen_component_type'


class ScreenComponentVersion(models.Model):
    agency = models.ForeignKey('Agency', models.DO_NOTHING)
    screen_component = models.ForeignKey(ScreenComponent, models.DO_NOTHING)
    disable = models.BooleanField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'screen_component_version'


class ScreenTree(models.Model):
    depth = models.IntegerField(blank=True, null=True)
    screen = models.ForeignKey(Screen, models.DO_NOTHING)
    ancestor = models.ForeignKey(
        ScreenComponent,
        models.DO_NOTHING,
        blank=True,
        null=True,
        related_name='screentree_ancestor_set',
    )
    descendant = models.ForeignKey(
        ScreenComponent,
        models.DO_NOTHING,
        blank=True,
        null=True,
        related_name='screentree_descendant_set',
    )
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'screen_tree'


class ScreenContext(models.Model):
    agency = models.ForeignKey('Agency', models.DO_NOTHING)
    screen_entity_id = models.IntegerField()
    screen_entity_type = models.CharField(max_length=255)
    context_entity_id = models.IntegerField(blank=True, null=True)
    context_entity_type = models.CharField(max_length=255)
    enable = models.BooleanField()
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'screen_context'
        constraints = [
            models.UniqueConstraint(
                fields=[
                    'agency_id',
                    'screen_entity_id',
                    'screen_entity_type',
                    'context_entity_id',
                    'context_entity_type',
                ],
                name='screen_context_agency_entity_uk',
            )
        ]
