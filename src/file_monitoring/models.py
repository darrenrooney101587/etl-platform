"""Domain models for file monitoring."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Dict, List, Optional


class CadenceType(str, Enum):
    """Supported cadence types for monitored streams."""

    DAILY_CUTOFF = "DAILY_CUTOFF"
    MAX_GAP = "MAX_GAP"
    FIXED_SCHEDULE = "FIXED_SCHEDULE"
    BUSINESS_DAY_DAILY_CUTOFF = "BUSINESS_DAY_DAILY_CUTOFF"
    AD_HOC = "AD_HOC"


class StreamStatus(str, Enum):
    """Operational status for a stream."""

    OK = "OK"
    DUE_SOON = "DUE_SOON"
    OVERDUE = "OVERDUE"
    UNKNOWN = "UNKNOWN"


class Severity(str, Enum):
    """Severity levels for alert routing."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AckStatus(str, Enum):
    """Acknowledgement lifecycle for alerts."""

    NONE = "none"
    ACKED = "acked"
    SNOOZED = "snoozed"


@dataclass
class EscalationPolicy:
    """Escalation controls for alerting."""

    realert_minutes: int = 60
    escalate_after_minutes: int = 180


@dataclass
class Expectation:
    """Expectation configuration for a monitored stream."""

    client_id: str
    stream_id: str
    s3_bucket: str
    s3_prefix: str
    timezone: Optional[str]
    cadence_type: CadenceType
    optional_pattern: Optional[str] = None
    cutoff_time_local: Optional[time] = None
    grace_minutes: int = 0
    max_gap_minutes: Optional[int] = None
    active_start_local: Optional[time] = None
    active_end_local: Optional[time] = None
    active_days_of_week: Optional[List[int]] = None
    alert_channels: List[str] = field(default_factory=list)
    severity: Severity = Severity.MEDIUM
    escalation_policy: EscalationPolicy = field(default_factory=EscalationPolicy)
    maintenance_windows: Optional[List[str]] = None
    holiday_calendar: Optional[str] = None
    allow_snooze: bool = True

    def validate(self) -> None:
        """Validate the expectation payload against required rules."""
        if self.cadence_type != CadenceType.AD_HOC and not self.timezone:
            raise ValueError("Timezone is required for non-AD_HOC expectations")
        if not self.s3_prefix:
            raise ValueError("s3_prefix must be provided")
        if self.cadence_type == CadenceType.DAILY_CUTOFF and not self.cutoff_time_local:
            raise ValueError("cutoff_time_local required for DAILY_CUTOFF")
        if self.cadence_type == CadenceType.MAX_GAP and not self.max_gap_minutes:
            raise ValueError("max_gap_minutes required for MAX_GAP")
        if self.active_days_of_week:
            for day in self.active_days_of_week:
                if day < 0 or day > 6:
                    raise ValueError("active_days_of_week must be between 0 (Mon) and 6 (Sun)")


@dataclass
class StreamState:
    """Per-stream durable state."""

    client_id: str
    stream_id: str
    last_seen_at_utc: Optional[datetime] = None
    last_seen_key: Optional[str] = None
    last_seen_etag_or_version: Optional[str] = None
    computed_next_due_at_utc: Optional[datetime] = None
    computed_overdue_at_utc: Optional[datetime] = None
    status: StreamStatus = StreamStatus.UNKNOWN
    alert_state: Dict[str, Optional[str]] = field(default_factory=lambda: {
        "last_alert_at_utc": None,
        "open_alert_id": None,
        "ack_status": AckStatus.NONE.value,
        "ack_until_utc": None,
        "escalation_level": 0,
    })
    updated_at_utc: Optional[datetime] = None


@dataclass
class DeliveryEvent:
    """Append-only record of deliveries."""

    event_id: str
    client_id: str
    stream_id: str
    bucket: str
    key: str
    event_time_utc: datetime
    received_time_utc: datetime
    event_source: str
    raw_event: Dict
    qualified: bool
    disqualification_reason: Optional[str] = None


@dataclass
class AlertEvent:
    """Persisted alert lifecycle entry."""

    alert_id: str
    client_id: str
    stream_id: str
    triggered_at: datetime
    resolved_at: Optional[datetime]
    severity: Severity
    message: str
    recipients: List[str]
    escalation_level: int = 0
