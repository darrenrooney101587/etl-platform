"""Handle hierarchy Key LTree

The ltree field MUST be hierarchy_key to use this
"""
from django.db import models

from django_ltree.paths import PathGenerator


class HKTreeQuerySet(models.QuerySet):
    def roots(self):
        return self.filter(hierarchy_key__depth=1)

    def children(self, hierarchy_key):
        return self.filter(
            hierarchy_key__descendants=hierarchy_key,
            hierarchy_key__depth=len(hierarchy_key) + 1,
        )


class HKTreeManager(models.Manager):
    def get_queryset(self):
        qs = HKTreeQuerySet(model=self.model, using=self._db).order_by("hierarchy_key")
        field_names = [f.name for f in self.model._meta.fields]
        if 'tenant' in field_names:
            qs = qs.select_related('tenant')
        if 'parent' in field_names:
            qs = qs.select_related('parent')
        return qs

    def roots(self):
        return self.filter().roots()

    def children(self, path):
        return self.filter().children(path)

    def create_child(self, parent=None, **kwargs):
        paths_in_use = parent.children() if parent else self.roots()
        prefix = parent.hierarchy_key if parent else None
        path_generator = PathGenerator(
            prefix,
            skip=paths_in_use.values_list("hierarchy_key", flat=True),
            label_size=getattr(self.model, "label_size"),
        )
        kwargs["hierarchy_key"] = path_generator.next()
        return self.create(**kwargs)
