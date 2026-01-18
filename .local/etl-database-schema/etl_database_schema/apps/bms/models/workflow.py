from etl_database_schema.apps.bms.models.errors import WorkflowError
import logging

from django.utils.text import slugify
from django.db import models

from etl_database_schema.apps.bms.models.notification import Notification

log = logging.getLogger(__name__)


class StateGroup(models.Model):
    state = models.ForeignKey('State', models.DO_NOTHING)
    group = models.ForeignKey('Group', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'group_state'


class Action(models.Model):
    REASSIGN_VALUE = 'reassign'  # Special Reassignment value
    REOPEN_VALUE = 'reopen'
    INVESTIGATE = 'Investigate Incident'

    workflow = models.ForeignKey('Workflow', models.DO_NOTHING)
    name = models.CharField(max_length=128)
    value = models.CharField(max_length=512)
    created_at = models.DateTimeField(blank=True, null=True, auto_now_add=True)
    updated_at = models.DateTimeField(blank=True, null=True, auto_now=True)

    class Meta:
        managed = False
        db_table = 'action'

    def __str__(self):
        return '{}'.format(self.name)


class ActionActionGroup(models.Model):
    action = models.ForeignKey(Action, models.DO_NOTHING)
    action_group = models.ForeignKey('ActionGroup', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'action_action_group'


class ActionGroup(models.Model):
    priority = models.IntegerField()
    name = models.CharField(max_length=128)
    value = models.CharField(max_length=255)
    workflow = models.ForeignKey('Workflow', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'action_group'


class AgencyWorkflow(models.Model):
    agency = models.ForeignKey('Agency', models.DO_NOTHING)
    workflow = models.ForeignKey('Workflow', models.DO_NOTHING)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'agency_workflow'


class WorkflowLabel(models.Model):
    CLOSED_WORKFLOW_SLUG = 'COMPLETED'
    IN_REVIEW_SLUG = 'IN_REVIEW'

    agency_workflow = models.ForeignKey(AgencyWorkflow, models.DO_NOTHING)
    slug = models.CharField(max_length=255)
    value = models.CharField(max_length=255)
    order = models.IntegerField(blank=True, null=True)
    is_default = models.BooleanField(blank=True, null=True)
    is_take_action = models.BooleanField(blank=True, null=True)
    is_draft = models.BooleanField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'workflow_label'

    def __str__(self):
        return '{}-{}'.format(self.id, self.slug)


class State(models.Model):
    workflow = models.ForeignKey('Workflow', models.DO_NOTHING)
    src = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=128)
    value = models.CharField(max_length=255)
    order = models.IntegerField()
    is_req_more_info = models.BooleanField()
    is_entry_point = models.BooleanField()
    include_submitter = models.BooleanField(blank=True, null=True)
    is_final = models.BooleanField()
    created_at = models.DateTimeField(blank=True, null=True, auto_now_add=True)
    updated_at = models.DateTimeField(blank=True, null=True, auto_now=True)
    workflow_label = models.ForeignKey(
        'WorkflowLabel', models.DO_NOTHING, blank=True, null=True
    )
    note_template = models.ForeignKey(
        'Template', models.DO_NOTHING, blank=True, null=True
    )
    include_trainee = models.BooleanField(blank=True, null=True)
    groups = models.ManyToManyField('Group', through='StateGroup')

    class Meta:
        managed = False
        db_table = 'state'

    def __str__(self):
        return self.name


class Transition(models.Model):
    action = models.ForeignKey(Action, models.DO_NOTHING)
    from_state = models.ForeignKey(State, models.DO_NOTHING)
    to_state = models.ForeignKey(
        State, models.DO_NOTHING, related_name='transition_to_set'
    )
    workflow = models.ForeignKey('Workflow', models.DO_NOTHING)
    priority = models.IntegerField()
    only_initial = models.BooleanField()
    is_lockable = models.BooleanField()
    is_choosable = models.BooleanField()
    is_redefinible = models.BooleanField()
    require_notes = models.BooleanField()
    created_at = models.DateTimeField(blank=True, null=True, auto_now_add=True)
    updated_at = models.DateTimeField(blank=True, null=True, auto_now=True)
    reviewer_label = models.CharField(max_length=255, blank=True, null=True)
    timeline_message = models.CharField(max_length=255, blank=True, null=True)
    requires_evidence = models.BooleanField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'transition'

    def __str__(self):
        return '{}-{}-{}'.format(self.from_state_id, self.action, self.to_state_id)


class TransitionCondition(models.Model):
    transition = models.ForeignKey(Transition, models.DO_NOTHING)
    rule = models.TextField()  # This field type is a guess.
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'transition_condition'


class Workflow(models.Model):
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    self_service_created = models.BooleanField()
    sealed = models.BooleanField(null=True)

    class Meta:
        managed = False
        db_table = 'workflow'

    def __str__(self):
        return '{} ({})'.format(self.name, self.id)

    @property
    def sorted_transition_set(self):
        return self.transition_set.order_by(
            'only_initial', 'from_state__order', 'from_state_id', 'action_id'
        ).select_related('from_state', 'to_state', 'action')

    @property
    def closed_state(self):
        """The state associated with this workflow that makes it closed/completed"""
        if getattr(self, '_closed_state', None) is None:
            try:
                self._closed_state = self.state_set.get(value='closed', is_final=True)
            except State.DoesNotExist as e:
                msg = f"Workflow ({self}) doesn't have a closed state"
                log.error(msg)
                raise State.DoesNotExist(msg) from None

            except State.MultipleObjectsReturned as e:
                log.error(f"Workflow ({self}) has multiple closed states")
                raise
        return self._closed_state

    @property
    def initial_transitions(self):
        """The transitions that represent the beginning point of the workflow"""
        return self.transition_set.all().filter(from_state__is_entry_point=True)

    @property
    def workflowlabel_set(self):
        return WorkflowLabel.objects.filter(
            agency_workflow__workflow=self
        ).select_related('agency_workflow', 'agency_workflow__agency')

    def simplify_workflow_submit_to_close(self, dry_run=False):
        """Converts this workflow into the simpliest possible: draft->submit->close

        Using the closed state, replace all the initial transitions
        """
        log.info(f"Simplifying workflow {self}: draft->submit->close")
        final_state = self.closed_state
        log.debug(f"Using {self} final state to {final_state}")
        changed = []
        for transition in self.initial_transitions:
            if transition.to_state != self.closed_state:
                orig_state = transition.from_state
                log.info(
                    f"Transition {transition} replacing {orig_state} with {final_state} "
                )
                transition.to_state = final_state
                if not dry_run:
                    transition.save()
                changed.append(transition)
            else:
                log.info(
                    f"Transition already points to {final_state}. No change needed."
                )

        log.info(
            "Unpruned transitions: {}".format(
                self.transition_set.exclude(id__in=[c.id for c in changed])
            )
        )
        return changed

    def get_initial_submission_group(self):
        """ This will support old-world workflows as well """
        states = self.state_set.filter(is_entry_point=True)
        groups = []
        for state in states:
            groups.append(state.groups.all())

        # flat the list
        return [val for sub in groups for val in sub]

    def get_penultimate_states(self, return_first=False):
        """ Return the states that come right before the final state in the workflow

        :param return_first: Boolean. If True, return just one state instead of the queryset
        """
        states = None
        transitions = self.transition_set.filter(to_state__is_final=True)
        states = State.objects.filter(transition__in=transitions)
        log.debug("Penultimate states: %s", states)
        if return_first:
            return states.first()
        return states

    # @transaction.atomic(using='bms')
    def add_final_transition(
        self,
        targets,
        agency,
        final_state_value='investigate-incident',
        end_label_slug='COMPLETED',
        require_notes=True,
        seal=True,
        action_name='Investigate Incident',
    ):
        """ Adds a new transition at the end of the workflow

        Transition will point to all initial groups in targets
        After creating this transition, workflow should be sealed

        :param targets: The user group that are part of the final state
        :param agency: The agency that the transition should associate to
        :param new_end_state_value: Default='investigage-incident'. The value that should be given to the final state.
        :param end_label_slug: Default='COMPLETED'. THe slug that identifies the final workflow label
        :param require_notes: Default=True. Whether the final state should require notes
        :param seal: Default True. Sealing a workflow prevents self-service from editing it.
        :param action_name: Default ACTION.INVESTIGATE. The name the action should receive

        TODO The workflow is basically a linked-list of transitions. As such, we should add
            standard linked list functionality for appending, prepending, inserting and removing
            transitions from the linked-list.
        """

        # Get prev to last state
        prev_to_last_state = self.get_penultimate_states(return_first=True)

        # get initial groups from targets
        groups = [workflow.get_initial_submission_group() for workflow in targets]
        groups = [val for sub in groups for val in sub]
        # create action
        action, created = Action.objects.get_or_create(
            workflow=self, value=slugify(action_name), defaults={'name': action_name}
        )
        if created:
            log.info(
                "Created new %s action for workflow %s: %s", action_name, self, action
            )

        # create state
        labels = WorkflowLabel.objects.filter(
            agency_workflow__workflow=self, agency_workflow__agency=agency
        )
        label = labels.filter(slug=end_label_slug).first()
        state, created = State.objects.get_or_create(
            workflow=self,
            value=final_state_value,
            defaults={
                'src': None,
                'name': final_state_value,
                'order': 100,
                'is_req_more_info': False,
                'is_entry_point': False,
                'include_submitter': False,
                'is_final': True,
                'note_template': None,
                'workflow_label': label,
                'include_trainee': False,
            },
        )
        if created:
            log.info("Created new state for workflow %s: %s", self, state)

            # relate groups to state
            state.groups.set(groups)
        else:
            log.warning("Workflow state already existed. Values might not all match")

        # create transition
        transition, created = Transition.objects.get_or_create(
            action=action,
            from_state=prev_to_last_state,
            to_state=state,
            workflow=self,
            defaults={
                'priority': 100,
                'only_initial': False,
                'is_lockable': False,
                'is_redefinible': True,
                'is_choosable': True,
                'require_notes': require_notes,
                'reviewer_label': '',
                'timeline_message': None,
                'requires_evidence': False,
            },
        )
        if created:
            log.info("Created new transition for workflow %s: %s", self, state)

        if seal:
            self.seal()

        # Finished adding transition
        return transition

    def seal(self):
        self.sealed = True
        self.save(force_update=True)

    def get_investigate_incident_state(self):
        """This method returns the state that corresponds to investigate incident.
        If a workflow is sealed and has a investigate incident state, it means it has been setup
        to be used as a linked report, that will trigger the creation of a second report.
        """
        state_value = 'investigate-incident'
        try:
            investigate_incident_state = self.state_set.get(value=state_value)
        except State.DoesNotExist as e:
            msg = f"Workflow ({self}) doesn't have a {state_value} state"
            log.error(msg)
            raise State.DoesNotExist(msg) from None

        except State.MultipleObjectsReturned as e:
            msg = f"Workflow ({self}) has multiple {state_value} states"
            log.error(msg)
            raise State.MultipleObjectsReturned(msg) from None

        return investigate_incident_state


class MovementManager(models.Manager):
    """ Defers the content field"""

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related(
                'transition',
                'from_user',
                'to_user',
                'transition__from_state',
                'transition__to_state',
                'transition__action',
                'form',
            )
            .order_by('-id')
        )


class Movement(models.Model):
    created_at = models.DateTimeField(blank=True, null=True, auto_now_add=True)
    updated_at = models.DateTimeField(blank=True, null=True, auto_now=True)
    form = models.ForeignKey('Form', models.DO_NOTHING, blank=True, null=True)
    transition = models.ForeignKey('Transition', models.PROTECT, blank=True, null=True)
    from_user = models.ForeignKey(
        'BenchmarkUser', models.PROTECT, blank=True, null=True
    )
    to_user = models.ForeignKey(
        'BenchmarkUser',
        models.PROTECT,
        blank=True,
        null=True,
        related_name='movement_to_set',
    )
    note = models.ForeignKey(
        'Form', models.PROTECT, blank=True, null=True, related_name='movement_note_set'
    )
    objects = MovementManager()

    class Meta:
        managed = False
        db_table = 'movement'

        permissions = (('add_movementnotification', 'Add Notification for Movements'),)

    @property
    def is_extraneous(self):
        """ Movements sometimes get created as extra movements mistakenly by BMS. This defines whether they can be removed """

        in_review = (
            True
            if self.form.workflow_label and self.form.workflow_label.slug == 'IN_REVIEW'
            else False
        )
        unassigned = True if self.to_user is None else False
        if in_review and unassigned:
            movements = (
                self.form.movement_set.all()
                .exclude(id=self.id)
                .order_by('-created_at', '-id')
            )
            penultimate = movements.first()
            non_singular_movement = (
                True if self.form.movement_set.all().count() > 1 else None
            )
            matching_user = (
                True
                if penultimate and penultimate.from_user == self.from_user
                else False
            )
        else:
            non_singular_movement = False
            matching_user = False

        if in_review and unassigned and non_singular_movement and matching_user:
            log.debug(
                "This movement may be extraneous. Form is in review but this isn't assigned to anyone"
            )
            return True
        else:
            return False

    def serialize(self):
        from django.core import serializers

        return serializers.serialize('json', Movement.objects.filter(id=self.id))

    def notify_user(
        self,
        notification_text="Please review {form_name}",
        action_item=True,
        action='submit-report',
    ):
        """Notifies the to_user on this movement by inserting an entry into the notification table

        WHY? Well... we have a problem with Kalamazoo where a user was not notified that
        they were assigned a report. This has also occured four other times for two agencies.
        In case this occurs again, be prepared to make this happen.
        """
        to_bms_user = self.to_user
        form_name = "{template_name} {form_number}".format(
            template_name=self.form.template_version.template.name,
            form_number=self.form.number,
        )

        # Notify the new user
        log.info(f"Notifying  {to_bms_user} that they now have a report {form_name}")
        notification = Notification(
            user=to_bms_user,
            title=notification_text.format(form_name=form_name),
            body=notification_text.format(form_name=form_name),
            data={"formId": self.form.id, "submitterId": self.form.submitter_id},
            action=action,
            new=True,
            action_item=action_item,
            is_dismissable=False,
            type="default",
        )
        notification.save()
        return notification
