from django.db import models


class Handler(models.Model):
    name = models.CharField(max_length=255, blank=True, null=True)
    description = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'handler'

    def __str__(self):
        return f'{self.name}'
