"""SLA computation utilities for different cadence types."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from .models import CadenceType, Expectation


def _combine_local(date_obj, time_obj: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(date_obj, time_obj, tzinfo=tz)


def _apply_grace(dt: datetime, grace_minutes: int) -> datetime:
    return dt + timedelta(minutes=grace_minutes)


def compute_daily_cutoff_schedule(expectation: Expectation, reference_utc: datetime) -> Tuple[datetime, datetime]:
    """Compute next due and overdue timestamps for a daily cutoff stream.

    :param expectation: The stream expectation.
    :type expectation: Expectation
    :param reference_utc: Reference timestamp, typically now or arrival time.
    :type reference_utc: datetime
    :returns: Tuple of (computed_next_due_at_utc, computed_overdue_at_utc).
    :rtype: Tuple[datetime, datetime]
    """
    if not expectation.cutoff_time_local or not expectation.timezone:
        raise ValueError("cutoff_time_local and timezone required")
    tz = ZoneInfo(expectation.timezone)
    reference_local = reference_utc.astimezone(tz)
    today_cutoff = _combine_local(reference_local.date(), expectation.cutoff_time_local, tz)
    today_overdue = _apply_grace(today_cutoff, expectation.grace_minutes)
    if reference_local <= today_overdue:
        next_due_local = today_cutoff
    else:
        next_due_local = _combine_local(reference_local.date() + timedelta(days=1), expectation.cutoff_time_local, tz)
    computed_next_due_at_utc = next_due_local.astimezone(timezone.utc)
    computed_overdue_at_utc = _apply_grace(computed_next_due_at_utc, expectation.grace_minutes)
    return computed_next_due_at_utc, computed_overdue_at_utc


def _find_next_active_window(expectation: Expectation, reference_local: datetime) -> Tuple[datetime, datetime]:
    """Find the next active window (start, end) after a reference time."""
    start = expectation.active_start_local or time(0, 0)
    end = expectation.active_end_local or time(23, 59)
    active_days = expectation.active_days_of_week or [0, 1, 2, 3, 4, 5, 6]
    current = reference_local
    for _ in range(8):
        candidate_day = current.date()
        if current.weekday() in active_days:
            window_start = _combine_local(candidate_day, start, reference_local.tzinfo)  # type: ignore[arg-type]
            window_end = _combine_local(candidate_day, end, reference_local.tzinfo)  # type: ignore[arg-type]
            if current <= window_end:
                return window_start, window_end
        current = current + timedelta(days=1)
    raise RuntimeError("Unable to locate next active window")


def compute_max_gap_schedule(expectation: Expectation, reference_utc: datetime, last_seen_at_utc: Optional[datetime]) -> Tuple[datetime, datetime]:
    """Compute next due and overdue for a max-gap stream.

    :param expectation: The stream expectation.
    :type expectation: Expectation
    :param reference_utc: The time to evaluate from, typically now.
    :type reference_utc: datetime
    :param last_seen_at_utc: Timestamp of last arrival, if any.
    :type last_seen_at_utc: Optional[datetime]
    :returns: Tuple of (computed_next_due_at_utc, computed_overdue_at_utc).
    :rtype: Tuple[datetime, datetime]
    """
    if expectation.max_gap_minutes is None or not expectation.timezone:
        raise ValueError("max_gap_minutes and timezone required for MAX_GAP")
    tz = ZoneInfo(expectation.timezone)
    reference_local = reference_utc.astimezone(tz)
    window_start, window_end = _find_next_active_window(expectation, reference_local)

    if reference_local < window_start:
        anchor_local = window_start
    elif reference_local > window_end:
        next_window_start, _ = _find_next_active_window(expectation, reference_local + timedelta(days=1))
        anchor_local = next_window_start
    else:
        if last_seen_at_utc:
            anchor_local = last_seen_at_utc.astimezone(tz)
        else:
            anchor_local = window_start

    next_due_local = anchor_local + timedelta(minutes=expectation.max_gap_minutes)
    computed_next_due_at_utc = next_due_local.astimezone(timezone.utc)
    computed_overdue_at_utc = _apply_grace(computed_next_due_at_utc, expectation.grace_minutes)
    return computed_next_due_at_utc, computed_overdue_at_utc


def compute_schedule(expectation: Expectation, reference_utc: datetime, last_seen_at_utc: Optional[datetime]) -> Tuple[datetime, datetime]:
    """Route to the correct scheduler based on cadence type."""
    if expectation.cadence_type == CadenceType.DAILY_CUTOFF:
        return compute_daily_cutoff_schedule(expectation, reference_utc)
    if expectation.cadence_type == CadenceType.MAX_GAP:
        return compute_max_gap_schedule(expectation, reference_utc, last_seen_at_utc)
    raise NotImplementedError(f"Cadence type {expectation.cadence_type} not implemented")
