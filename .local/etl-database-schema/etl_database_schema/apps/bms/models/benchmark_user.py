from django.db import models
from django.contrib.postgres.fields import citext
from django.db.models import UniqueConstraint

from etl_database_schema.apps.bms.models.json import JSONNonBField
from etl_database_schema.apps.bms.models.benchmark_role import BenchmarkRole
from etl_database_schema.apps.bms.models.action_log import ActionLog
from etl_database_schema.apps.bms.models.group import Group
from etl_database_schema.apps.bms.models.snapshot import AbstractSnapshot, SnapshotUserManager
from etl_database_schema.apps.bms.models.notification import Notification


class BenchmarkRoleUser(models.Model):
    user = models.ForeignKey('BenchmarkUser', models.DO_NOTHING)
    role = models.ForeignKey(BenchmarkRole, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'benchmark_role_user'


class BenchmarkUser(models.Model):
    email = models.CharField(max_length=255)
    username = models.CharField(unique=True, max_length=255, db_collation='default')
    benchmark_id = citext.CICharField(
        unique=True, max_length=255, blank=True, null=True, db_collation='default'
    )
    organization_user = models.ForeignKey(
        'bms_organization.User',
        models.CASCADE,
        blank=True,
        null=True,
        help_text='The User in the BMS organization',
        db_column="integration_id",
        related_name="benchmark_user",
    )
    password = models.CharField(max_length=255)
    created_at = models.DateTimeField(blank=True, null=True, auto_now_add=True)
    updated_at = models.DateTimeField(blank=True, null=True, auto_now=True)
    rank = models.ForeignKey('Rank', models.DO_NOTHING)
    agency = models.ForeignKey('Agency', models.DO_NOTHING)
    first_name = models.CharField(max_length=128)
    last_name = models.CharField(max_length=128)
    full_name = models.CharField(max_length=128)
    gender = models.CharField(max_length=255, blank=True, null=True)
    race = models.CharField(max_length=255, blank=True, null=True)
    height = models.DecimalField(
        max_digits=65535, decimal_places=10, blank=True, null=True
    )
    weight = models.DecimalField(
        max_digits=65535, decimal_places=10, blank=True, null=True
    )
    dominant_hand = models.CharField(
        max_length=255, blank=True, null=True, db_column='dominant_hand'
    )
    birthday = models.CharField(max_length=255, blank=True, null=True)
    unit_assignment = models.CharField(max_length=255, blank=True, null=True)
    division = models.CharField(max_length=255, blank=True, null=True)
    beat_assignment = models.CharField(max_length=255, blank=True, null=True)
    appointment_date = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text='This is a datetime but there are some year 0 dates that python cant handle',
    )
    star_number = models.CharField(max_length=255, blank=True, null=True)
    post_id = citext.CharField(
        max_length=1000, blank=True, null=True, db_collation='default'
    )
    watch = models.CharField(max_length=255, blank=True, null=True)
    sworn = models.BooleanField()
    taser_serial_number = models.CharField(max_length=255, blank=True, null=True)
    handgun_serial_number = models.CharField(max_length=255, blank=True, null=True)
    rifle_serial_number = models.CharField(max_length=255, blank=True, null=True)
    last_imported_date = models.DateTimeField(blank=True, null=True)
    title = models.CharField(max_length=255, blank=True, null=True)
    employee_id = models.CharField(max_length=255, blank=True, null=True)
    deleted_at = models.DateTimeField(blank=True, null=True)
    is_deleted = models.BooleanField(blank=True, null=True)
    is_izenda_admin = models.BooleanField(
        blank=True, null=True, help_text="This is for internal BM users only"
    )
    realm = models.TextField(blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    mobile_phone = models.CharField(max_length=255, blank=True, null=True)
    home_phone = models.CharField(max_length=255, blank=True, null=True)
    emergency_name = models.CharField(max_length=255, blank=True, null=True)
    emergency_address = models.CharField(max_length=255, blank=True, null=True)
    relationship_officer = models.CharField(max_length=255, blank=True, null=True)
    emergency_home_phone = models.CharField(max_length=255, blank=True, null=True)
    emergency_mobile_phone = models.CharField(max_length=255, blank=True, null=True)
    emergency_optional_phone = models.CharField(max_length=255, blank=True, null=True)
    equipment = JSONNonBField(blank=True, null=True)
    county = models.CharField(max_length=255, blank=True, null=True)
    duty_status = models.CharField(max_length=255, blank=True, null=True)
    termination_date = models.CharField(max_length=255, blank=True, null=True)
    race_other = models.CharField(max_length=255, blank=True, null=True)
    integration_id = models.UUIDField(blank=True, null=True)
    username = models.CharField(max_length=255, blank=True, null=True)
    benchmark_id = models.CharField(max_length=255, blank=True, null=True)
    created_by = models.UUIDField(blank=True, null=True)
    last_modified_by = models.UUIDField(blank=True, null=True)
    mailing_address = models.CharField(max_length=255, blank=True, null=True)
    mailing_county = models.CharField(max_length=255, blank=True, null=True)
    middle_name = models.CharField(max_length=255, blank=True, null=True)
    suffix = models.CharField(max_length=255, blank=True, null=True)
    referencing_gender = models.CharField(max_length=255, blank=True, null=True)

    roles = models.ManyToManyField('BenchmarkRole', through=BenchmarkRoleUser)
    security_roles = models.ManyToManyField(
        'bms_security.BenchmarkRole', through='bms_security.UsersBenchmarkRoles'
    )
    certified = models.BooleanField(
        blank=True,
        null=True,
    )
    cont_education = models.BooleanField(
        blank=True,
        null=True,
    )
    hide_profile_picture = models.BooleanField(
        blank=True,
        null=True,
    )
    ethnicity = models.CharField(max_length=65535, blank=True, null=True)
    supervisor = models.CharField(max_length=255, blank=True, null=True)
    hire_date = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'benchmark_user'
        constraints = [
            UniqueConstraint(
                fields=['username'], name='benchmark_user_username_unique_index'
            ),
            UniqueConstraint(
                fields=['email', 'agency_id'], name='benchmark_user_email_agency_uk'
            ),
        ]
        permissions = (('change_employeeId', 'Change Benchmark User\'s Employee Id'),)

    def __str__(self):
        return '{} ({})'.format(self.email, self.id)

    @property
    def get_user_pipeline_exclusion(self):
        from bms_reporting.models import UserPipelineExclusionList

        result_set = UserPipelineExclusionList.objects.filter(
            employee_id=self.employee_id, bms_agency_id=self.agency_id
        )

        return result_set.first()

    @property
    def user_pipeline_import_exclusion(self):
        from bms_reporting.models import UserPipelineExclusionList

        result_set = UserPipelineExclusionList.objects.filter(
            employee_id=self.employee_id, bms_agency_id=self.agency_id
        )
        return getattr(result_set.first(), 'user_import_pipeline')

    @property
    def user_pipeline_update_exclusion(self):
        from bms_reporting.models import UserPipelineExclusionList

        result_set = UserPipelineExclusionList.objects.filter(
            employee_id=self.employee_id, bms_agency_id=self.agency_id
        )
        return getattr(result_set.first(), 'user_update_pipeline')

    @property
    def user_pipeline_ou_role_exclusion(self):
        from bms_reporting.models import UserPipelineExclusionList

        result_set = UserPipelineExclusionList.objects.filter(
            employee_id=self.employee_id, bms_agency_id=self.agency_id
        )
        return getattr(result_set.first(), 'ou_role_assignment_pipeline')

    @property
    def user_pipeline_all_bms_exclusion(self):
        from bms_reporting.models import UserPipelineExclusionList

        result_set = UserPipelineExclusionList.objects.filter(
            employee_id=self.employee_id, bms_agency_id=self.agency_id
        )
        return getattr(result_set.first(), 'all_bms_pipelines')

    @property
    def has_pipeline_exclusions(self):
        from bms_reporting.models import UserPipelineExclusionList

        result_set = UserPipelineExclusionList.objects.filter(
            employee_id=self.employee_id, bms_agency_id=self.agency_id
        )
        if result_set.count() > 0:
            return True
        else:
            return False

    def snapshot_set(self):
        """Returns a queryset of the snapshots associated with this user"""
        return SnapshotUser.objects.filter(user=self)

    @property
    def integration_id(self):
        return self.organization_user.id

    @property
    def password_masked(self):
        return self.password[0:9] + "*****" + self.password[-2:]

    @property
    def user_organizational_units(self):
        from bms_organization import models as org_models

        if self.organization_user:
            return self.organization_user.userorganizationalunit_set.select_related(
                'organizational_unit'
            )
        else:
            # return org_models.UserOrganizationalUnit.objects.filter(id=-9999)
            return None

    @property
    def actionlogs(self):
        return ActionLog.objects.raw(
            "SELECT * FROM action_log WHERE action_data ->> 'userId'='%s'", [self.id]
        )

    @property
    def is_activated(self):
        """Easier to interpret"""
        if self.is_deleted is None:
            return None
        else:
            return not self.is_deleted

    def decommission(self, prefix='DECOMMISSIONED__'):
        """Decommissioning a user renames them and marks them as deleted

        This is better than deleting data. And it allows us to free up an agency's namespace in case it needs reuse
        """
        self.full_name = f'{prefix}{self.full_name}'
        self.email = f'{prefix}{self.email}'
        self.realm = f'{prefix}{self.realm}'
        self.is_deleted = True
        self.save()

    def groups(self):
        """Get simple group membership excluding complex rules"""
        return Group.objects.raw(
            '''SELECT g.*
                FROM "group" g
                    INNER join agency_group ag on ag.group_id = g.id
                    INNER join group_rule gr on gr.group_id = g.id
                    INNER join rule r on r.id = rule_id and relation = 'users' and model = 'BenchmarkRole'
                    inner join benchmark_role br on br.agency_id =ag.agency_id and br.name = r.filters::json#>>'{0, value,0}'
                    INNER JOIN benchmark_role_user bru on bru.role_id = br.id
            WHERE bru.user_id=%s
            ''',
            [self.id],
        )

    def get_absolute_bms_url(self):
        """Special function to show multi-database url"""
        from django.urls import reverse

        return reverse('user-detail', kwargs={'pk': self.id})


class BenchmarkUserIntegrationId(models.Model):
    agency = models.ForeignKey('Agency', models.DO_NOTHING)
    integration_id = models.UUIDField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'benchmark_user'


class SnapshotUser(AbstractSnapshot):
    user = models.ForeignKey(
        BenchmarkUser,
        db_column='entity_id',
        null=True,
        editable=False,
        on_delete=models.DO_NOTHING,
    )
    objects = SnapshotUserManager()

    class Meta:
        managed = False
        db_table = 'snapshot'

    @property
    def actionlogs(self):
        return ActionLog.objects.raw(
            "SELECT * FROM action_log WHERE action_data ->> 'userId'='%s'",
            [self.user_id],
        )

    @property
    def notifications(self):
        return Notification.objects.raw(
            "SELECT * FROM notification WHERE data ->> 'userId'='%s'", [self.user_id]
        )


class BenchmarkUserSecret(BenchmarkUser):
    """Extra class for showing secrets in the admin page"""

    class Meta:
        proxy = True


class UserConfigDefault(models.Model):
    field = models.CharField(max_length=255, blank=True, null=True)
    label = models.CharField(max_length=255, blank=True, null=True)
    type = models.CharField(max_length=255, blank=True, null=True)
    editable = models.BooleanField(blank=True, null=True)
    visible = models.BooleanField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True, auto_now_add=True)
    updated_at = models.DateTimeField(blank=True, null=True, auto_now=True)
    profile_data_in_form = models.BooleanField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'user_config_default'

    def __str__(self):
        return str(self.field)


class UserConfigOverride(models.Model):
    agency = models.ForeignKey('Agency', models.DO_NOTHING, blank=True, null=True)
    user_config_default = models.ForeignKey(
        UserConfigDefault, models.DO_NOTHING, blank=True, null=True
    )
    label = models.CharField(max_length=255, blank=True, null=True)
    editable = models.BooleanField(blank=True, null=True)
    visible = models.BooleanField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True, auto_now_add=True)
    updated_at = models.DateTimeField(blank=True, null=True, auto_now=True)
    profile_data_in_form = models.BooleanField(blank=True, null=True)
    exclude_from_pipeline = models.BooleanField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'user_config_override'
