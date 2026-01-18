from django.db import models

from etl_core.models.apps.bms.models.workflow import Workflow


class Group(models.Model):
    name = models.CharField(max_length=255, blank=True, null=True)
    description = models.CharField(max_length=255, blank=True, null=True)
    rules_operation = models.CharField(max_length=255)
    permissions = models.ManyToManyField('Permission', through='GroupPermission')
    rules = models.ManyToManyField('Rule', through='GroupRule')
    states = models.ManyToManyField('State', through='GroupState')

    class Meta:
        managed = False
        db_table = 'group'

    def __str__(self):
        return self.name

    def workflows(self):
        """Traverse to the available workflow queryset"""
        workflows = Workflow.objects.filter(
            state__is_entry_point=True, state__groupstate__group=self
        ).distinct('id')
        return workflows

    def create_rule_for_role(self, role):
        """Makes rule and group-rule that will find the given role"""
        rule = Rule(
            name=f"{role.name} rule",
            relation="users",
            model="BenchmarkRole",
            op="and",
            filters='[{"property":"name","op":"inq","value":["' + role.name + '"]}]',
            agency=role.agency,
        )
        rule.save()
        rule.grouprule_set.create(group=self)
        return rule


class Rule(models.Model):
    name = models.CharField(max_length=128)
    relation = models.CharField(max_length=255, blank=True, null=True)
    model = models.CharField(max_length=255)
    op = models.CharField(max_length=255, blank=True, null=True)
    filters = models.CharField(max_length=255, blank=True, null=True)
    agency = models.ForeignKey('Agency', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'rule'

    def __str__(self):
        return self.name


class AgencyGroupManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related('group', 'agency')


class AgencyGroup(models.Model):
    group = models.ForeignKey('Group', models.DO_NOTHING)
    agency = models.ForeignKey('Agency', models.DO_NOTHING)
    objects = AgencyGroupManager()

    class Meta:
        managed = False
        db_table = 'agency_group'

    def __str__(self):
        return '{}-{}'.format(self.agency, self.group)


class GroupPermission(models.Model):
    group = models.ForeignKey(Group, models.DO_NOTHING)
    permission = models.ForeignKey('Permission', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'group_permission'

    def __str__(self):
        return '{}-{}'.format(self.group, self.permission)


class GroupRule(models.Model):
    group = models.ForeignKey(Group, models.DO_NOTHING)
    rule = models.ForeignKey('Rule', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'group_rule'

    def __str__(self):
        return '{}-{}'.format(self.group, self.rule)


class GroupState(models.Model):
    group = models.ForeignKey(Group, models.DO_NOTHING)
    state = models.ForeignKey('State', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'group_state'

    def __str__(self):
        return '{}-{}'.format(self.group, self.state)
