from django.db import models


class Permission(models.Model):
    name = models.CharField(max_length=128)
    description = models.CharField(max_length=255)
    value = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = 'permission'

    def __str__(self):
        return self.name
