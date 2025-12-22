from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from file_monitoring.arrival_consumer import ArrivalConsumer
from file_monitoring.models import CadenceType, Expectation, StreamStatus
from file_monitoring.sweeper import Sweeper
from file_monitoring.stores import (
    InMemoryAlertEventStore,
    InMemoryDeliveryEventStore,
    InMemoryExpectationStore,
    InMemoryStreamStateStore,
)


def test_daily_overdue_after_grace():
    expectations = InMemoryExpectationStore()
    states = InMemoryStreamStateStore()
    deliveries = InMemoryDeliveryEventStore()
    alerts = InMemoryAlertEventStore()
    consumer = ArrivalConsumer(expectations, states, deliveries)
    sweeper = Sweeper(expectations, states, alerts)

    expectation = Expectation(
        client_id="client1",
        stream_id="daily",
        s3_bucket="bucket",
        s3_prefix="daily/",
        timezone="America/New_York",
        cadence_type=CadenceType.DAILY_CUTOFF,
        cutoff_time_local=time(12, 0),
        grace_minutes=30,
        alert_channels=["ops@example.com"],
    )
    expectations.upsert(expectation)

    arrival_time = datetime(2024, 1, 9, 17, 30, tzinfo=timezone.utc)  # 12:30 Eastern
    consumer.process(
        {
            "eventTime": arrival_time.isoformat(),
            "bucket": "bucket",
            "key": "daily/file_20240109.csv",
            "eventID": "evt1",
        }
    )
    state = states.get("client1", "daily")
    assert state
    # Expected next due Jan 10 12:00 Eastern
    overdue_time = state.computed_overdue_at_utc
    sweep_time = overdue_time + timedelta(minutes=5)  # type: ignore[operator]
    sweeper.run(sweep_time)
    updated = states.get("client1", "daily")
    assert updated.status == StreamStatus.OVERDUE
    assert alerts.list("client1", "daily")


def test_max_gap_overdue_within_active_hours():
    expectations = InMemoryExpectationStore()
    states = InMemoryStreamStateStore()
    deliveries = InMemoryDeliveryEventStore()
    alerts = InMemoryAlertEventStore()
    consumer = ArrivalConsumer(expectations, states, deliveries)
    sweeper = Sweeper(expectations, states, alerts)

    expectation = Expectation(
        client_id="client1",
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
    expectations.upsert(expectation)

    arrival_time = datetime(2024, 1, 10, 9, 0, tzinfo=timezone.utc)
    consumer.process(
        {
            "eventTime": arrival_time.isoformat(),
            "bucket": "bucket",
            "key": "freq/file1.csv",
            "eventID": "evt-gap-1",
        }
    )
    sweep_time = datetime(2024, 1, 10, 10, 5, tzinfo=timezone.utc)
    sweeper.run(sweep_time)
    state = states.get("client1", "freq")
    assert state.status == StreamStatus.OVERDUE
    assert alerts.list("client1", "freq")


def test_duplicate_events_are_idempotent():
    expectations = InMemoryExpectationStore()
    states = InMemoryStreamStateStore()
    deliveries = InMemoryDeliveryEventStore()
    alerts = InMemoryAlertEventStore()
    consumer = ArrivalConsumer(expectations, states, deliveries)
    sweeper = Sweeper(expectations, states, alerts)

    expectation = Expectation(
        client_id="client1",
        stream_id="daily",
        s3_bucket="bucket",
        s3_prefix="daily/",
        timezone="UTC",
        cadence_type=CadenceType.DAILY_CUTOFF,
        cutoff_time_local=time(12, 0),
        grace_minutes=15,
    )
    expectations.upsert(expectation)

    event_payload = {
        "eventTime": datetime(2024, 1, 5, 12, 0, tzinfo=timezone.utc).isoformat(),
        "bucket": "bucket",
        "key": "daily/file.csv",
        "eventID": "dupe1",
    }
    consumer.process(event_payload)
    consumer.process(event_payload)
    events = deliveries.list("client1", "daily")
    assert len(events) == 1
    state = states.get("client1", "daily")
    assert state.status == StreamStatus.OK
