from django.db import models


class StatsView(models.Model):
    actor_type = models.TextField()
    actor_id = models.TextField()
    group_date = models.DateTimeField()
    # This field type is a guess.
    stats = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'stats_view'
