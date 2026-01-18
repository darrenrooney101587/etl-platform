import logging

from django.db import transaction
from django.db import models

from etl_core.models.apps.bms.models.group import Group, AgencyGroup

log = logging.getLogger(__name__)


class BenchmarkRole(models.Model):
    """Roles and Groups have an awkward relationship. Many legacy functionalities
    use groups. Groups look for roles of a given name through a text lookup. So for a group
    to function correctly it must
        * Group
        * Rule
        * Group Rule
        * Agency Group
    """

    name = models.CharField(max_length=128)
    description = models.CharField(max_length=255)
    created_at = models.DateTimeField(blank=True, null=True, auto_now_add=True)
    updated_at = models.DateTimeField(blank=True, null=True, auto_now=True)
    agency = models.ForeignKey('Agency', models.DO_NOTHING)
    public = models.BooleanField(blank=True, null=True)
    is_choosable = models.BooleanField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'benchmark_role'
        verbose_name = 'Legacy BenchmarkRole'
        verbose_name_plural = 'Legacy BenchmarkRoles'

    def __str__(self):
        return '{} ({} Agency:{})'.format(self.name, self.id, self.agency_id)

    def groups(self):
        """Get simple group membership excluding complex rules"""
        return Group.objects.raw(
            '''SELECT g.*
                FROM "group" g
                    INNER join agency_group ag on ag.group_id = g.id
                    INNER join group_rule gr on gr.group_id = g.id
                    INNER join rule r on r.id = rule_id and model = 'BenchmarkRole' and relation = 'users'
                    INNER join benchmark_role br on br.agency_id =ag.agency_id and br.name = r.filters::json#>>'{0, value,0}'
            WHERE br.id=%s
            ''',
            [self.id],
        )

    def get_or_create_security_role(self):
        """Get or create a security role that matches this rank

        Security role is the new way that permissions are managed
        """
        from bms_security.models import BenchmarkRole as SecurityRole

        role, created = SecurityRole.objects.get_or_create(
            agency=self.agency, name=self.name
        )
        if created:
            log.info(
                "Created Security.BenchmarkRole %s to match Legacy Role %d",
                role,
                self.id,
            )
        return role, created

    @transaction.atomic(using='bms')
    def get_or_create_group(self):
        """Get or create a group that ties to this role"""
        groups = self.groups()
        if len(groups) > 0:
            return groups[0], False
        else:
            created = False
            if self.name != self.name.strip():
                log.info(
                    "Group Name has extra spaces. Stripping %d %s", self.id, self.name
                )
                self.name = self.name.strip()
                self.save()
                groups = self.groups()

            # If the group was returned, that means all components were in place (not only the group but also the agency group and the rule)
            if len(groups) == 0:
                log.info("Creating group and agencygroup to match role %s", self)
                group = Group(
                    name=f'{self.name} group',
                    description=f'{self.name} group',
                    rules_operation="intersection",
                )
                group.save()
                created = True
                ag = AgencyGroup(agency=self.agency, group=group)
                ag.save()

                # Now for the non-obvious part, create a rule that matches the group and role
                rule = group.create_rule_for_role(role=self)
            else:
                group = groups[0]
        return group, created
