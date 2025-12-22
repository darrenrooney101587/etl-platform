from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from file_monitoring.models import CadenceType, Expectation
from file_monitoring.sla import compute_daily_cutoff_schedule, compute_max_gap_schedule


def _base_expectation_daily() -> Expectation:
    return Expectation(
        client_id="c1",
        stream_id="s1",
        s3_bucket="bucket",
        s3_prefix="prefix/",
        timezone="America/New_York",
        cadence_type=CadenceType.DAILY_CUTOFF,
        cutoff_time_local=time(12, 0),
        grace_minutes=30,
    )


def test_daily_cutoff_before_cutoff_uses_today():
    expectation = _base_expectation_daily()
    reference = datetime(2024, 1, 10, 15, 0, tzinfo=timezone.utc)  # 10:00 Eastern
    next_due, overdue = compute_daily_cutoff_schedule(expectation, reference)
    assert next_due.astimezone(ZoneInfo("America/New_York")).time() == time(12, 0)
    assert overdue - next_due == timedelta(minutes=30)


def test_daily_cutoff_after_overdue_rolls_forward():
    expectation = _base_expectation_daily()
    reference = datetime(2024, 1, 10, 18, 0, tzinfo=timezone.utc)  # 13:00 Eastern
    next_due, overdue = compute_daily_cutoff_schedule(expectation, reference)
    next_local = next_due.astimezone(ZoneInfo("America/New_York"))
    assert next_local.date().day == 11
    assert next_local.time() == time(12, 0)
    assert overdue - next_due == timedelta(minutes=30)


def _base_expectation_gap() -> Expectation:
    return Expectation(
        client_id="c1",
        stream_id="freq",
        s3_bucket="bucket",
        s3_prefix="freq/",
        timezone="UTC",
        cadence_type=CadenceType.MAX_GAP,
        max_gap_minutes=60,
        active_start_local=time(8, 0),
        active_end_local=time(18, 0),
        grace_minutes=0,
    )


def test_max_gap_inside_window_uses_last_seen():
    expectation = _base_expectation_gap()
    last_seen = datetime(2024, 1, 10, 9, 0, tzinfo=timezone.utc)
    reference = datetime(2024, 1, 10, 10, 5, tzinfo=timezone.utc)
    next_due, overdue = compute_max_gap_schedule(expectation, reference, last_seen)
    assert next_due == datetime(2024, 1, 10, 10, 0, tzinfo=timezone.utc)
    assert overdue == next_due  # no grace


def test_max_gap_before_window_uses_start():
    expectation = _base_expectation_gap()
    reference = datetime(2024, 1, 10, 6, 0, tzinfo=timezone.utc)
    next_due, overdue = compute_max_gap_schedule(expectation, reference, None)
    assert next_due == datetime(2024, 1, 10, 9, 0, tzinfo=timezone.utc)
    assert overdue == next_due
