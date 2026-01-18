from django.db import models

class AdiministrativeEditHistory(models.Model):
    id = models.IntegerField(primary_key=True, editable=False)
    form = models.ForeignKey('Form',models.DO_NOTHING)
    user = models.ForeignKey('BenchmarkUser',models.DO_NOTHING)
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)

    class Meta:
        managed = False
        db_table = u'"public\".\"form_administrative_report_edit_history"'
        verbose_name_plural = 'Administrative Edit History'
