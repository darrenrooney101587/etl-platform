from django.apps import AppConfig

class AccountsConfig(AppConfig):
    name = 'etl_core.models.apps.account'
    label = 'account'
    default_auto_field = 'django.db.models.BigAutoField'
