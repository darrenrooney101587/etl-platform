from django.db import models


class ClientApplication(models.Model):
    client_id = models.CharField(max_length=255, blank=True, null=True)
    client_secret = models.CharField(max_length=255, blank=True, null=True)
    client_type = models.CharField(max_length=255, blank=True, null=True)
    redirect_uris = models.TextField(
        blank=True, null=True
    )  # This field type is a guess.
    # This field type is a guess.
    scopes = models.TextField(blank=True, null=True)
    application_type = models.CharField(max_length=255, blank=True, null=True)
    response_types = models.TextField(
        blank=True, null=True
    )  # This field type is a guess.
    # This field type is a guess.
    grant_types = models.TextField(blank=True, null=True)
    client_name = models.CharField(max_length=255, blank=True, null=True)
    logo_uri = models.CharField(max_length=255, blank=True, null=True)
    client_uri = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    token_endpoint_auth_method = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'client_application'
