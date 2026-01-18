import logging

from django.db import models
from django.db import transaction

from etl_database_schema.apps.bms.models.json import JSONNonBField
from etl_database_schema.apps.bms.models.action_log import ActionLog
from etl_database_schema.apps.bms.models.notification import Notification
from etl_database_schema.apps.bms.models.errors import WorkflowError, FormError
from etl_database_schema.apps.bms.models.workflow import WorkflowLabel, Action, Movement

log = logging.getLogger(__name__)


class FormManager(models.Manager):
    """Selects common related values"""

    def get_queryset(self):
        return super().get_queryset().select_related('agency', 'workflow_label')


class Form(models.Model):
    agency = models.ForeignKey('Agency', models.CASCADE, blank=True, null=True)
    data = models.TextField(blank=True, null=True)
    number = models.CharField(max_length=255, blank=True, null=True)
    participant_statuses = models.JSONField(
        blank=True, null=True
    )  # This field type is a guess.
    last_reviewed_at = models.DateTimeField(blank=True, null=True)
    last_draft_at = models.DateTimeField(blank=True, null=True)
    submitted_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True, auto_now=True)
    submitter = models.ForeignKey(
        'BenchmarkUser', models.PROTECT, blank=True, null=True
    )
    workflow = models.ForeignKey('Workflow', models.PROTECT, blank=True, null=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(blank=True, null=True)
    time_tracking = models.ForeignKey(
        'TimeTracking', models.DO_NOTHING, blank=True, null=True
    )
    workflow_label = models.ForeignKey(
        'WorkflowLabel', models.PROTECT, blank=True, null=True
    )
    template_version = models.ForeignKey('TemplateVersion', models.PROTECT)
    on_behalf = JSONNonBField(blank=True, null=True)
    organizational_unit_id = models.UUIDField(max_length=255, blank=True, null=True)
    hierarchy_key = models.CharField(max_length=255, blank=True, null=True)
    locked = models.BooleanField(blank=True, null=True)
    trainee_name = models.IntegerField(blank=True, null=True)
    note_version_id = models.IntegerField(blank=True, null=True)
    external_id = models.UUIDField(blank=True, null=True)
    objects = FormManager()

    class Meta:
        managed = False
        db_table = 'form'
        permissions = (
            ('reassign_form', 'Reassign Form'),
            ('reopen_form', 'Re-open Form'),
        )

    def __str__(self):
        return '{} ({})'.format(self.number, self.id)

    def get_absolute_bms_url(self):
        """Special function to show multi-database url"""
        from django.urls import reverse

        return reverse(
            'agency-form-detail', kwargs={'pk': self.id, 'agency_id': self.agency_id}
        )

    @property
    def actionlogs(self):
        al = ActionLog.objects.extra(
            where=["action_data ->> 'formId'=%s "], params=[str(self.id)]
        )
        return al.select_related('user')

    @property
    def notifications(self):
        return (
            Notification.objects.extra(
                where=['data ->> \'formId\' = %s'], params=[str(self.id)]
            )
            .order_by('-created_at', '-id')
            .select_related('user')
        )

    @property
    def last_movement(self):
        """Returns the last movement that occurred for this form"""
        m = self.movement_set.order_by('-id')
        if m.count() > 0:
            return m[0]

    @property
    def last_form_status_history(self):
        """Returns the last form status history that occurred for this form"""
        fsh = self.form_status_history_form.order_by('-id')
        if fsh.count() > 0:
            return fsh[0]

    @property
    def current_user(self):
        """Gets the current user that needs to take action on this form"""
        last_movement = self.last_movement

        last_form_status_history = self.last_form_status_history
        if not last_movement:
            if last_form_status_history:
                return last_form_status_history.target
            return
        if not last_form_status_history:
            if last_movement:
                return last_movement.to_user
            return

        if last_movement.updated_at > last_form_status_history.updated_at:
            return last_movement.to_user
        elif last_form_status_history.updated_at >= last_movement.updated_at:
            return last_form_status_history.target

    def check_reassign_allowed(self, to_user, raise_error=True):
        """Returns True if reassignment allow. Raise Exception or returns False otherwise

        Is the form deleted? -- NotPermitted
        Is the form submitted?
            Is the form open? (in a non-closed state)
                ALLOWED
            Form closed? Reassignment not allowed
        Form in draft mode? (FUTURE)
            Reassign the owner of the form and update notifications

        raises: WorkflowError, FormError, NotImplementedError,
        """
        allowed = False
        msg = None
        err = None
        if self.is_deleted:
            msg = f"Form {self} is in a deleted state. Unable to reassign."
            err = FormError(msg)
        else:
            # Form submitted?
            if self.submitted_at:
                if not self.workflow_label:
                    msg = f"Form {self} does not have a workflow. Unable to reassign."
                    err = WorkflowError(msg)
                elif self.workflow_label.slug == WorkflowLabel.CLOSED_WORKFLOW_SLUG:
                    msg = f"Form {self} is closed. Reassignment not allowed."
                    err = WorkflowError(msg)
                else:
                    if to_user is None:
                        msg = f"Unable to reassign {self} to a null user"
                        err = FormError(msg)
                    elif to_user.agency != self.agency:
                        msg = f"Unable to reassign {self} to a user in a different agency {self.agency} != {to_user.agency}"
                        err = FormError(msg)
                    else:
                        if to_user == self.current_user:
                            msg = f"Unable to reassign {self} to {to_user}: User already associated"
                            err = FormError(msg)
                        else:
                            allowed = True

            else:
                msg = f"Functionality not yet defined for reassigning a draft report ({self})"
                err = NotImplementedError(msg)

        if msg:
            log.info(msg)
        if err and raise_error:
            raise err

        return allowed

    @transaction.atomic(using='bms')
    def reassignment_transition(self):
        """Get's a "Reassignment" transition. Creates it if it doesn't exist."""
        from django.utils.text import slugify

        workflow = self.workflow
        workflow_slug = slugify(workflow.name)
        state_slug = slugify(workflow_slug + '-1.reassign')

        # Gets a reassignment action
        action, created = self.workflow.action_set.get_or_create(
            value=Action.REASSIGN_VALUE, defaults={'name': "Reassign Report"}
        )
        if created:
            log.info(
                "Created Reassignment action on {}: {}".format(self.workflow, action)
            )

        # Get/Create a state for Reassignment.
        from_state, created = self.workflow.state_set.get_or_create(
            value=state_slug,
            defaults={
                'src': workflow_slug,
                'name': state_slug,
                'order': 100,
                'is_req_more_info': False,
                'is_entry_point': False,
                'is_final': False,
                # 'workflow_label': False,
            },
        )
        if created:
            log.info(
                "Created Reassignment from_state on {}: {}".format(
                    self.workflow, from_state
                )
            )

        # Look for a transition that goes to the current state
        transition, created = self.workflow.transition_set.get_or_create(
            action=action,
            from_state=from_state,
            to_state=self.last_movement.transition.to_state,
            defaults={
                'priority': 100,
                'only_initial': True,
                'timeline_message': 'Report was reassigned',
                'is_lockable': False,
                'is_choosable': False,
                'is_redefinible': False,
                'require_notes': False,
                'requires_evidence': False,
            },
        )
        if created:
            log.info(
                "Created Reassignment transition on {}: {}".format(
                    self.workflow, transition
                )
            )

        return transition

    @transaction.atomic(using='bms')
    def reassign(self, to_bms_user, requesting_user=None):
        """Reassigns the current owner of the form to another user

        Find the most recent movement and change the to-user, add action log, update notifications

        :param to_bms_user: The benchmark_user that the form should be reassigned to.
        :param requesting_user: The benchmark_user that requested/approved the reassignment.

        raises: NotPermitted, NotImplementedError
        returns: None
        """
        log.info(
            f"Reassignment requested for form {self} to {to_bms_user} by {requesting_user}"
        )
        self.check_reassign_allowed(to_bms_user, raise_error=True)

        transition = self.reassignment_transition()

        # Reassign
        cur_movement = self.movement_set.order_by('-id')[0]
        cur_user = self.current_user
        log.info(f"Reassigning {cur_movement} from {cur_user} to {to_bms_user}")
        movement = Movement(
            form=self,
            transition=transition,
            from_user=cur_user,
            to_user=to_bms_user,
            note=None,
        )
        movement.save()

        reassigner = requesting_user or self.submitter

        # Add an action log entry
        action_log = ActionLog(
            user=self.submitter,
            action='reassign-report',
            state='success',
            action_data={"formId": self.id, "submitterId": reassigner.id},
        )
        action_log.save()

        # Make the notifications:
        self.build_reassign_notifications(cur_user, to_bms_user)

        # DONE!

    def build_reassign_notifications(self, cur_user, to_bms_user):
        """Notify the old user and the new user of the reassignment

        If there are no existing notifications, build text manually
        """
        # Current notifications

        cur_notification = self.notifications.filter(
            user=cur_user, action_item=True
        ).first()
        if cur_notification:
            title = cur_notification.title
            body = cur_notification.body
            data = cur_notification.data
            action = cur_notification.action
            is_dismissable = cur_notification.is_dismissable
            notification_type = cur_notification.type
            ## Deactivating old notifiction
            log.info(
                f"Changing old action item to notification for {cur_user}: {cur_notification}"
            )
            cur_notification.action_item = False
            cur_notification.save()
        else:
            title = f"{self.number} is reassigned to you"
            body = f"{self.number} is reassigned to you"
            data = {"formId": self.id, "submitterId": self.submitter_id}
            action = "submit-report"
            is_dismissable = False
            notification_type = "default"

        # Notify the new user
        log.info(f"Notifying  {to_bms_user} that they now have a report")
        notification = Notification(
            user=to_bms_user,
            title=title,
            body=body,
            data=data,
            action=action,
            new=True,
            action_item=True,
            is_dismissable=is_dismissable,
            type=notification_type,
        )
        notification.save()

        # Notify old user
        log.info(
            f"Notifying  {cur_user} that the report was reassigned AWAY from them."
        )
        passive_notification = Notification(
            user=cur_user,
            title=f"{self.number} was reassigned to {to_bms_user}",
            body=f"{self.number} was reassigned to {to_bms_user}",
            data=data,
            action="report-reassigned",
            new=True,
            action_item=False,
            is_dismissable=False,
            type="default",
        )
        passive_notification.save()

        return [notification, passive_notification]

    def check_reopen_allowed(self, raise_error=True):
        """Returns True if reopening is allowed. Raise Exception or returns False otherwise

        Is the form deleted? -- NotPermitted
        Is the form submitted?
            Is the form closed?
                ALLOWED
            Form open? reopening not allowed
        Form in draft mode? (FUTURE)
            Reassign the owner of the form and update notifications

        raises: WorkflowError, FormError, NotImplementedError,
        """
        allowed = False
        msg = None
        err = None
        if self.is_deleted:
            msg = f"Form {self} is in a deleted state. Unable to reopen."
            err = FormError(msg)
        else:
            # Form submitted?
            if self.submitted_at:
                if not self.workflow_label:
                    msg = f"Form {self} does not have a workflow. Unable to reopen."
                    err = WorkflowError(msg)
                elif self.workflow_label.slug != WorkflowLabel.CLOSED_WORKFLOW_SLUG:
                    msg = f"Form {self} is not closed. Reopening not allowed."
                    err = WorkflowError(msg)
                else:
                    last_movement = self.last_movement
                    if last_movement.to_user is not None:
                        msg = f"Form {self} is assigned to a user {last_movement.to_user}. Unable to reopen."
                        err = WorkflowError(msg)
                    elif last_movement.transition.to_state.name.lower() != 'closed':
                        msg = f"Form {self} most recent movement is not closed: {last_movement.transition.to_state.name}. Unable to reopen."
                        err = WorkflowError(msg)
                    else:
                        # Maybe also check that the workflow has a previous state (eg, not going immediately back to draft?)
                        allowed = True

            else:
                msg = f"Functionality not yet defined for reopening a draft report ({self})"
                err = NotImplementedError(msg)

        if msg:
            log.info(msg)
        if err and raise_error:
            raise err

        return allowed

    @transaction.atomic(using='bms')
    def reopen_transition(self):
        """Get's a "Reopen" transition. Creates it if it doesn't exist.

        Also makes sure that there are appropriate transitions for closing or requesting more info etc
        """
        from django.utils.text import slugify

        workflow = self.workflow
        workflow_slug = slugify(workflow.name)
        state_slug = slugify(workflow_slug + '-reopened')

        # Gets a reopening action
        action, created = self.workflow.action_set.get_or_create(
            value=Action.REOPEN_VALUE, defaults={'name': "Reopen Report"}
        )
        if created:
            log.info("Created Reopen action on {}: {}".format(self.workflow, action))

        # Closed state/from state
        from_state = self.last_movement.transition.from_state
        closed_state = self.last_movement.transition.to_state

        # Get/Create a state for Reopening.
        to_state, created = self.workflow.state_set.get_or_create(
            value=state_slug,
            defaults={
                'src': workflow_slug,
                'name': state_slug,
                'order': 100,
                'is_req_more_info': False,
                'is_entry_point': False,
                'is_final': False,
                # 'workflow_label': False,
            },
        )
        reopen_state = to_state
        reopen_state.groups.set(from_state.groups.all())

        if created:
            log.info(
                "Created Reopen to_state on {}: {}".format(self.workflow, to_state)
            )

        # Look for a transition that goes to the current state
        transition, created = self.workflow.transition_set.get_or_create(
            action=action,
            from_state=closed_state,
            to_state=reopen_state,
            defaults={
                'priority': 100,
                'only_initial': True,
                'timeline_message': 'Report was reopened',
                'is_lockable': False,
                'is_choosable': False,
                'is_redefinible': False,
                'require_notes': False,
                'requires_evidence': False,
            },
        )
        if created:
            log.info(
                "Created Reopen transition on {}: {}".format(self.workflow, transition)
            )

        # Make sure that the go-forward transitions that will allow user to get out of the reopened state
        # First get all the transitions that point to closed (except those already created)
        pre_close_states = self.workflow.state_set.filter(
            transition__to_state=closed_state
        )
        replicate_transitions = self.workflow.transition_set.filter(
            from_state__in=pre_close_states
        ).exclude(from_state=reopen_state)
        for to_replicate in replicate_transitions:
            replica, created = self.workflow.transition_set.get_or_create(
                action=to_replicate.action,
                from_state=reopen_state,
                to_state=to_replicate.to_state,
                defaults={
                    'priority': to_replicate.priority,
                    'only_initial': to_replicate.only_initial,
                    'timeline_message': to_replicate.timeline_message,
                    'is_lockable': to_replicate.is_lockable,
                    'is_choosable': to_replicate.is_choosable,
                    'is_redefinible': to_replicate.is_redefinible,
                    'require_notes': to_replicate.require_notes,
                    'requires_evidence': to_replicate.requires_evidence,
                },
            )
            if created:
                log.info(
                    "Created replica post-reopen transition on {}: {}".format(
                        self.workflow, replica
                    )
                )
            else:
                log.debug(
                    "replica post-reopen transition already existed %s: %s",
                    self.workflow,
                    replica,
                )

        return transition

    def reopened_label(self):
        """Gets the in-review label that this should have when re-opened"""
        return self.workflow_label.agency_workflow.workflowlabel_set.get(
            slug=WorkflowLabel.IN_REVIEW_SLUG
        )

    @transaction.atomic(using='bms')
    def reopen(self, requesting_user=None):
        """Reopens the form and puts in control of the last user

        Find the most recent movement and change the to-user, add action log, update notifications

        :param requesting_user: The benchmark_user that requested/approved the reopening.

        raises: NotPermitted, NotImplementedError
        returns: None
        """
        log.info(f"Reopening requested for form {self} by {requesting_user}")
        self.check_reopen_allowed(raise_error=True)

        transition = self.reopen_transition()
        reopen_label = self.reopened_label()

        # REOPEN
        cur_movement = self.last_movement
        cur_user = cur_movement.from_user
        log.info(f"Reopening {cur_movement} to {cur_user}")
        movement = Movement(
            form=self,
            transition=transition,
            from_user=cur_user,
            to_user=cur_user,
            note=None,
        )
        movement.save()
        self.workflow_label = reopen_label
        self.save()

        reopener = requesting_user or cur_user

        # Add an action log entry
        action_log = ActionLog(
            user=reopener,
            action='reopen-report',
            state='success',
            action_data={"formId": self.id, "submitterId": self.submitter_id},
        )
        action_log.save()

        # Make the notifications:
        self.build_reopen_notifications(cur_user, requesting_user)

        # DONE!
        return cur_user

    def build_reopen_notifications(self, cur_user, requesting_user):
        """Notify the old user and the requesting user of the re-opening

        If there are no existing notifications, build text manually
        """
        # Current notifications

        cur_notification = self.notifications.filter(
            user=cur_user, action_item=True
        ).first()
        if cur_notification:
            title = cur_notification.title
            body = cur_notification.body
            data = cur_notification.data
            action = cur_notification.action
            is_dismissable = cur_notification.is_dismissable
            notification_type = cur_notification.type
            ## Deactivating old notifiction
            log.info(
                f"Changing old action item to notification for {cur_user}: {cur_notification}"
            )
            cur_notification.action_item = False
            cur_notification.save()
        else:
            title = f"{self.number} is reopened and assigned to you"
            body = f"{self.number} is  reopened and assigned to you"
            data = {"formId": self.id, "submitterId": self.submitter_id}
            action = "submit-report"
            is_dismissable = False
            notification_type = "default"

        # Notify the new user
        log.info(f"Notifying  {cur_user} that they now have a report")
        notification = Notification(
            user=cur_user,
            title=title,
            body=body,
            data=data,
            action=action,
            new=True,
            action_item=True,
            is_dismissable=is_dismissable,
            type=notification_type,
        )
        notification.save()

        # Notify old user
        if requesting_user != cur_user:
            log.info(f"Notifying  {requesting_user} that the report was reopened.")
            passive_notification = Notification(
                user=requesting_user,
                title=f"{self.number} was reopened for {cur_user}",
                body=f"{self.number} was  reopened for {cur_user}",
                data=data,
                action="report-reopened",
                new=True,
                action_item=False,
                is_dismissable=False,
                type="default",
            )
            passive_notification.save()

            return [notification, passive_notification]
        else:
            return [notification, None]


class FormAction(models.Model):
    form = models.ForeignKey(Form, models.DO_NOTHING)
    link = models.ForeignKey('Link', models.DO_NOTHING)
    # This field type is a guess.
    metadata = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'form_action'


class FormSubmission(models.Model):
    number = models.CharField(max_length=255, blank=True, null=True)
    participant_statuses = models.TextField(
        blank=True, null=True
    )  # This field type is a guess.
    last_reviewed_at = models.DateTimeField(blank=True, null=True)
    last_draft_at = models.DateTimeField(blank=True, null=True)
    submitted_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    submitter = models.ForeignKey(
        'BenchmarkUser', models.DO_NOTHING, blank=True, null=True
    )
    workflow = models.ForeignKey('Workflow', models.DO_NOTHING, blank=True, null=True)
    agency = models.ForeignKey('Agency', models.CASCADE, blank=True, null=True)
    is_deleted = models.BooleanField()
    deleted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'form_submission'
