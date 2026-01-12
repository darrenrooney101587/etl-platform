# reporting_seeder (package)

...existing code...

## Using the Django ORM (developer example)

If you have an upstream package that provides Django settings and models (for example `packages/reporting_models`), you can bootstrap Django at runtime and use a Django-backed DB client:

- Example: `packages/reporting_seeder/reporting_seeder/django_bootstrap.py` contains a deferred-import helper and `DjangoORMClient`.

Direct bootstrap example:

```python
from reporting_seeder.django_bootstrap import bootstrap_django, DjangoORMClient
# Ensure your reporting_models.settings exists and is importable
bootstrap_django("reporting_models.settings")
db = DjangoORMClient()
rows = db.fetch_all("SELECT id, name FROM reporting.some_table LIMIT 10")
```

Factory usage (swap clients via env var):

```bash
export DJANGO_DB_CLIENT_PATH=reporting_seeder.django_bootstrap:DjangoORMClient
```

Then code that uses the `etl_core.support.db_factory.get_database_client()` factory will instantiate `DjangoORMClient` automatically.

Note: importing `reporting_seeder.django_bootstrap` does not itself import Django — the heavy imports are deferred until `bootstrap_django` or `DjangoORMClient` is used.
