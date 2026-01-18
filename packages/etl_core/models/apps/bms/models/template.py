import logging

from django.db import models
from django.db import transaction

from etl_database_schema.apps.bms.models.config import ConfigOptionValue
from etl_database_schema.apps.bms.models.event import EventConfigurationSchemeTemplateType, EventSchemeHandler
from etl_database_schema.apps.bms.models.handler import Handler
from etl_database_schema.apps.bms.models.validation import ValidationVersion
from etl_database_schema.apps.bms.models.errors import ConfigError
from etl_database_schema.apps.bms.models.json import JSONNonBField
from etl_database_schema.apps.bms.models.screen import Screen

log = logging.getLogger(__name__)


class TemplateManager(models.Manager):
    def get_by_natural_key(self, name, tt_value):
        return self.using('bms').get(name=name, template_type__value=tt_value)


class TemplateTypeManager(models.Manager):
    def get_by_natural_key(self, value):
        return self.using('bms').get(value=value)


class TemplateType(models.Model):
    name = models.CharField(max_length=255, blank=True, null=True)
    value = models.CharField(max_length=255, blank=True, null=True)
    abbreviation = models.CharField(max_length=255, blank=True, null=True)
    description = models.CharField(max_length=255, blank=True, null=True)

    objects = TemplateTypeManager()

    class Meta:
        managed = False
        db_table = 'template_type'

    def __str__(self):
        return f'{self.name} ({self.id})'

    def natural_key(self):
        return (self.value,)

    def configurations(self):
        """Returns the config structure that reference this template"""
        return (
            ConfigOptionValue.objects.filter(
                config_scheme__config_option__config_entity__name='template',
                scope=self.value,
            )
            .select_related('config_scheme', 'config_scheme__config_option')
            .order_by('config_scheme__config_option__name')
        )

    # @transaction.atomic(using='bms')
    def add_event_handler(self, agency, state, handlers):
        """Creates an event configuration and attaches to the current event configuration.

        (Agency should always have an event configuration context, or we have a bigger problem)

        """
        # Get post_submit scope for agency
        context = agency.get_context_for('event', 'handler', 'POST_SUBMIT')
        optionvalue = context.configoptionvalue_set().first()
        stored_handlers = [h for h in optionvalue.value if h['name'] in handlers]
        rest = [h for h in optionvalue.value if h['name'] not in handlers]

        # calculate handlers that do not currently exists on the handlers from db
        captured_handlers_names = [st['name'] for st in stored_handlers]
        missing_handlers = [h for h in handlers if h not in captured_handlers_names]

        # create missing handlers
        for missing_hanlder in missing_handlers:
            new_hanlder = {
                'name': missing_hanlder,
                'templateTypes': [self.value],
                'states': [state.value],
            }
            rest.append(new_hanlder)

        for stored_handler in stored_handlers:
            # If the handler was extracted, update it. If not, create it.
            if stored_handler is not None:
                if state.value not in stored_handler['states']:
                    stored_handler['states'].append(state.value)
                if self.value not in stored_handler['templateTypes']:
                    stored_handler['templateTypes'].append(self.value)

                # add the modified handler values to the remaining list of handlers for saving.
                rest.append(stored_handler)

        optionvalue.value = rest
        optionvalue.save()
        # update event config to reflect the change
        return self.add_event_configuration(agency, handlers, state)

    def add_event_configuration(self, agency, handler_names, state):
        """Creates the event configuration in the event tables.

        When a workflow for the agency (through self service) is created, the NodeAPI will
        manage this config up-to-date
        """
        context = agency.get_event_context_for('POST_SUBMIT', self.value)
        scheme = context.event_configuration_scheme

        for handler_name in handler_names:
            handler = Handler.objects.filter(name=handler_name).first()

            log.info(
                "Attempting to get or create template_type: %s, state: %s, scheme: %s",
                self,
                state,
                scheme,
            )
            # Find if exist, if not create
            ecstt, _ = EventConfigurationSchemeTemplateType.objects.get_or_create(
                template_type=self,
                state=state,
                event_configuration_scheme=scheme,
                defaults={'meta': '{}'},
            )
            event_scheme_handler, _ = EventSchemeHandler.objects.get_or_create(
                event_configuration_scheme_template_type=ecstt,
                handler=handler,
                defaults={'meta': {}},
            )

        return True


class Template(models.Model):
    template_type = models.ForeignKey('TemplateType', models.DO_NOTHING)
    name = models.CharField(max_length=255, blank=True, null=True)
    category = models.CharField(max_length=255, blank=True, null=True)

    objects = TemplateManager()

    class Meta:
        managed = False
        db_table = 'template'

    def __str__(self):
        return str(self.name)

    def natural_key(self):
        return str(self.name) + self.template_type.natural_key()

    natural_key.dependencies = ['bms.templatetype']

    @property
    def field_set_sorted_label(self):
        return self.field_set.select_related('field_type').order_by(
            'label', 'reporting_key'
        )

    @property
    def field_set_sorted_name(self):
        return self.field_set.select_related('field_type').order_by('name')

    @property
    def field_set_sorted_name_with_validations(self):
        from django.db.models import Prefetch

        validations_and_conditions = ValidationVersion.objects.select_related(
            'validation_condition', 'validation'
        )
        # self.field_set.prefetch_related('fieldversion_set', 'fieldversion_set__validationversion_set').order_by('name')
        return (
            self.field_set.filter()
            .prefetch_related(
                'fieldversion_set',
                Prefetch(
                    'fieldversion_set__validationversion_set',
                    queryset=validations_and_conditions,
                ),
            )
            .order_by('name')
        )

    def get_linked_template(self, agency):
        context = agency.get_context_for(
            'link', ConfigOptionValue.LINK_TEMPLATE, self.template_type.value
        )

        if context:
            cov = context.configoptionvalue_set()
            config_value = cov.first()
            if not config_value:
                raise ConfigError(
                    f"Linked Template configuration missing config_option_value ({self} context={context})"
                )
            if isinstance(config_value.value, list):
                # This should be an array and we'll work on the first...
                target_value = config_value.value[0]
            else:
                raise ConfigError(
                    f"Linked Template for {self}/{config_value} is not an array (perhaps it is a string?): {config_value.value}"
                )
            template_type = TemplateType.objects.filter(value=target_value).first()
            if template_type:
                return template_type
            else:
                raise ConfigError(
                    f"Linked Template with value={target_value} does not exist ({self}/{context})"
                )
        else:
            return None

    @transaction.atomic(using='bms')
    def link_to(self, agency, target):
        """Link this template to a second template (within a given agency)

        :param agency: The agency to setup the linking for
        :param target: The template to link TO
        """
        base_tt = self.template_type
        target_template_type = target.template_type
        # Since we'll be converting this value to an array anyways @ create_link_config
        # Let's use it as an string, so we don't nest arrays
        config = target_template_type.value
        scope = base_tt.value

        log.info("Linking %s (%s) to %s", self, base_tt, target_template_type)

        agency.create_link_config(
            target=config, base=scope, link_option='targetFormType'
        )

        log.info(f"Succesfully created link config for {self} -> {target}")
        return True

    def get_field_name_hash(self):
        """Gets a hash to identify all the unique field names on the template"""
        from hashlib import md5

        fields = self.field_set.all().values_list('name', flat=True).distinct()
        distinct_fields = set(fields)
        return md5(str(distinct_fields).encode('utf-8')).hexdigest()

    def get_report_key_hash(self):
        """Gets a hash to identify all the unique field names on the template"""
        from hashlib import md5

        fields = self.field_set.all().values_list('reporting_key', flat=True).distinct()
        distinct_fields = set(fields)
        return md5(str(distinct_fields).encode('utf-8')).hexdigest()


class TemplateScreen(models.Model):
    template = models.ForeignKey(Template, models.DO_NOTHING)
    screen = models.ForeignKey(Screen, models.DO_NOTHING)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'template_screen'


class TemplateStatus(models.Model):
    name = models.CharField(max_length=255, blank=True, null=True)
    description = models.CharField(max_length=255, blank=True, null=True)
    label = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'template_status'


class TemplateTemplateStatus(models.Model):
    template = models.ForeignKey(Template, models.DO_NOTHING)
    template_status = models.ForeignKey(TemplateStatus, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'template_template_status'


class TemplateVersionManager(models.Manager):
    """Defers the schema field"""

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .defer('schema')
            .select_related('template', 'template__template_type')
        )

    def get_by_natural_key(self, version, agency_identifier, template_name, tt_value):
        return self.using('bms').get(
            version=version,
            agency__identifier=agency_identifier,
            template__template_type__value=tt_value,
        )


class TemplateVersion(models.Model):
    agency = models.ForeignKey('Agency', models.DO_NOTHING)
    template = models.ForeignKey(Template, models.DO_NOTHING)
    workflow = models.ForeignKey('Workflow', models.DO_NOTHING, blank=True, null=True)
    disabled = models.BooleanField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    schema = JSONNonBField(blank=True, null=True)  # This field type is a guess.
    template_json = JSONNonBField(blank=True, null=True)
    version = models.IntegerField(blank=True, null=True)

    objects = TemplateVersionManager()

    class Meta:
        managed = False
        db_table = 'template_version'

    def natural_key(self):
        return (self.version,) + self.agency.natural_key() + self.template.natural_key()

    natural_key.dependencies = ['bms.agency', 'bms.template']

    @property
    def screen_components(self):
        if self.schema:
            if 'screenComponents' in self.schema:
                return self.schema['screenComponents']
            else:
                log.error(
                    "TemplateVersion %s schema does not have a screen component in the schema",
                    self,
                )
        else:
            log.error(
                "TemplateVersion %s does not have a populated schema",
                self,
            )
        return []

    def schema_components(self):
        """Takes the schema and represents it in a way that is digestible by keys"""
        i = 0
        screen_components = self.screen_components
        for components in screen_components:
            i += 1
            elems = {}
            for options in components['options']:
                if options['name'] in ('id', 'reportingKey', 'title'):
                    elems[options['name']] = options['value']
                # elif options['name'] not in ('key', 'disable', 'source', 'options', 'icon', 'columns'):
                #    print([options['name'], options])

                # elems[condition] = {'id': condition_value['id'], 'value': condition_value['value']}

            yield elems

    def current_fields(self):
        """Returns the information about all the fields currently on this template version"""
        template_fields = self.template.field_set.all().select_related('field_type')
        template_field_dict = {f.id: f for f in template_fields}
        current_fields = []
        for field_version in self.schema['fieldVersions']:
            fv = dict(field_version)
            _field = template_field_dict[fv['field_id']]
            fv['field__name'] = _field.name
            fv['field__label'] = _field.short_label()
            fv['field__reporting_key'] = _field.reporting_key
            fv['field__field_type__name'] = _field.field_type.name
            current_fields.append(fv)
        return current_fields

    @property
    def linked_template_version(self):
        """Retrieve and cache the template version this template is linked to"""
        tv = None
        if getattr(self, '_linked_template_version', None) is None and not getattr(
            self, '_linked_template_version_checked', False
        ):
            # Checking for template version is expensive. So only do it once.
            self._linked_template_version_checked = True
            tt = self.get_linked_template_type()
            if tt is not None:
                # Template version now stores multiple versions per template type. So just get the most recent version
                tv_ = TemplateVersion.objects.filter(
                    agency=self.agency, template__template_type=tt
                ).order_by('-version')
                tv = tv_.first()
                if tv is None:
                    log.error(
                        "Configuration Error. Template Type %s doesn't have a template version on the %s. But Link said it would.",
                        tt,
                        self.agency,
                    )
            self._linked_template_version = tv
        return self._linked_template_version

    def get_linked_template_type(self):
        """Lookup the link from the configuration"""
        return self.template.get_linked_template(self.agency)

    def get_linked_field_setting(self):
        if self.linked_template_version:
            context = self.agency.get_context_for(
                'link', 'formKeyMappings', self.template.template_type.value
            )
            if context:
                option_values = context.configoptionvalue_set().all()
                return option_values

    def get_linked_fields(self):
        option_values = self.get_linked_field_setting()
        if option_values:
            return option_values.first().value

    @property
    def linked_fields(self):
        # Check the cache AND whether or not we have checked before
        if getattr(self, '_linked_fields', None) is None and not getattr(
            self, '_linked_fields_checked', False
        ):
            self._linked_fields_checked = True
            self._linked_fields = self.get_linked_fields()
        return self._linked_fields


class TemplateWorkflow(models.Model):
    template_version = models.ForeignKey(TemplateVersion, models.DO_NOTHING)
    workflow = models.ForeignKey('Workflow', models.CASCADE, blank=True, null=True)
    disabled = models.BooleanField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'template_workflow'

    def __str__(self):
        return str(self.id)


class TemplateRoleVisibility(models.Model):
    id = models.AutoField(primary_key=True)
    agency = models.ForeignKey('Agency', models.DO_NOTHING)
    template = models.ForeignKey(Template, models.DO_NOTHING)
    role_constraints = JSONNonBField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'template_role_visibility'

    def __str__(self):
        return str(self.id)


class TemplateSecurityConfig(models.Model):
    id = models.AutoField(primary_key=True)
    agency = models.ForeignKey('Agency', models.DO_NOTHING)
    template = models.ForeignKey(Template, models.DO_NOTHING)
    submitter_visibility = models.BooleanField(default=False)

    class Meta:
        managed = False
        db_table = 'template_security_config'

    def __str__(self):
        return str(self.id)


class Temptable(models.Model):
    count = models.BigIntegerField(blank=True, null=True)
    full_name = models.CharField(max_length=255, blank=True, null=True)
    unit_assignment = models.CharField(max_length=255, blank=True, null=True)
    form_id = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'temptable'
