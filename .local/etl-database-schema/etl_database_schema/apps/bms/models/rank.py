import logging

from django.db import transaction
from django.db import models

from etl_database_schema.apps.bms.models.agency import Agency
from etl_database_schema.apps.bms.models.benchmark_role import BenchmarkRole
from etl_database_schema.apps.bms.models.benchmark_user import BenchmarkUser
from etl_database_schema.apps.bms.models.group import Group

log = logging.getLogger(__name__)


class Rank(models.Model):
    name = models.CharField(max_length=128)
    description = models.CharField(max_length=255, blank=True, null=True)
    abbreviation = models.CharField(max_length=255, blank=True, null=True)
    agency = models.ForeignKey(Agency, models.DO_NOTHING)
    is_choosable = models.BooleanField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'rank'

    def __str__(self):
        return self.name

    def __repr__(self):
        return '{self.__class__}({name}, {description}, {abbreviation}, {agency}, {is_choosable})'

    def groups(self):
        """Get simple group membership excluding complex rules"""
        return Group.objects.raw(
            '''SELECT g.*
                FROM "group" g
                    INNER join agency_group ag on ag.group_id = g.id
                    INNER join group_rule gr on gr.group_id = g.id
                    INNER join rule r on r.id = rule_id and model = 'Rank' and relation = 'users'
                    INNER join rank on rank.agency_id =ag.agency_id and rank.name = r.filters::json#>>'{0, value,0}'
            WHERE rank.id=%s
            ''',
            [self.id],
        )

    @transaction.atomic(using='bms')
    def get_or_create_role(self, propagate=True):
        """Get or create a role that matches this rank

        :param propagage: When true, make sure that there is a matching security role, group, etc

        Ranks, Roles, Groups and individuals have an awkward relationship. Many legacy functionalities
        use groups. Groups look for users with a role of a given name through a text lookup. So for a rank
        to function correctly as a role, there must be:
            * BenchmarkRole
            * Group
            * Rule
            * Group Rule
            * Agency Group
        And for good measure there should also be the new security.role
        """
        role, created = BenchmarkRole.objects.get_or_create(
            agency=self.agency,
            name=self.name,
            defaults={
                'description': f"Role that matches rank {self}",
                'public': True,
                'is_choosable': True,
            },
        )
        if created:
            log.info("Created BenchmarkRole %s to match Rank %d", role, self.id)

        if propagate:
            security_role, sec_created = role.get_or_create_security_role()
            group, group_created = role.get_or_create_group()
        return role, created


class RankHierarchy(models.Model):
    agency = models.ForeignKey(Agency, models.DO_NOTHING)
    rank = models.ForeignKey(Rank, models.DO_NOTHING)
    parent_rank = models.ForeignKey(
        Rank, models.DO_NOTHING, related_name='rank_children_set'
    )

    class Meta:
        managed = False
        db_table = 'rank_hierarchy'


class RankHistory(models.Model):
    user = models.ForeignKey(BenchmarkUser, models.DO_NOTHING)
    rank = models.ForeignKey(Rank, models.DO_NOTHING)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'rank_history'
