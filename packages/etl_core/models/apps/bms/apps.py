# etl_database_schema/apps/bms/apps.py

from django.apps import AppConfig

class BMSConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'etl_core.models.apps.bms'
    label = 'bms'
