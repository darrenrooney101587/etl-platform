from django.db import models


class OauthAccessToken(models.Model):
    token_id = models.CharField(max_length=255)
    token = models.BinaryField()
    authentication_id = models.CharField(max_length=255)
    user_name = models.CharField(max_length=255)
    client_id = models.CharField(max_length=255)
    authentication = models.BinaryField()
    refresh_token = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = 'oauth_access_token'


class OauthApprovals(models.Model):
    user_id = models.CharField(max_length=255)
    client_id = models.CharField(max_length=255)
    scope = models.CharField(max_length=255)
    status = models.CharField(max_length=10)
    expires_at = models.DateTimeField()
    last_modified_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'oauth_approvals'


class OauthClientDetails(models.Model):
    client_id = models.CharField(primary_key=True, max_length=256)
    resource_ids = models.CharField(max_length=256)
    client_secret = models.CharField(max_length=256)
    scope = models.CharField(max_length=256)
    authorized_grant_types = models.CharField(max_length=256)
    web_server_redirect_uri = models.CharField(max_length=256)
    authorities = models.CharField(max_length=256, blank=True, default='')
    access_token_validity = models.IntegerField()
    refresh_token_validity = models.IntegerField()
    additional_information = models.CharField(max_length=4096, blank=True, null=True)
    autoapprove = models.CharField(max_length=256, blank=True, null=True)
    forgot_password_uri = models.CharField(max_length=256, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'oauth_client_details'
        verbose_name_plural = "OAuth Client Details"


class OauthCode(models.Model):
    authentication = models.BinaryField()

    class Meta:
        managed = False
        db_table = 'oauth_code'


class OauthRefreshToken(models.Model):
    token_id = models.CharField(max_length=255)
    token = models.BinaryField()
    authentication = models.BinaryField()

    class Meta:
        managed = False
        db_table = 'oauth_refresh_token'
