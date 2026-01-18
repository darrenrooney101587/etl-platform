"""BMS tables and logic

Originally auto-inspected. Logic added to support business rules.
"""

from etl_database_schema.apps.bms.models.action_log import *
from etl_database_schema.apps.bms.models.agency import *
from etl_database_schema.apps.bms.models.attachment import *
from etl_database_schema.apps.bms.models.benchmark_access_token import *
from etl_database_schema.apps.bms.models.benchmark_role import *
from etl_database_schema.apps.bms.models.benchmark_user import *
from etl_database_schema.apps.bms.models.changelog import *
from etl_database_schema.apps.bms.models.client_application import *
from etl_database_schema.apps.bms.models.config import *
from etl_database_schema.apps.bms.models.data_update import *
from etl_database_schema.apps.bms.models.errors import *
from etl_database_schema.apps.bms.models.event import *
from etl_database_schema.apps.bms.models.field import *
from etl_database_schema.apps.bms.models.form import *
from etl_database_schema.apps.bms.models.group import *
from etl_database_schema.apps.bms.models.handler import *
from etl_database_schema.apps.bms.models.imports import *
from etl_database_schema.apps.bms.models.integration import *
from etl_database_schema.apps.bms.models.json import *
from etl_database_schema.apps.bms.models.kmi import *
from etl_database_schema.apps.bms.models.legacy_form_data import *
from etl_database_schema.apps.bms.models.link import *
from etl_database_schema.apps.bms.models.migration import *
from etl_database_schema.apps.bms.models.notification import *
from etl_database_schema.apps.bms.models.oauth import *
from etl_database_schema.apps.bms.models.permission import *
from etl_database_schema.apps.bms.models.rank import *
from etl_database_schema.apps.bms.models.reasons import *
from etl_database_schema.apps.bms.models.report_viewers import *
from etl_database_schema.apps.bms.models.screen import *
from etl_database_schema.apps.bms.models.share import *
from etl_database_schema.apps.bms.models.snapshot import *
from etl_database_schema.apps.bms.models.stats_view import *
from etl_database_schema.apps.bms.models.template import *
from etl_database_schema.apps.bms.models.time_track import *
from etl_database_schema.apps.bms.models.training import *
from etl_database_schema.apps.bms.models.validation import *
from etl_database_schema.apps.bms.models.validation import *
from etl_database_schema.apps.bms.models.vendor import *
from etl_database_schema.apps.bms.models.workflow import *
from etl_database_schema.apps.bms.models.admin_edit_history import *


class FieldToFieldLinkDraft(models.Model):
    """Model to store temporary the field linking configurations"""

    agency_id = models.CharField(max_length=125)
    # Template ID represented as a combination of source and target templates divided by '-',e.g.3-3
    template_id = models.CharField(max_length=125)
    config = models.JSONField()

    class Meta:
        ordering = ["agency_id"]

    def __str__(self):
        return f"{self.agency_id}_{self.template_id}"
