import datetime
import logging

from django.db import models
from django.db import transaction
from django.conf import settings
# from etl_database_schema.apps.services import bms_cache
from etl_database_schema.apps.bms.models.snapshot import Snapshot
from etl_database_schema.apps.bms.models.config import (
    ConfigOption,
    ConfigScheme,
    ConfigOptionValue,
    ConfigContext,
)
from etl_database_schema.apps.bms.models.workflow import Transition
from etl_database_schema.apps.bms.models.template import TemplateWorkflow
from etl_database_schema.apps.bms.models.errors import LinkingError

log = logging.getLogger(__name__)


class AgencyManager(models.Manager):
    def get_by_natural_key(self, identifier):
        return self.using('bms').get(identifier=identifier)


class Agency(models.Model):
    name = models.CharField(max_length=128)
    identifier = models.CharField(max_length=255, blank=True, null=True, unique=True)
    logo = models.CharField(max_length=255, blank=True, null=True)
    timezone = models.CharField(max_length=255, blank=True, null=True)
    address = models.CharField(max_length=255)
    subdomain = models.CharField(max_length=255)
    izenda_tenant_id = models.CharField(max_length=255, blank=True, null=True)
    groups = models.ManyToManyField('Group', through='AgencyGroup')
    active = models.BooleanField(null=False, blank=False, default=True)
    lms_integration_enabled = models.BooleanField(
        null=False, blank=False, default=False
    )
    integration_id = models.UUIDField(blank=True, null=True)
    templates = models.ManyToManyField('Template', through='TemplateVersion')

    objects = AgencyManager()

    class Meta:
        managed = False
        db_table = 'agency'
        verbose_name_plural = 'Agencies'
        permissions = (
            ('list_agencykeys', 'List Agency\'s Cached Keys'),
            ('decommission_agency', 'Decommission an agency and its users'),
            ('delete_agencykey', 'Delete Agency\'s Cached Key'),
            ('change_agencyconfig', 'Modify agency\'s configuration'),
        )

    def __str__(self):
        return self.name

    def natural_key(self):
        return (self.identifier,)

    @property
    def organization_tenant(self):
        from bms_organization.models import Tenant

        try:
            return Tenant.objects.get(id=self.integration_id)
        except Tenant.DoesNotExist:
            return None

    @property
    def sorted_configcontext_set(self):
        return self.configcontext_set.order_by(
            'config_scheme__config_option__config_entity__name', 'scope', '-updated_at'
        ).select_related(
            'config_scheme',
            'config_scheme__config_option',
            'config_scheme__config_option__config_entity',
        )

    @property
    def report_set(self):
        """Returns the report submissions excluding those that don't have workflows"""
        return self.form_set.filter(workflow__isnull=False)

    @property
    def get_orphaned_forms(self):
        from etl_database_schema.apps.bms.models.form import Form

        """ Gets a custom list of the forms that have been orphaned """
        query = '''
            SELECT DISTINCT on (type, form_id) type as number, form_id as id, created_at, agency_id
            FROM (
            SELECT substring(al.title, 15) as type,
                al.data->>'formId' as form_id, al.created_at, benchmark_user.agency_id
                from notification al
                INNER JOIN benchmark_user on al.user_id = benchmark_user.id
                inner join agency on agency.id = benchmark_user.agency_id
                LEFT JOIN form on al.data->>'formId' = form.id::varchar
            WHERE form.id is null and action = 'submit-report' and user_id::varchar = al.data->>'submitterId'
                AND benchmark_user.agency_id = %s
            ORDER BY substring(al.title, 15), created_at) A
        '''
        return Form.objects.raw(query, params=[self.id])

    @property
    def orphaned_snapshots(self):
        """Snapshots that no longer have a template"""
        subquery = '''entity_id::varchar in (SELECT form_id FROM (
            SELECT distinct on(substring(al.title, 15), al.data->>'formId') substring(al.title, 15) as type,
                al.data->>'formId' as form_id, al.created_at
            from notification al
                INNER JOIN benchmark_user on al.user_id = benchmark_user.id
                LEFT JOIN form on al.data->>'formId' = form.id::varchar
            WHERE form.id is null and action = 'submit-report' and user_id::varchar = al.data->>'submitterId'
                AND benchmark_user.agency_id = %s ) as A )
        '''
        return Snapshot.objects.filter(entity_type='Form').extra(
            where=[subquery], params=[self.id]
        )

    @property
    def is_training_enabled(self):
        """If training context has been set, returns its value, otherwise false"""
        context = self.get_training_enable_context()
        if context:
            option_value = context.configoptionvalue_set().first()
            return bool(option_value.value)
        else:
            return False

    @transaction.atomic(using='bms')
    def decommission(self, prefix="DECOMMISSIONED__"):
        """Decommissioning an agency renames the agency AND its users

        This is better than deleting data. And it allows us to free up an agency's namespace in case it needs reuse
        """
        dt = datetime.datetime.now().strftime("%d%b%YH%H").upper()
        pre = f'{prefix}{dt}__'
        self.name = f'{pre}{self.name}'
        self.identifier = f'{pre}{self.identifier}'
        self.subdomain = f'{pre} {self.subdomain}'
        self.save()
        for user in self.benchmarkuser_set.all():
            user.decommission(prefix=pre)

    @property
    def is_decommissioned(self):
        return str(self.name).startswith('DECOMMISSIONED__')

    @transaction.atomic(using='bms')
    def clean_rank_names(self, clean_descriptions=True):
        """Strips extra text from agency ranks

        BMS allows imports with extra spaces. This can cause problems
        """
        log.info("Cleaning %s ranks for %s", self.rank_set.count(), self)
        changed = []
        for rank in self.rank_set.all():
            log.debug("Cleaning rank %s", rank)
            new = rank.name.strip()
            if new != rank.name:
                rank.name = new
                if clean_descriptions:
                    rank.description = rank.description.strip()
                rank.save()
                changed.append(rank)

        if len(changed) > 0:
            log.info("Clearing cache for %s post cleaning of ranks", self)
            self.delete_cached_config()
        log.info("%s ranks were cleaned", len(changed))
        return changed

    @transaction.atomic(using='bms')
    def clean_user_titles(self):
        """Strips extra text from user titles

        BMS allows imports with extra spaces. This can cause problems
        """
        log.info("Cleaning %s titles for %s", self.benchmarkuser_set.count(), self)
        changed = []
        for user in self.benchmarkuser_set.all():
            if user.title:
                log.debug("Cleaning user %s", user)
                new = user.title.strip()
                if new != user.title:
                    user.title = new
                    user.save()
                    changed.append(new)
        log.info("%s titles were cleaned", len(changed))
        return changed

    @transaction.atomic(using='bms')
    def get_or_create_org_entities(self):
        """Create the org agency and entity if it doesn't exist"""
        from bms_organization import models as org_models

        log.info(f"Creating agency/org entities for {self}")
        org_agency, a_created = org_models.AgencyEntity.objects.get_or_create(
            bms_agency=self, defaults={'name': self.name}
        )
        org_entity, o_created = org_models.OrgEntity.objects.get_or_create(
            agency_entity=org_agency, is_agency_top=True, defaults={'name': self.name}
        )
        return org_agency, org_entity, a_created, o_created

    @transaction.atomic(using='bms')
    def get_or_create_jurisdiction(self, municipality_name):
        """Adds municipal jurisdiction for this agency"""
        from bms_organization import models as org_models

        log.info(f"Creating municipal jurisdiction %s for %s", municipality_name, self)
        mjur, created = org_models.MunicipalJurisdiction.objects.get_or_create(
            municipality=municipality_name, prosecuting_agency=self
        )
        return mjur, created

    def get_training_enable_context(self):
        """Get the current training-enable contexts

        If there are multiple, BMS looks at the most recently created.
        Hacky, I know.
        """
        return self.get_context_for('training', 'enable')

    def get_context_for(
        self, entity_name, option_name, scope='daily-observation-report'
    ):
        """Get a configuration context based on criteria specified.

        If more than one context is found will return the most up-to-date context
        """
        contexts = self.configcontext_set.filter(
            config_option__config_entity__name=entity_name,
            config_option__name=option_name,
            scope=scope,
        ).order_by('-created_at')

        n_contexts = contexts.count()
        if n_contexts > 1:
            log.warning(
                f"{self} has multiple contexts for entity {entity_name} and option {option_name}. Expecting one, got {n_contexts}"
            )
        if n_contexts:
            return contexts.first()

    def get_event_context_for(self, event_name, template_type_value):
        """Get the most recent event configuration context for a given event and template type.

        (In this type of config, only the most recent matters and there could be multiple)
        """
        context = (
            self.eventconfigurationcontext_set.filter(
                event_configuration_scheme__event__name=event_name,
                event_configuration_scheme__ecstt__template_type__value=template_type_value,
            )
            .order_by('-id')
            .first()
        )

        return context

    def disable_training_config(self):
        """Disable training if it exists. Otherwise create it."""
        log.info(f"Disabling {self}'s training-enable context (If it exists)")
        context = self.get_training_enable_context()
        if context:
            option_value = context.configoptionvalue_set().first()

            log.debug(f"{self} context={context} option_value={option_value}")
            option_value.value = False
            option_value.save()
        else:
            log.info(f"{self} does not have a training context to disable. Creating")

            context, option_value = self.create_training_config_set(
                is_training_enabled=False
            )

    def enable_training_config(self):
        """Enable training if it exists. Otherwise create it."""
        log.info(f"Enabling {self}'s training-enable context ")
        context = self.get_training_enable_context()
        if context:
            option_value = context.configoptionvalue_set().first()

            log.debug(f"{self} context={context} option_value={option_value}")
            option_value.value = True
            option_value.save()
        else:
            # Context doesn't exist, so we have to create the context and the option
            # which also means we have to create the scheme
            # This could probably be abstracted/refactored...
            log.info(
                f"{self} doesn't have a training-enable context. Creating scheme, context, and option"
            )
            context, option_value = self.create_training_config_set(
                is_training_enabled=True
            )

    @transaction.atomic(using='bms')
    def _create_config_set(
        self,
        value=True,
        scope='daily-observation-report',
        entity_name='training',
        option_name='enable',
        use_existing_scheme=False,
    ):
        """Creates a training-enable configuration for the agency

        Making this a "private" method because it shouldn't be called directly. It
        assumes all previous checks for the existence of the schems have already been done

        :param value: True if the config is supposed to be enabled
        """
        log.info(f"Creating config_set for {self}: {entity_name} - {option_name}")

        config_scope = scope
        option = ConfigOption.objects.get(
            name=option_name, config_entity__name=entity_name
        )
        # This config scheme is so dumb. It doesn't explicitly reference the agency even though
        # it is almost always tied to an agency. As a result an agency can have multiple
        # overlapping schemes. To make things a little bit worse, some configs require to have only
        # one active scheme, so we need to support this use case when building a config as well
        scheme = None
        # Attempt to use an existing scheme
        if use_existing_scheme:
            context = (
                self.configcontext_set.filter(
                    config_option__config_entity__name=entity_name,
                    config_option__name=option_name,
                )
                .order_by('-id')
                .first()
            )
            if context:
                scheme = context.config_scheme

        # If there's no existing scheme, or if we wanted to create from the begining
        if scheme is None:
            scheme = ConfigScheme.objects.create(config_option=option, system=False)

        option_value, updated = ConfigOptionValue.objects.update_or_create(
            config_scheme=scheme, scope=config_scope, defaults={'value': value}
        )
        context, updated = ConfigContext.objects.get_or_create(
            agency=self,
            config_option=option,
            config_scheme=scheme,
            enable=True,
            scope=config_scope,
        )
        log.debug(
            f"Updated configs for {self}: {option_value}, {context} (scope={scope}, entity={entity_name}, option={option_name}"
        )
        return context, option_value

    def create_training_config_set(self, is_training_enabled=True):
        """Helper function for DRY calling of create_config_set for training enablement
        :param is_training_enabled: True if the config is supposed to be enabled
        """
        # Scope is temporarily daily-observation-report, we'll have to change this after BTD-144
        return self._create_config_set(
            value=is_training_enabled,
            scope='daily-observation-report',
            entity_name='training',
            option_name='enable',
        )

    def create_link_config(self, base, target, link_option, clear_cache=True):
        """Create a configuration entry that links two templates or its fields

        :param base: The Template Type to Link From
        :param target: The Target Template Type to link to
        link_option: targetFormType links two templates.
                     formKeyMappings, links the fields between templates
        """
        log.info(
            "Creating %s Link config %s to %s for %s", link_option, base, target, self
        )

        # When linking templates, the target is a template_type.value array.
        # When linking fields, it is a JSON field mapping
        target_value = target
        if link_option == ConfigOptionValue.LINK_TEMPLATE:
            target_value = [target]

        result = self._create_config_set(
            value=target_value,
            scope=base,
            entity_name='link',
            option_name=link_option,
            use_existing_scheme=True,
        )

        # Last, clear the config cache
        if clear_cache:
            self.delete_cached_config()

        return result

    def create_template_config(self, template_type, config_option, details):
        """Helper for DRY calling to create a new template config

        :param template_type: The template type to configure
        :param option_name: the option to add
        :param details: Defines the actual configuration value
        """
        return self._create_config_set(
            value=details,
            scope=template_type.value,
            entity_name='template',
            option_name=config_option.name,
        )

    def configcontext_by_entity(self):
        """Groups the configuration contexts by their entity"""
        results = []
        entity_results = []
        prev_entity = None
        for cc in self.sorted_configcontext_set.all():
            if prev_entity is None:
                pass
            elif prev_entity != cc.config_scheme.config_option.config_entity:
                results.append(
                    {'config_entity': prev_entity, 'config_contexts': entity_results}
                )
                entity_results = []
            entity_results.append(cc)
            prev_entity = cc.config_scheme.config_option.config_entity
        results.append(
            {'config_entity': prev_entity, 'config_contexts': entity_results}
        )
        return results

    @property
    def bms_cache(self):
        if getattr(self, '_bms_cache', None) is None:
            self._bms_cache = bms_cache.BMSCache()
        return self._bms_cache

    def get_cached_keys(self):
        """Gets keys cached in BMS"""
        return self.bms_cache.agency_keys(self.identifier)

    def get_cached_keys_forms(self):
        """Gets keys of forms cached in BMS"""
        return self.bms_cache.agency_form_keys(self.identifier)

    def get_cached_keys_forms_new_workflow(self):
        """Gets keys of forms new workflow cached in BMS"""
        return self.bms_cache.agency_form_new_workflow_keys(self.identifier)

    def get_cached_keys_config(self):
        """Gets keys of config cached in BMS"""
        return self.bms_cache.agency_config_keys(self.identifier)

    def get_cached_keys_templates(self):
        """Gets keys of templates cached in BMS"""
        return self.bms_cache.agency_template_keys(self.identifier)

    def delete_key(self, key, confirm=True):
        """Deletes a key. Confirms that it is part of the agency first"""
        if confirm and key in self.get_cached_keys():
            return self.bms_cache.delete(key)
        else:
            return False

    def delete_cached_config(self):
        """Removes the configuration keys"""
        if settings.BMS_CACHE_ENABLED:
            config_keys = self.get_cached_keys_config()
            for key in config_keys:
                self.delete_key(key)
        else:
            log.warning("Cache not enabled in settings. Deleting keys not possible.")

    @transaction.atomic(using='bms')
    def link_agency_templates(self, from_template, to_template):
        """Creates a link configuration between from_template and to_template.
        The process adds a new transition to each from_template's workflows and then they are sealed
        raises LinkingError if something fails
        """
        log.info('Attempting to create workflow linkage')
        # Create the workflows
        self.create_linked_workflows(from_template, to_template)

        log.info('Attempting to create link configuration')
        # Create link config for templates
        from_template.link_to(self, to_template)

        # Last, clear the config cache
        self.delete_cached_config()

    @transaction.atomic(using='bms')
    def repair_config_links(self, from_template, to_template):
        """Attempts to re-insert the link configuration for a template.
        Raises a LinkingError if something fails
        """
        log.info('Attempting to refresh the link configuration for templates')

        # Refresh link configuration for templates
        from_template.link_to(self, to_template)

        # Last, clear the config cache
        self.delete_cached_config()

    @transaction.atomic(using='bms')
    def delink_agency_templates(
        self, from_template, agency_id, to_state_name='investigate-incident'
    ):
        """Delink templates that are already joined by link_agency_templates.
        The de-link process consist in the followings steps:
        1-Get all transitions that are in the state = 'investigate-incident'
        2-For each transition: delete the state by id ( transition.to_state ), delete the action by id ( transition.action_id ), delete the transition by id, update workflow ( sealed = false )
        3-Remove from json config_option_value.value the template type which is related to from_template and remove the state 'investigate-incident'
        """
        delinked_transitions = self.create_delinked_workflows(
            from_template, agency_id, to_state_name
        )

        # Last, clear the config cache
        self.delete_cached_config()

        return delinked_transitions

    def create_delinked_workflows(self, from_template, agency_id, to_state_name):
        log.debug(
            'create_delinked_workflows from_template %s agency_id %s',
            from_template,
            agency_id,
        )
        # Get always most recent version
        from_template_version = (
            from_template.templateversion_set.filter(agency=self)
            .order_by('-id')
            .first()
        )

        transitions_investigate_incident = None

        # Get Workflows
        workflow_ids = TemplateWorkflow.objects.filter(
            template_version=from_template_version
        ).values_list('workflow_id', flat=True)

        # Get Transitions
        transitions_investigate_incident = Transition.objects.filter(
            workflow_id__in=workflow_ids, to_state__name=to_state_name
        )

        self.delinked_validate(
            from_template, from_template_version, transitions_investigate_incident
        )

        for transition in transitions_investigate_incident:
            # t.to_state_id
            self.delinked_delete_state(transition)
            # t.action_id
            self.delinked_delete_action(transition)
            # t.id
            self.delinked_delete_transition(transition)
            # t.workflow_id
            self.delinked_update_workflow_to_unsealed(transition)

        self.delinked_update_event(from_template, agency_id)

        delinked_transitions = str(transitions_investigate_incident)

        return delinked_transitions

    def delinked_validate(
        self, from_template, from_template_version, transitions_investigate_incident
    ):
        transitions_investigate_incidents_count = None

        if not from_template:
            log.debug(
                'Cannot de-link templates: Template A is not defined, please validate'
            )
            raise LinkingError(
                'Cannot de-link templates: Template A is not defined, please validate'
            )
        if not from_template_version:
            log.debug(
                'delinked_validate Cannot de-link templates: %s is not linked, please validate',
                from_template,
            )
            raise LinkingError(
                'Cannot de-link templates: Template A is not linked, please validate'
            )

        transitions_investigate_incidents_count = (
            transitions_investigate_incident.count()
        )

        log.debug(
            'delinked_validate f"Cannot de-link templates: %s is not linked, please validate, %s',
            from_template,
            transitions_investigate_incidents_count,
        )
        if (
            not transitions_investigate_incidents_count
            or transitions_investigate_incidents_count == 0
        ):
            raise LinkingError(
                'Cannot de-link templates: Template A is not linked, please validate'
            )

    def delinked_delete_state(self, transition):
        log.debug('delinked_delete_state id %s', transition.to_state.id)
        transition.to_state.delete()

    def delinked_delete_action(self, transition):
        log.debug('delinked_delete_action id %s', transition.action.id)
        transition.action.delete()

    def delinked_delete_transition(self, transition):
        log.debug('delinked_delete_transition id %s', transition.id)
        transition.delete()

    def delinked_update_workflow_to_unsealed(self, transition):
        log.debug('delinked_update_workflow_to_unsealed id %s', transition.workflow)
        workflow = transition.workflow
        workflow.sealed = False
        workflow.save()

    def delinked_update_event(self, from_template, agency_id):
        json_event = None

        cov = ConfigOptionValue.objects.raw(
            """select cov.* from config_option_value cov
                                    where config_scheme_id in(
                                        select distinct on (config_option_id, scope) config_scheme_id
                                        from config_context
                                        where (agency_id = %s and scope = 'POST_SUBMIT' )
                                        order by config_option_id, scope, updated_at desc
                                    )and cov.scope = 'POST_SUBMIT'
               """,
            [agency_id],
        )[0]

        json_event = cov.value

        from_template_str = str(from_template).lower()
        templateTypes_filtered_list = []
        states_filtered_list = []

        for obj in json_event:
            if obj.get('name') == 'createForm':
                templateTypes = obj.get('templateTypes')
                states = obj.get('states')
                if templateTypes is not None:
                    for templateType in templateTypes:
                        if templateType is not None and not templateType.startswith(
                            from_template_str
                        ):
                            templateTypes_filtered_list.append(templateType)
                if states is not None:
                    for state in states:
                        if state != 'investigate-incident':
                            states_filtered_list.append(state)
                obj["templateTypes"] = templateTypes_filtered_list
                obj["states"] = states_filtered_list
                log.info("delinked_update_event createForm updated %s", obj)

        cov.value = json_event
        cov.save()

    def create_linked_workflows(self, from_template, to_template):
        """Create the workflow transitions that BMS needs for linking

        For forms to generate linking actions, they need appropriate workflow states that BMS expects
        """
        # Get always most recent version

        from_template_version = (
            from_template.templateversion_set.filter(agency=self)
            .order_by('-id')
            .first()
        )

        log.info("from_template_version {}".format(from_template_version.id))

        to_template_version = (
            to_template.templateversion_set.filter(agency=self).order_by('-id').first()
        )

        from_template_workflows = from_template_version.templateworkflow_set.all()
        to_template_workflows = to_template_version.templateworkflow_set.all()

        # Verify if both templates have workflows
        if not from_template_workflows:
            raise LinkingError(
                f"Cannot link templates: 'Template A' doesn't have worflows"
            )

        if not to_template_workflows:
            raise LinkingError(
                f"Cannot link templates: 'Template B' doesn't have worflows"
            )

        # Verify if any of the workflows are already sealed. If they are, we cannot touch them
        are_workflows_sealed = any(
            [tw.workflow.sealed for tw in from_template_workflows]
        )

        if are_workflows_sealed:
            raise LinkingError(
                f"Cannot link templates: One or more 'Template A' workflows are sealed"
            )

        targets = [tv.workflow for tv in to_template_workflows]

        # add investigation transition
        for template_workflow in from_template_workflows:
            workflow = template_workflow.workflow
            transition = workflow.add_final_transition(
                targets,
                self,
                final_state_value='investigate-incident',
                action_name='Investigate Incident',
            )
            state = transition.to_state

            # Add event handlers for template
            from_template.template_type.add_event_handler(
                self, state, ['createForm', 'notifyUsers']
            )


class AgencyNextGen(models.Model):
    name = models.CharField(max_length=128)
    identifier = models.CharField(max_length=255, blank=True, null=True)
    logo = models.CharField(max_length=255, blank=True, null=True)
    timezone = models.CharField(max_length=255, blank=True, null=True)
    address = models.CharField(max_length=255)
    subdomain = models.CharField(max_length=255)
    izenda_tenant_id = models.CharField(max_length=255, blank=True, null=True)
    active = models.BooleanField(null=False, blank=False, default=True)
    lms_integration_enabled = models.BooleanField(
        null=False, blank=False, default=False
    )
    integration_id = models.UUIDField(blank=True, null=True)
    lms_tenant_root_only = models.BooleanField(null=False, blank=False, default=False)

    class Meta:
        managed = False
        db_table = 'agency'
