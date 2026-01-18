from django.db import models
import uuid

from etl_core.models.apps.bms.models.benchmark_user import BenchmarkUser


class KmiCourse(models.Model):
    format_name = models.CharField(max_length=255, blank=True, null=True)
    created_date = models.DateTimeField(blank=True, null=True)
    # This field type is a guess.
    languages = models.TextField(blank=True, null=True)
    name = models.CharField(max_length=128)
    description = models.CharField(max_length=255, blank=True, null=True)
    provider_course_no = models.CharField(max_length=255, blank=True, null=True)
    published_date = models.DateTimeField(blank=True, null=True)
    updated_date = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    kmi_id = models.IntegerField(blank=True, null=True)

    def __str__(self) -> str:
        return self.name

    class Meta:
        managed = False
        db_table = 'kmi_course'


class KmiCourseSession(models.Model):
    kmi_course = models.ForeignKey(KmiCourse, models.DO_NOTHING, blank=True, null=True)
    attend_capacity = models.IntegerField(blank=True, null=True)
    created_date = models.DateTimeField(blank=True, null=True)
    description = models.CharField(max_length=255, blank=True, null=True)
    instructor = models.CharField(max_length=255, blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    registration_deadline = models.DateTimeField(blank=True, null=True)
    updated_date = models.DateTimeField(blank=True, null=True)
    schedule_date = models.DateTimeField(blank=True, null=True)
    seats_allocated = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'kmi_course_session'


class KmiPullConfiguration(models.Model):
    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    kmi_pull_type = models.CharField(max_length=50, null=True, blank=True)
    last_run_date = models.DateTimeField(blank=True, null=True)
    reload = models.BooleanField(default=False)
    run_status = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'kmi_pull_configuration'


class KmiRegistration(models.Model):
    user = models.ForeignKey('KmiUser', models.DO_NOTHING)
    course = models.ForeignKey(KmiCourse, models.DO_NOTHING, blank=True, null=True)
    approved_by = models.ForeignKey(
        'KmiUser',
        models.DO_NOTHING,
        db_column='approved_by',
        blank=True,
        null=True,
        related_name='kmiregistration_approved_set',
    )
    declined_by = models.ForeignKey(
        'KmiUser',
        models.DO_NOTHING,
        db_column='declined_by',
        blank=True,
        null=True,
        related_name='kmiregistration_declined_set',
    )
    approved_date = models.DateTimeField(blank=True, null=True)
    certificate_type = models.CharField(max_length=255, blank=True, null=True)
    completion_date = models.DateTimeField(blank=True, null=True)
    created_date = models.DateTimeField(blank=True, null=True)
    declined_date = models.DateTimeField(blank=True, null=True)
    evaluation_completed = models.BooleanField(blank=True, null=True)
    expiration_date = models.DateTimeField(blank=True, null=True)
    initial_launch_date = models.DateTimeField(blank=True, null=True)
    last_launch_date = models.DateTimeField(blank=True, null=True)
    post_assessment_percentage = models.DecimalField(
        max_digits=65535, decimal_places=65535, blank=True, null=True
    )
    pre_assessment_percentage = models.DecimalField(
        max_digits=65535, decimal_places=65535, blank=True, null=True
    )
    post_assessment_points = models.IntegerField(blank=True, null=True)
    pre_assessment_points = models.IntegerField(blank=True, null=True)
    registration_date = models.DateTimeField(blank=True, null=True)
    target_completion_date = models.DateTimeField(blank=True, null=True)
    updated_date = models.DateTimeField(blank=True, null=True)
    evaluation_id = models.IntegerField(blank=True, null=True)
    post_assessment_id = models.IntegerField(blank=True, null=True)
    pre_assessment_id = models.IntegerField(blank=True, null=True)
    pre_assessment = models.CharField(max_length=255, blank=True, null=True)
    evaluation = models.CharField(max_length=255, blank=True, null=True)
    post_assessment = models.CharField(max_length=255, blank=True, null=True)
    status_name = models.CharField(max_length=255, blank=True, null=True)
    status_id = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'kmi_registration'


class KmiUser(models.Model):
    benchmark_user = models.ForeignKey(
        BenchmarkUser,
        models.DO_NOTHING,
        blank=True,
        null=True,
        db_column='benchmark_id',
    )
    created_date = models.DateTimeField(blank=True, null=True)
    email = models.CharField(max_length=255)
    first_name = models.CharField(max_length=128)
    last_name = models.CharField(max_length=128)
    time_zone_name = models.CharField(max_length=128)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    kmi_id = models.IntegerField(blank=True, null=True)

    def __str__(self) -> str:
        return self.benchmark_user.username if self.benchmark_user else str(self.kmi_id)

    class Meta:
        managed = False
        db_table = 'kmi_user'
