"""Arrival consumer for S3 ObjectCreated notifications."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List
from zoneinfo import ZoneInfo

from .models import CadenceType, DeliveryEvent, Expectation, StreamState, StreamStatus
from .sla import compute_schedule
from .stores import DeliveryEventStore, ExpectationStore, StreamStateStore


IGNORED_SUFFIXES = {".tmp", "_COPYING_"}


def _is_temp_key(key: str) -> bool:
    return any(key.endswith(suffix) for suffix in IGNORED_SUFFIXES)


def _matches_expectation(key: str, expectation: Expectation) -> bool:
    if not key.startswith(expectation.s3_prefix):
        return False
    if expectation.optional_pattern:
        return re.search(expectation.optional_pattern, key) is not None
    return True


def _extract_event_time(event: Dict) -> datetime:
    if "eventTime" in event:
        return datetime.fromisoformat(event["eventTime"].replace("Z", "+00:00"))
    return datetime.now(timezone.utc)


def _candidate_expectations(key: str, bucket: str, store: ExpectationStore) -> Iterable[Expectation]:
    for expectation in store.list():
        if expectation.s3_bucket == bucket and key.startswith(expectation.s3_prefix):
            yield expectation


class ArrivalConsumer:
    """Consumes S3 events and updates state."""

    def __init__(
        self,
        expectation_store: ExpectationStore,
        state_store: StreamStateStore,
        delivery_event_store: DeliveryEventStore,
    ) -> None:
        self.expectation_store = expectation_store
        self.state_store = state_store
        self.delivery_event_store = delivery_event_store

    def process(self, event: Dict) -> List[DeliveryEvent]:
        """Process a raw S3 event."""
        processed_events: List[DeliveryEvent] = []
        records = event.get("Records", [event])
        for record in records:
            bucket = record.get("s3", {}).get("bucket", {}).get("name") or record.get("bucket")
            key = record.get("s3", {}).get("object", {}).get("key") or record.get("key")
            if not bucket or not key:
                continue
            if _is_temp_key(key):
                continue
            event_time_utc = _extract_event_time(record)
            candidates = list(_candidate_expectations(key, bucket, self.expectation_store))
            for expectation in candidates:
                qualified = _matches_expectation(key, expectation)
                disqualification = None if qualified else "Pattern mismatch"
                delivery_event = DeliveryEvent(
                    event_id=record.get("eventID") or f"{bucket}:{key}:{record.get('s3', {}).get('object', {}).get('versionId', '')}",
                    client_id=expectation.client_id,
                    stream_id=expectation.stream_id,
                    bucket=bucket,
                    key=key,
                    event_time_utc=event_time_utc,
                    received_time_utc=datetime.now(timezone.utc),
                    event_source="S3",
                    raw_event=json.loads(json.dumps(record)),
                    qualified=qualified,
                    disqualification_reason=disqualification,
                )
                self.delivery_event_store.append(delivery_event)
                processed_events.append(delivery_event)
                if not qualified:
                    continue
                self._update_state_on_arrival(expectation, delivery_event)
        return processed_events

    def _update_state_on_arrival(self, expectation: Expectation, delivery_event: DeliveryEvent) -> None:
        state = self.state_store.get(expectation.client_id, expectation.stream_id) or StreamState(
            client_id=expectation.client_id, stream_id=expectation.stream_id
        )
        state.last_seen_at_utc = delivery_event.event_time_utc
        state.last_seen_key = delivery_event.key
        state.last_seen_etag_or_version = delivery_event.raw_event.get("s3", {}).get("object", {}).get("eTag")
        if expectation.cadence_type == CadenceType.DAILY_CUTOFF:
            tz = ZoneInfo(expectation.timezone) if expectation.timezone else timezone.utc
            arrival_local = delivery_event.event_time_utc.astimezone(tz)
            due_date_local = arrival_local.date() + timedelta(days=1)
            next_due = datetime.combine(due_date_local, expectation.cutoff_time_local, tzinfo=tz)
            overdue = next_due + timedelta(minutes=expectation.grace_minutes)
            next_due = next_due.astimezone(timezone.utc)
            overdue = overdue.astimezone(timezone.utc)
        else:
            next_due, overdue = compute_schedule(expectation, delivery_event.event_time_utc, delivery_event.event_time_utc)
        state.computed_next_due_at_utc = next_due
        state.computed_overdue_at_utc = overdue
        state.status = StreamStatus.OK
        state.alert_state["open_alert_id"] = None
        state.alert_state["ack_status"] = state.alert_state.get("ack_status") or "none"
        self.state_store.upsert(state)
