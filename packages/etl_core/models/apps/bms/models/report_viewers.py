from django.db import models


class ReportsViewer(models.Model):
    reviewer = models.ForeignKey(
        'BenchmarkUser', models.DO_NOTHING, related_name='reportsviewer_reviewer_set'
    )
    viewer = models.ForeignKey('BenchmarkUser', models.DO_NOTHING)
    state = models.ForeignKey('State', models.DO_NOTHING)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    form_id = models.IntegerField(blank=True, null=True)
    show_bubble = models.BooleanField(blank=True, null=True)
    appear_as_take_action = models.BooleanField()
    can_edit = models.BooleanField()

    class Meta:
        managed = False
        db_table = 'reports_viewer'
