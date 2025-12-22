"""Utilities to seed in-memory stores with mock expectations and arrivals."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone, time
from typing import Iterable

from .arrival_consumer import ArrivalConsumer
from .models import CadenceType, Expectation, Severity
from .sweeper import Sweeper
from .stores import AlertEventStore, DeliveryEventStore, ExpectationStore, StreamStateStore


def load_mock_data(
    expectations: ExpectationStore,
    states: StreamStateStore,
    deliveries: DeliveryEventStore,
    alerts: AlertEventStore,
    consumer: ArrivalConsumer,
    sweeper: Sweeper,
    now: datetime | None = None,
) -> None:
    """Populate stores with representative expectations and arrivals."""
    now_utc = now or datetime.now(timezone.utc)
    demo_expectations: Iterable[Expectation] = (
        Expectation(
            client_id="acme",
            stream_id="daily-reports",
            s3_bucket="sample-ingest",
            s3_prefix="acme/reports/",
            timezone="America/New_York",
            cadence_type=CadenceType.DAILY_CUTOFF,
            cutoff_time_local=time(12, 0),
            grace_minutes=30,
            alert_channels=["alerts@acme.test"],
            severity=Severity.MEDIUM,
        ),
        Expectation(
            client_id="acme",
            stream_id="events-hi-freq",
            s3_bucket="sample-ingest",
            s3_prefix="acme/events/",
            timezone="America/New_York",
            cadence_type=CadenceType.MAX_GAP,
            max_gap_minutes=60,
            active_start_local=time(0, 0),
            active_end_local=time(23, 59),
            grace_minutes=10,
            alert_channels=["alerts@acme.test"],
            severity=Severity.HIGH,
        ),
    )

    for exp in demo_expectations:
        exp.validate()
        expectations.upsert(exp)

    suffix = int(now_utc.timestamp())
    sample_events = [
        {
            "Records": [
                {
                    "eventTime": (now_utc - timedelta(hours=2)).isoformat(),
                    "eventID": f"evt-1-{suffix}",
                    "s3": {
                        "bucket": {"name": "sample-ingest"},
                        "object": {"key": "acme/reports/report_20240501.csv", "eTag": "etag-1", "versionId": "1"},
                    },
                }
            ]
        },
        {
            "Records": [
                {
                    "eventTime": (now_utc - timedelta(minutes=130)).isoformat(),
                    "eventID": f"evt-2-{suffix}",
                    "s3": {
                        "bucket": {"name": "sample-ingest"},
                        "object": {"key": "acme/events/part-0001.json", "eTag": "etag-2", "versionId": "1"},
                    },
                }
            ]
        },
    ]

    for event in sample_events:
        consumer.process(event)

    # Run sweeper once to demonstrate overdue status/escalation.
    sweeper.run(now=now_utc)
