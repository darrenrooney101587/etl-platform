"""
NOTE: because this controls tables in BMS, this MUST use the schema name explicitly
"""
from django.db import models
from django_ltree.fields import PathField
from django.contrib.postgres.fields import ArrayField
import logging
import uuid

from etl_core.models.apps.bms.models import Agency
from etl_core.models.apps.bms_organization.managers import HKTreeManager
from etl_core.models.apps.bms_security.models import BenchmarkRole

log = logging.getLogger(__name__)


class AgencyEntity(models.Model):
    name = models.CharField(max_length=100)
    bms_agency = models.OneToOneField(
        'bms.Agency',
        models.PROTECT,
        blank=True,
        null=True,
        help_text='The Agency in the core BMS App',
    )
    created = models.DateTimeField(blank=True, auto_now_add=True)
    updated = models.DateTimeField(blank=True, auto_now=True)

    class Meta:
        managed = False
        db_table = u'"organization\".\"agency_entity\"'
        verbose_name_plural = 'POC Agency Entities'

    def __str__(self):
        return f"{self.name} BMS-{self.bms_agency_id}"

    def org_entity(self):
        """Returns the top level org entity for this agency"""
        return self.orgentity_set.filter(is_agency_top=True).first()


class OrgEntity(models.Model):
    ENTITY_SEPARATOR = '.'
    ENTITY_PREFIX = 'OU'
    name = models.CharField(max_length=128)
    agency_entity = models.ForeignKey(AgencyEntity, models.CASCADE)
    external_uid = models.CharField(max_length=32, null=True, blank=True)
    parent = models.ForeignKey(
        'OrgEntity',
        models.CASCADE,
        blank=True,
        null=True,
        related_name='org_children_set',
    )
    is_agency_top = models.BooleanField(
        default=False,
        help_text="True when this is the top entity for the agency (it can still have parents, but they would be in another org)",
    )
    hierarchy_key = models.CharField(
        blank=True, null=True, max_length=128, editable=False, db_index=True
    )
    created = models.DateTimeField(blank=True, auto_now_add=True)
    updated = models.DateTimeField(blank=True, auto_now=True)

    class Meta:
        managed = False
        db_table = u'"organization\".\"org_entity\"'
        verbose_name = 'Organization Entity'
        verbose_name_plural = 'POC Organization Entities'

    def __str__(self):
        return f"{self.name} ({self.hierarchy_key})"

    @property
    def root_hierarchy_key(self):
        """Returns the very firs tentry in the hierarchy key"""
        if self.hierarchy_key:
            root_key = (
                self.hierarchy_key.split(self.ENTITY_SEPARATOR)[0]
                + self.ENTITY_SEPARATOR
            )
            return root_key

    def descendents(self, cross_agency=True, include_self=False):
        """Returns all descendents as defined by the hierarchy key"""
        if self.hierarchy_key:
            oe = OrgEntity.objects.filter(hierarchy_key__startswith=self.hierarchy_key)
            if not cross_agency:
                oe = oe.filter(agency_entity=self.agency_entity)
            if not include_self:
                oe = oe.exclude(id=self.id)
            return oe
        else:
            return OrgEntity.objects.filter(id=-1)  # Return empty queryset

    def ancestry_root(self):
        """Returns the top most node in this tree"""
        if self.hierarchy_key:
            return OrgEntity.objects.filter(
                hierarchy_key=self.root_hierarchy_key
            ).first()

    def agency_ancestry_root(self):
        """Returns the top most node in this tree WITH THE SAME AGENCY"""
        if self.hierarchy_key:
            return (
                self.ancestry_root()
                .descendents(include_self=True)
                .filter(agency_entity=self.agency_entity, is_agency_top=True)
                .first()
            )

    def create_hierarchy_key(self, rebuild=False):
        """Creates a hierarchy key from this entity and its parents

        :param rebuild: If True, this will overwrite existing values
        """
        if self.hierarchy_key is None or rebuild:
            node_key = f'{self.ENTITY_PREFIX}{self.id}{self.ENTITY_SEPARATOR}'
            log.info(f"Creating hierarchy key for {self.id}-{self.name}")
            if self.parent is None:
                self.hierarchy_key = node_key
            else:
                if self.parent.hierarchy_key is None:
                    msg = f"Parent entity {self.parent} has not set its hierarchy key. Unable to continue."
                    log.error(msg)
                    raise ValueError(msg)
                else:
                    self.hierarchy_key = f'{self.parent.hierarchy_key}{node_key}'
            self.save()
            log.debug(f"Hierarchy Key Set: {self.name} ({self.hierarchy_key})")
        return self.hierarchy_key

    def build_key_tree(self, depth=0, rebuild=False):
        """Builds key for self and all descendents"""
        n_keys = 1
        log.info(f"{depth}:\tBuilding keys from {self} (rebuild={rebuild})")
        self.create_hierarchy_key(rebuild=rebuild)
        n_children = self.org_children_set.count()
        if n_children:
            log.debug(f"\t\t{n_children} direct descendents")
            for descendent in self.org_children_set.all():
                n_keys += descendent.build_key_tree(depth=depth + 1, rebuild=rebuild)

            log.debug(f"\t {self} branch complete")
        return n_keys


class OrgMember(models.Model):
    """Data model to the lowest level of membership for users"""

    org_entity = models.ForeignKey(
        OrgEntity,
        on_delete=models.CASCADE,
        help_text="Store the Prosecuting Agency information",
    )
    bms_benchmark_user = models.ForeignKey(
        'bms.BenchmarkUser',
        models.CASCADE,
        blank=True,
        null=True,
        help_text='The User in the core BMS App',
    )
    created = models.DateTimeField(blank=True, auto_now_add=True)
    updated = models.DateTimeField(blank=True, auto_now=True)

    class Meta:
        managed = False
        db_table = u'"organization\".\"org_member\"'
        verbose_name_plural = 'POC Organization Members'


class MunicipalJurisdiction(models.Model):
    """Data model to store a municipality jurisdiction reference lookup information."""

    municipality = models.CharField(
        verbose_name="Municipality",
        help_text="Store the Municipality information",
        max_length=255,
    )
    county = models.CharField(
        verbose_name="County",
        blank=True,
        null=True,
        help_text="Store the County information",
        max_length=255,
    )
    prosecuting_agency = models.ForeignKey(
        'bms.Agency',
        on_delete=models.DO_NOTHING,
        verbose_name="Prosecuting Agency",
        help_text="Store the Prosecuting Agency information",
    )
    created = models.DateTimeField(blank=True, auto_now_add=True)
    updated = models.DateTimeField(blank=True, auto_now=True)

    class Meta:
        managed = False
        db_table = u'"organization\".\"municipal_jurisdiction\"'
        verbose_name_plural = 'Municipal Jurisdictions'


class Tenant(models.Model):
    class UsernameSourceEnum(models.TextChoices):
        BENCHMARK_ID = 'benchmarkId'
        EMAIL = 'email'

    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    slug = models.CharField(unique=True, max_length=255)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField(blank=True, null=True)
    username_source = models.CharField(
        max_length=50, choices=UsernameSourceEnum.choices
    )
    benchmark_id_prefix = models.CharField(max_length=50, blank=True, null=True)
    agency_id = models.IntegerField(blank=True, null=True)
    created_by = models.UUIDField(blank=True, null=True)
    last_modified_by = models.UUIDField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = u'"organization\".\"tenant\"'
        ordering = ('slug',)

    def __str__(self):
        return f"{self.slug} ({self.id})"

    @property
    def agency(self):
        if self.agency_id:
            return Agency.objects.get(id=self.agency_id)

    def organizational_unit(self):
        """Returns the top level org entity for this agency"""
        return self.organizationalunit_set.filter(tenant_root=True).first()

    def root_organizational_units(self):
        """Returns the top level org entity for this agency"""
        return self.organizationalunit_set.filter(tenant_root=True)

    def decommission(self, prefix='DECOMMISSIONED__'):
        """Decommissioning a tenant renames them and marks them as deleted

        This is better than deleting data. And it allows us to free up an agency's namespace in case it needs reuse
        """
        self.slug = f'{prefix}{self.slug}'
        self.save()
        user_orgs = UserOrganizationalUnit.objects.filter(
            organizational_unit__tenant=self
        )
        for user_org in user_orgs.all().select_related('user'):
            user_org.user.decommission()


class DatabaseChangeLog(models.Model):
    id = models.CharField(max_length=255, primary_key=True)
    author = models.CharField(max_length=255)
    filename = models.CharField(max_length=255)
    date_executed = models.DateTimeField(db_column='dateexecuted')
    order_executed = models.IntegerField(db_column='orderexecuted')
    exec_type = models.CharField(max_length=10, db_column='exectype')
    md5sum = models.CharField(max_length=35, blank=True, null=True)
    description = models.CharField(max_length=255, blank=True, null=True)
    comments = models.CharField(max_length=255, blank=True, null=True)
    tag = models.CharField(max_length=255, blank=True, null=True)
    liquibase = models.CharField(max_length=20, blank=True, null=True)
    contexts = models.CharField(max_length=255, blank=True, null=True)
    labels = models.CharField(max_length=255, blank=True, null=True)
    deployment_id = models.CharField(max_length=10, blank=True, null=True)

    class Meta:
        managed = False
        db_table = u'"organization\".\"databasechangelog\"'


class DatabaseChangeLogLock(models.Model):
    id = models.IntegerField(primary_key=True, editable=False, default=uuid.uuid4)
    locked = models.BooleanField()
    lock_granted = models.DateTimeField(blank=True, null=True, db_column='lockgranted')
    locked_by = models.CharField(
        max_length=255, blank=True, null=True, db_column='lockedby'
    )

    class Meta:
        managed = False
        db_table = u'"organization\".\"databasechangeloglock\"'


class OrganizationalUnit(models.Model):
    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    name = models.CharField(max_length=250, blank=True, null=True, unique=True)
    tenant = models.ForeignKey('Tenant', models.CASCADE)
    parent = models.ForeignKey('self', models.CASCADE, blank=True, null=True)
    tenant_root = models.BooleanField(blank=True, null=True)
    incremental_id = models.PositiveIntegerField(
        help_text='Like a primary key. But not.', unique=True, editable=False
    )
    depth = models.IntegerField(blank=True, null=True)
    hierarchy_key = PathField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)
    phone_number = models.CharField(max_length=50, blank=True, null=True)
    website = models.CharField(max_length=255, blank=True, null=True)
    display_name = models.CharField(max_length=255)
    created_by = models.ForeignKey(
        'bms_organization.User',
        db_column='created_by',
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )
    last_modified_by = models.ForeignKey(
        'bms_organization.User',
        db_column='last_modified_by',
        blank=True,
        null=True,
        related_name='organizationalunit_modified_set',
        on_delete=models.SET_NULL,
    )
    operational = models.BooleanField(default=True)
    decommissioned = models.BooleanField(default=False)
    agency_organization_uid = models.CharField(max_length=255, blank=True, null=True)
    agency_organization_code = models.CharField(max_length=50, blank=True, null=True)
    compare_slug = models.CharField(max_length=50, blank=True, null=True)
    census_place_id = models.CharField(max_length=50, blank=True, null=True)

    objects = HKTreeManager()

    class Meta:
        managed = False
        db_table = u'"organization"."organizational_unit"'

    def __str__(self):
        return f"{self.name} ({self.hierarchy_key})"

    def get_ancestors_paths(self):  # type: () -> List[List[str]]
        # return None
        return [
            PathValue(self.hierarchy_key[:n])
            for n, p in enumerate(self.hierarchy_key)
            if n > 0
        ]

    def ancestors(self):
        return type(self)._default_manager.filter(
            hierarchy_key__ancestors=self.hierarchy_key
        )

    def descendants(self):
        return type(self)._default_manager.filter(
            hierarchy_key__descendants=self.hierarchy_key
        )

    def descendants_without_decommissioned(self):
        return type(self)._default_manager.filter(
            hierarchy_key__descendants=self.hierarchy_key, decommissioned=False
        )

    def root(self):
        return self.ancestors().filter(hierarchy_key__depth=1).first()

    def agency_root(self):
        return self.tenant.organizational_unit()

    def parent_by_key(self):
        if len(self.hierarchy_key) > 1:
            return self.ancestors().exclude(id=self.id).last()

    def children(self):
        return self.descendants().filter(
            hierarchy_key__depth=len(self.hierarchy_key) + 1
        )

    def children_without_decommissioned(self):
        return self.descendants().filter(
            hierarchy_key__depth=len(self.hierarchy_key) + 1, decommissioned=False
        )

    def siblings(self):
        parent = self.hierarchy_key[:-1]
        return (
            type(self)
            ._default_manager.filter(hierarchy_key__descendants=".".join(parent))
            .filter(hierarchy_key__depth=len(self.hierarchy_key))
            .exclude(hierarchy_key=self.hierarchy_key)
        )

    @property
    def hkdepth(self):
        if self.hierarchy_key:
            return len(self.hierarchy_key)
        else:
            return None


class User(models.Model):
    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    created_at = models.DateTimeField(editable=False, auto_now=True)
    updated_at = models.DateTimeField(
        editable=False, blank=True, null=True, auto_now_add=True
    )

    def __str__(self) -> str:
        benchmark_user = self.benchmark_user.all()
        return str(benchmark_user[0] if len(benchmark_user) >= 1 else self.id)

    def email(self) -> str:
        benchmark_user = self.benchmark_user.all().first()
        return benchmark_user.email if benchmark_user else 'no email found'

    def _id(self):
        return self.id

    # added because cannot pull from Benchmark_User, gives none, not sure why this is a workaround.
    # same for email
    def benchmark_user_id(self) -> str:
        benchmark_user = self.benchmark_user.all().first()
        return benchmark_user.id if benchmark_user else 'no id found'

    integration_id = property(_id)

    @property
    def benchmark_user(self):
        benchmark_user = self.benchmark_user.all().first()
        return benchmark_user if benchmark_user else 'BMS User not related'

    @property
    def agency_name(self):
        benchmark_user = self.benchmark_user.all().first()
        if benchmark_user and benchmark_user.agency:
            return benchmark_user.agency.name
        return 'No Agency'

    class Meta:
        managed = False
        db_table = u'"organization"."user"'

    def decommission(self, prefix='DECOMMISSIONED__'):
        """Nothing to do here anymore... no more email..."""
        pass

    def get_primary_roles(self):

        roles = BenchmarkRole.objects.filter(
            userorganizationalunitrole__user_organizational_unit__user_id=self.id,
            userorganizationalunitrole__user_organizational_unit__primary=True,
        )
        return roles

    def get_absolute_bms_url(self):
        """Special function to show multi-database url"""
        from django.urls import reverse

        if self.benchmark_user.first():
            return reverse('user-detail', kwargs={'pk': self.benchmark_user.first().id})


class UserDatastoreAttribute(models.Model):
    class AttributeTypeEnum(models.TextChoices):
        BOOLEAN = 'boolean'
        STRING = 'string'
        NUMBER = 'number'
        TEXT = 'text'
        DATE = 'date'
        OBJECT = 'object'

    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    tenant = models.ForeignKey(Tenant, models.DO_NOTHING)
    attribute_name = models.CharField(max_length=50)
    attribute_type = models.CharField(max_length=50, choices=AttributeTypeEnum.choices)
    is_array = models.BooleanField(blank=True, null=True)
    valid_values = ArrayField(models.TextField(), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(blank=True, null=True, auto_now=True)
    parent = models.ForeignKey('self', models.DO_NOTHING, blank=True, null=True)

    def __str__(self):
        return f"{self.attribute_name} ({self.id})"

    class Meta:
        managed = False
        db_table = u'"organization"."user_datastore_attribute"'
        constraints = [
            models.UniqueConstraint(
                fields=['tenant_id', 'attribute_name'],
                name='user_datastore_attribute_tenant_attribute_uk',
            )
        ]


class UserDatastoreSection(models.Model):
    class TypeEnum(models.TextChoices):
        TABLE = 'table'
        FORM = 'form'

    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    tenant = models.ForeignKey(Tenant, models.DO_NOTHING)
    title = models.CharField(max_length=100)
    visible = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(blank=True, null=True, auto_now=True)
    settings = models.JSONField(default={"order": 0, "collapsedByDefault": False})
    type = models.CharField(max_length=128, choices=TypeEnum.choices)
    table_object_attribute_id = models.UUIDField(null=True, blank=True)
    role_ids_with_view = ArrayField(models.BigIntegerField())
    role_ids_with_edit = ArrayField(models.BigIntegerField())
    created_by = models.UUIDField(null=True, blank=True)
    last_modified_by = models.UUIDField(null=True, blank=True)

    def __str__(self):
        return f"{self.title} ({self.id})"

    class Meta:
        managed = False
        db_table = u'"organization"."user_datastore_section"'


class UserDatastoreSectionAttribute(models.Model):
    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    section = models.ForeignKey(UserDatastoreSection, models.DO_NOTHING)
    user_datastore_attribute = models.ForeignKey(
        UserDatastoreAttribute, models.DO_NOTHING
    )
    attribute_title = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(blank=True, null=True, auto_now=True)
    settings = models.JSONField(
        default={"formOrder": 0, "formColumn": 0, "tableOrder": 0, "tableColumn": 0}
    )

    class Meta:
        managed = False
        db_table = u'"organization"."user_datastore_section_attribute"'
        constraints = [
            models.UniqueConstraint(
                fields=['section_id', 'user_datastore_attribute'],
                name='user_datastore_section_attribute_section_attribute_uk',
            )
        ]

    def __str__(self):
        return f"{self.section.title}: {self.user_datastore_attribute.attribute_name}"


class UserDatastoreValue(models.Model):
    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    user = models.ForeignKey(User, models.DO_NOTHING)
    user_datastore_attribute = models.ForeignKey(
        UserDatastoreAttribute, models.DO_NOTHING
    )
    value = models.CharField(max_length=256, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(blank=True, null=True, auto_now=True)
    parent = models.ForeignKey('self', models.DO_NOTHING, blank=True, null=True)

    def __str__(self):
        return f"{self.value} ({self.id})"

    class Meta:
        managed = False
        db_table = u'"organization"."user_datastore_value"'


class EmploymentHistoryConfig(models.Model):
    class FieldEnum(models.TextChoices):
        EFFECTIVE_DATE = 'effectiveDate'
        SEPARATION_DATE = 'separationDate'
        EMPLOYMENT_ACTION = 'employmentAction'
        TITLE_RANK = 'titleRank'
        PRIMARY = 'primary'
        COMMENT = 'comment'
        EMPLOYMENT_TYPE = 'employmentType'
        STATUS = 'status'
        APPOINTMENT_DATE = 'appointmentDate'
        TOUR_OF_DUTY = 'tourOfDuty'
        SUPERVISOR = 'supervisor'
        ROLE = 'role'

    class TypeEnum(models.TextChoices):
        STRING = "string"
        DATE = "date"
        DATETIME = "datetime"
        TIME = "time"
        NUMBER = "number"
        BOOLEAN = "boolean"
        # LINK = "link" valid in org service repo, not sure if implemented
        # TREE = "tree" valid in org service repo, not sure if implemented
        MULTISELECT = "multiselect"
        TEXT = "text"

    class SourceEnum(models.TextChoices):
        ORGANIZATION = "organization"
        EMPLOYMENT = "employment"

    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    tenant = models.ForeignKey('Tenant', models.DO_NOTHING)
    field = models.CharField(
        max_length=100, blank=True, null=True, editable=False, choices=FieldEnum.choices
    )
    label = models.CharField(max_length=255, blank=True, null=True)
    type = models.CharField(
        max_length=100, blank=True, null=True, choices=TypeEnum.choices
    )
    editable = models.BooleanField(null=True, blank=True)
    visible = models.BooleanField(null=True, blank=True)
    values = models.CharField(max_length=500, blank=True, null=True)
    source = models.CharField(
        max_length=100, blank=True, null=True, choices=SourceEnum.choices
    )
    table = models.CharField(max_length=255, blank=True, null=True)
    table_fields = models.CharField(max_length=500, blank=True, null=True)
    display_order = models.IntegerField(blank=True, null=True)
    created_by = models.UUIDField(blank=True, null=True)
    last_modified_by = models.UUIDField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = u'"organization"."employment_history_config"'


class UserEmploymentHistory(models.Model):
    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    user_organizational_unit_history = models.ForeignKey(
        'UserOrganizationalUnitHistory', models.DO_NOTHING
    )
    effective_date = models.CharField(max_length=255, blank=True, null=True)
    employment_action = models.CharField(max_length=255, blank=True, null=True)
    title_rank = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=255, blank=True, null=True)
    employment_type = models.CharField(max_length=255, blank=True, null=True)
    supervisor = models.CharField(max_length=255, blank=True, null=True)
    tour_of_duty = models.CharField(max_length=255, blank=True, null=True)
    detail_method = models.CharField(max_length=255, blank=True, null=True)
    comment = models.CharField(max_length=512, blank=True, null=True)
    role = models.CharField(max_length=512, blank=True, null=True)
    is_deleted = models.BooleanField()
    created_at = models.CharField(max_length=255, blank=True, null=True)
    updated_at = models.CharField(max_length=255, blank=True, null=True)
    created_by = models.ForeignKey(
        User,
        models.DO_NOTHING,
        db_column='created_by',
        related_name='useremploymenthistory_created_set',
    )
    last_modified_by = models.ForeignKey(
        User,
        models.DO_NOTHING,
        db_column='last_modified_by',
        related_name='useremploymenthistory_updated_set',
    )

    class Meta:
        managed = False
        db_table = u'"organization"."user_employment_history"'

    @property
    def user(self):
        return self.user_organizational_unit_history.user


class UserOrganizationalUnitHistory(models.Model):
    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    user = models.ForeignKey(User, models.DO_NOTHING)
    organizational_unit = models.ForeignKey(OrganizationalUnit, models.DO_NOTHING)
    appointment_date = models.DateField()
    separation_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField(blank=True, null=True)

    def _id(self):
        return self.id

    user_organizational_unit_history = property(_id)

    class Meta:
        managed = False
        db_table = u'"organization"."user_organizational_unit_history"'


class UserOrganizationalUnit(models.Model):
    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    user = models.ForeignKey('bms_organization.User', models.DO_NOTHING)
    organizational_unit = models.ForeignKey(OrganizationalUnit, models.DO_NOTHING)
    created_at = models.DateTimeField(null=True, blank=True, auto_now_add=True)
    updated_at = models.DateTimeField(blank=True, null=True, auto_now=True)
    created_by = models.ForeignKey(
        'bms_organization.User',
        db_column='created_by',
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name='userorganizationalunit_created_by_set',
    )
    last_modified_by = models.ForeignKey(
        'bms_organization.User',
        db_column='last_modified_by',
        blank=True,
        null=True,
        related_name='userorganizationalunit_modified_by_set',
        on_delete=models.SET_NULL,
    )
    primary = models.BooleanField(null=True, blank=True)

    # creating a field not stored in the DB for admin view
    def _view_roles(self):
        return ""

    view_roles = property(_view_roles)

    def _delete_role(self):
        return ""

    delete_roles = property(_delete_role)

    def _add_role(self):
        return ""

    add_roles = property(_add_role)

    def _id(self):
        return self.id

    user_organizational_unit_id = property(_id)

    class Meta:
        managed = False
        db_table = u'"organization"."user_organizational_unit"'


class UserOrganizationalUnitRole(models.Model):
    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    user_organizational_unit = models.ForeignKey(
        UserOrganizationalUnit, models.DO_NOTHING, db_column='user_ou_id'
    )
    user_role = models.ForeignKey(
        'bms_security.BenchmarkRole', models.DO_NOTHING, db_column='role_id'
    )
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField(blank=True, null=True)
    created_by = models.ForeignKey(
        'bms_organization.User',
        db_column='created_by',
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name='organizationalunitrole_created_by_set',
    )
    last_modified_by = models.ForeignKey(
        'bms_organization.User',
        db_column='last_modified_by',
        blank=True,
        null=True,
        related_name='organizationalunitrole_modified_by_set',
        on_delete=models.SET_NULL,
    )

    @property
    def organizational_unit(self):
        return self.user_organizational_unit.organizational_unit

    @property
    def role(self):
        return self.user_role.name

    @property
    def user(self):
        return self.user_organizational_unit.user

    class Meta:
        managed = False
        db_table = u'"organization"."user_organizational_unit_role"'


class UserDocument(models.Model):
    """Model for user_documents table (managed externally)."""

    id: models.UUIDField = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )
    user = models.ForeignKey(
        'User',
        db_column='user_id',
        on_delete=models.DO_NOTHING,
        related_name='user_documents',
    )
    file_name: models.CharField = models.CharField(max_length=255)
    description: models.CharField = models.CharField(
        max_length=1000, blank=True, null=True
    )
    document_type: models.CharField = models.CharField(
        max_length=255, blank=True, null=True
    )
    location_url: models.CharField = models.CharField(
        max_length=255, blank=True, null=True
    )
    created_by = models.ForeignKey(
        'User',
        db_column='created_by',
        on_delete=models.DO_NOTHING,
        related_name='created_user_documents',
        blank=True,
        null=True,
    )
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    last_modified_by = models.ForeignKey(
        'User',
        db_column='last_modified_by',
        on_delete=models.DO_NOTHING,
        related_name='modified_user_documents',
        blank=True,
        null=True,
    )
    updated_at: models.DateTimeField = models.DateTimeField(
        auto_now=True, blank=True, null=True
    )

    class Meta:
        managed = False

        db_table = u'"organization"."user_documents"'
