from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils.timezone import now

from etl_database_schema.apps.bms.models import Agency


class LoginAttempt(models.Model):
    username = models.CharField(max_length=255)
    ip_address = models.GenericIPAddressField()
    attempt_time = models.DateTimeField(auto_now_add=True)
    success = models.BooleanField(default=False)

    @classmethod
    def get_failed_attempts(cls, username, ip):
        """Returns the number of failed login attempts for a user + IP within the lockout window."""
        lockout_window = now() - timedelta(minutes=5)
        return cls.objects.filter(
            username=username,
            ip_address=ip,
            success=False,
            attempt_time__gte=lockout_window,
        ).count()

    @classmethod
    def is_locked_out(cls, username, ip, failure_limit=3):
        """Checks if the user is currently locked out."""
        return cls.get_failed_attempts(username, ip) >= failure_limit

    @classmethod
    def record_attempt(cls, username, ip, success):
        cls.objects.create(username=username, ip_address=ip, success=success)

    @classmethod
    def clear_attempts(cls, username, ip):
        cls.objects.filter(username=username, ip_address=ip, success=False).delete()

    class Meta:
        managed = True
        verbose_name = "Login Attempt"
        verbose_name_plural = "Login Attempts"

class UserFileMonitoringPreference(models.Model):
    """
    User preferences for file monitoring dashboard.

    Modeled after UserAgency, this stores which agencies a user wants to monitor
    for file monitoring purposes.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='file_monitoring_preference',
    )
    show_all_agencies = models.BooleanField(
        default=True,
        help_text="If True, user sees all agencies. If False, only selected agencies.",
    )
    selected_agency_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="List of agency IDs the user wants to monitor",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def set_selected_agencies(self, agency_ids: list[int]) -> None:
        """
        Set the selected agency IDs.

        :param agency_ids: List of agency IDs to monitor
        :type agency_ids: list[int]
        :rtype: None
        """
        self.selected_agency_ids = agency_ids

    def get_selected_agencies(self) -> list[int]:
        """
        Get the list of selected agency IDs.

        :return: List of agency IDs
        :rtype: list[int]
        """
        return self.selected_agency_ids or []

    @property
    def agencies(self):
        """
        Get Agency objects for selected agency IDs.

        :return: QuerySet of Agency objects
        :rtype: QuerySet
        """
        if self.selected_agency_ids:
            return Agency.objects.filter(id__in=self.selected_agency_ids)
        return Agency.objects.none()

    def __str__(self) -> str:
        """String representation of the preference."""
        mode = (
            "All Agencies"
            if self.show_all_agencies
            else f"{len(self.get_selected_agencies())} Selected"
        )
        return f"{self.user.username} - {mode}"

    class Meta:
        managed = True
        verbose_name = "File Monitoring Preference"
        verbose_name_plural = "File Monitoring Preferences"


class SeederMonitoringPreference(models.Model):
    """
    User preferences for seeder monitoring dashboard.
    Stores which agencies a user wants to monitor.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='seeder_monitoring_preference',
    )
    show_all_agencies = models.BooleanField(
        default=True,
        help_text="If True, user sees all agencies. If False, only selected agencies.",
    )
    selected_agency_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="List of agency IDs the user wants to monitor",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def set_selected_agencies(self, agency_ids: list[int]) -> None:
        """
        Set the selected agency IDs.

        :param agency_ids: List of agency IDs to monitor
        :type agency_ids: list[int]
        :rtype: None
        """
        self.selected_agency_ids = agency_ids

    def get_selected_agencies(self) -> list[int]:
        """
        Get the list of selected agency IDs.

        :return: List of agency IDs
        :rtype: list[int]
        """
        return self.selected_agency_ids or []

    @property
    def agencies(self):
        """
        Get Agency objects for selected agency IDs.

        :return: QuerySet of Agency objects
        :rtype: QuerySet
        """
        if self.selected_agency_ids:
            return Agency.objects.filter(id__in=self.selected_agency_ids)
        return Agency.objects.none()

    def __str__(self) -> str:
        """String representation of the preference."""
        mode = (
            "All Agencies"
            if self.show_all_agencies
            else f"{len(self.get_selected_agencies())} Selected"
        )
        return f"{self.user.username} - {mode}"

    class Meta:
        managed = True
        verbose_name = "Seeder Monitoring Preference"
        verbose_name_plural = "Seeder Monitoring Preferences"


class ETLMonitoringPreference(models.Model):
    """
    User preferences for ETL monitoring dashboard.
    Stores which agencies a user wants to monitor.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='etl_monitoring_preference',
    )
    show_all_agencies = models.BooleanField(
        default=True,
        help_text="If True, user sees all agencies. If False, only selected agencies.",
    )
    selected_agency_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="List of agency IDs the user wants to monitor",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def set_selected_agencies(self, agency_ids: list[int]) -> None:
        """
        Set the selected agency IDs.

        :param agency_ids: List of agency IDs to monitor
        :type agency_ids: list[int]
        :rtype: None
        """
        self.selected_agency_ids = agency_ids

    def get_selected_agencies(self) -> list[int]:
        """
        Get the list of selected agency IDs.

        :return: List of agency IDs
        :rtype: list[int]
        """
        return self.selected_agency_ids or []

    @property
    def agencies(self):
        """
        Get Agency objects for selected agency IDs.

        :return: QuerySet of Agency objects
        :rtype: QuerySet
        """
        if self.selected_agency_ids:
            return Agency.objects.filter(id__in=self.selected_agency_ids)
        return Agency.objects.none()

    def __str__(self) -> str:
        """String representation of the preference."""
        mode = (
            "All Agencies"
            if self.show_all_agencies
            else f"{len(self.get_selected_agencies())} Selected"
        )
        return f"{self.user.username} - ETL - {mode}"

    class Meta:
        managed = True
        verbose_name = "ETL Monitoring Preference"
        verbose_name_plural = "ETL Monitoring Preferences"
