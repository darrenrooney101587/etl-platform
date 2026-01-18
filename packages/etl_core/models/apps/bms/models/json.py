from django.db import models


class JSONNonBField(models.JSONField):
    """ Override the JSONNonBField handling so that it correctly handles regular JSON (non-JSONB) fields """

    def from_db_value(self, *args, **kwargs):
        value = kwargs.get('value', args[0])
        if value is None:
            return value
        if (
            isinstance(value, dict)
            or isinstance(value, list)
            or isinstance(value, bool)
        ):
            return value

        return super().from_db_value(*args, **kwargs)
