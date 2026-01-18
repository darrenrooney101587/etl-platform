from django.db import models


class BenchmarkAccessToken(models.Model):
    id = models.CharField(primary_key=True, max_length=128)
    ttl = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    user = models.ForeignKey('BenchmarkUser', models.DO_NOTHING)
    scopes = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'benchmark_access_token'
