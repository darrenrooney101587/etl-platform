# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey has `on_delete` set to the desired behavior.
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models
from django.db.models import UniqueConstraint

from etl_core.models.apps.bms.models import BenchmarkUser


class AgencyConfiguration(models.Model):
    AUTH_HTTP = 'HTTP'
    AUTH_FILE = 'FILE'
    AUTH_OPTIONS = ((AUTH_HTTP, AUTH_HTTP), (AUTH_FILE, AUTH_FILE))
    agency = models.OneToOneField(
        'bms.Agency', on_delete=models.CASCADE, primary_key=True
    )
    identifier = models.CharField(
        max_length=50, help_text="Must Match BMS identifier", unique=True
    )
    auth_type = models.CharField(
        max_length=50,
        choices=AUTH_OPTIONS,
        help_text="How is the agency configuration provided?",
    )
    auth_config_url = models.CharField(
        max_length=255,
        help_text="If HTTP Type, put the URL here",
        blank=True,
        null=True,
    )
    auth_config = models.TextField(blank=True, null=True, editable=True)
    created_at = models.DateTimeField(blank=True, auto_now_add=True)
    updated_at = models.DateTimeField(blank=True, auto_now=True)

    class Meta:
        managed = False
        db_table = u'"security\".\"agency_configuration\"'
        verbose_name = 'Agency Security Configuration'
        verbose_name_plural = 'Agency Security Configurations'

    def __str__(self):
        return f'{self.identifier}'


class BenchmarkRole(models.Model):
    name = models.CharField(max_length=50)
    rank_number = models.IntegerField(default=100)
    agency = models.ForeignKey(
        'bms.Agency',
        models.CASCADE,
        blank=True,
        null=True,
        related_name='securityrole_set',
    )
    tenant_id = models.UUIDField(blank=True, null=True)
    role_permissions = models.ManyToManyField(
        'bms_security.Permission',
        related_name="role_set",
        through='bms_security.BenchmarkRolesPermissions',
    )
    is_internal = models.BooleanField(default=False)
    created_by = models.UUIDField(blank=True, null=True)
    last_modified_by = models.UUIDField(blank=True, null=True)
    created = models.DateTimeField(blank=True, auto_now_add=True)
    updated = models.DateTimeField(blank=True, auto_now=True)

    class Meta:
        managed = False
        db_table = u'"security\".\"benchmark_role\"'
        constraints = [
            UniqueConstraint(
                fields=['agency', 'name'], name='benchmark_role_agency_name_uk'
            )
        ]
        verbose_name = 'Benchmark Role'
        verbose_name_plural = 'Benchmark Roles'

    def __str__(self):
        return str(self.name)


class BenchmarkRolesPermissions(models.Model):
    permission = models.ForeignKey('bms_security.Permission', models.DO_NOTHING)
    role = models.ForeignKey('bms_security.BenchmarkRole', models.CASCADE)
    created = models.DateTimeField(blank=True, auto_now_add=True)
    updated = models.DateTimeField(blank=True, auto_now=True)

    class Meta:
        managed = False
        db_table = u'"security\".\"benchmark_roles_permissions\"'
        verbose_name = 'Benchmark Role Permission'
        verbose_name_plural = 'Benchmark Role Permissions'

    def __str__(self):
        return f'{self.role}-{self.permission}'


class Permission(models.Model):
    name = models.CharField(unique=True, max_length=50)
    display_name = models.CharField(unique=True, max_length=50)
    description = models.CharField(max_length=255, blank=True, null=True)
    category = models.CharField(max_length=255, blank=True, null=True)
    created = models.DateTimeField(blank=True, auto_now_add=True)
    updated = models.DateTimeField(blank=True, auto_now=True)

    class Meta:
        managed = False
        db_table = u'"security\".\"permission\"'
        verbose_name = 'Security Permission'
        verbose_name_plural = 'Security Permissions'

    def __str__(self):
        return str(self.name)


class UsersBenchmarkRoles(models.Model):
    user = models.ForeignKey('bms.BenchmarkUser', models.CASCADE)
    role = models.ForeignKey('bms_security.BenchmarkRole', models.CASCADE)
    created = models.DateTimeField(blank=True, auto_now_add=True)
    updated = models.DateTimeField(blank=True, auto_now=True)

    class Meta:
        managed = False
        db_table = u'"security\".\"users_benchmark_roles\"'
        verbose_name = 'Security User-Role'
        verbose_name_plural = 'Security User-Roles'


class LoginAuditHistory(models.Model):
    ip_address = models.CharField(max_length=20, editable=False)
    failed = models.BooleanField(editable=False)
    logged_at = models.DateTimeField(editable=False)
    source = models.CharField(max_length=100, editable=False)
    benchmark_user = models.ForeignKey(
        BenchmarkUser,
        db_column="username",
        to_field="username",
        on_delete=models.PROTECT,
        db_constraint=False,
    )

    class Meta:
        managed = False
        db_table = u'"security\".\"login_audit_history\"'
