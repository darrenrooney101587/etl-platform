from django.db import models


class Migration(models.Model):
    name = models.CharField(max_length=255)
    run_on = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'migration'

    def __str__(self):
        return self.name


class SchemaMigrations(models.Model):
    version = models.CharField(primary_key=True, max_length=255)

    class Meta:
        managed = False
        db_table = 'schema_migrations'
