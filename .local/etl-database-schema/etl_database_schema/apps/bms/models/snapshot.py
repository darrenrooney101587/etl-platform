from django.apps.registry import apps
from django.db import models

from etl_database_schema.apps.bms.models.json import JSONNonBField
from etl_database_schema.apps.bms.models.action_log import ActionLog
from etl_database_schema.apps.bms.models.notification import Notification
from etl_database_schema.apps.bms.models.form import Form


class SnapshotManager(models.Manager):
    """ Defers the content field"""

    def get_queryset(self):
        return super().get_queryset().defer('content')


class SnapshotFormManager(SnapshotManager):
    """ Defers the content field"""

    def get_queryset(self):
        return super().get_queryset().filter(entity_type='Form')


class SnapshotFormOrphanManager(SnapshotFormManager):
    """ Defers the content field"""

    def get_queryset(self):
        Form = apps.get_model(app_label='bms', model_name='Form')
        form_ids = Form.objects.all().values_list('id', flat=True)
        return super().get_queryset().exclude(form_id__in=form_ids)


class AbstractSnapshot(models.Model):
    content = JSONNonBField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    document = JSONNonBField(blank=True, null=True)
    entity_type = models.CharField(max_length=255)
    is_final_version = models.BooleanField()
    objects = SnapshotManager()

    class Meta:
        managed = False
        db_table = 'snapshot'
        abstract = True


class Snapshot(AbstractSnapshot):
    entity_id = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'snapshot'


class SnapshotForm(AbstractSnapshot):
    form = models.ForeignKey(
        Form,
        db_column='entity_id',
        null=True,
        editable=False,
        on_delete=models.DO_NOTHING,
    )
    objects = SnapshotFormManager()
    orphans = SnapshotFormOrphanManager()

    class Meta:
        managed = False
        db_table = 'snapshot'

    """
    We have registered the use of the property in this way, because after the refractorization of the code in the models folder,
    for some reason that is not yet known, it has stopped working the way django does it by default.
    """

    @property
    def form__agency(self):
        return self.form.agency

    @property
    def actionlogs(self):
        return ActionLog.objects.raw(
            "SELECT * FROM action_log WHERE action_data ->> 'formId'='%s'",
            [self.form_id],
        )

    @property
    def notifications(self):
        return Notification.objects.raw(
            "SELECT * FROM notification WHERE data ->> 'formId'='%s'", [self.form_id]
        )


class SnapshotUserManager(SnapshotManager):
    """ Defers the content field"""

    def get_queryset(self):
        from django.db.models import Q

        return super().get_queryset().filter(entity_type='BenchmarkUser')
