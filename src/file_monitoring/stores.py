"""Persistence interfaces and in-memory implementations."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple

from .models import AlertEvent, DeliveryEvent, Expectation, StreamState


class ExpectationStore:
    """Interface for expectation persistence."""

    def upsert(self, expectation: Expectation) -> None:
        raise NotImplementedError

    def get(self, client_id: str, stream_id: str) -> Optional[Expectation]:
        raise NotImplementedError

    def list(self, client_id: Optional[str] = None) -> List[Expectation]:
        raise NotImplementedError


class InMemoryExpectationStore(ExpectationStore):
    """In-memory expectation store suitable for tests and local runs."""

    def __init__(self) -> None:
        self._data: Dict[Tuple[str, str], Expectation] = {}

    def upsert(self, expectation: Expectation) -> None:
        expectation.validate()
        key = (expectation.client_id, expectation.stream_id)
        self._data[key] = expectation

    def get(self, client_id: str, stream_id: str) -> Optional[Expectation]:
        return self._data.get((client_id, stream_id))

    def list(self, client_id: Optional[str] = None) -> List[Expectation]:
        if client_id is None:
            return list(self._data.values())
        return [exp for exp in self._data.values() if exp.client_id == client_id]


class StreamStateStore:
    """Interface for persisted stream state."""

    def upsert(self, state: StreamState) -> None:
        raise NotImplementedError

    def get(self, client_id: str, stream_id: str) -> Optional[StreamState]:
        raise NotImplementedError

    def list(self) -> Iterable[StreamState]:
        raise NotImplementedError


class InMemoryStreamStateStore(StreamStateStore):
    """In-memory state persistence."""

    def __init__(self) -> None:
        self._data: Dict[Tuple[str, str], StreamState] = {}

    def upsert(self, state: StreamState) -> None:
        state.updated_at_utc = datetime.now(timezone.utc)
        self._data[(state.client_id, state.stream_id)] = replace(state)

    def get(self, client_id: str, stream_id: str) -> Optional[StreamState]:
        state = self._data.get((client_id, stream_id))
        return replace(state) if state else None

    def list(self) -> Iterable[StreamState]:
        return [replace(state) for state in self._data.values()]


class DeliveryEventStore:
    """Interface for append-only delivery event log."""

    def append(self, event: DeliveryEvent) -> None:
        raise NotImplementedError

    def list(self, client_id: str, stream_id: str) -> List[DeliveryEvent]:
        raise NotImplementedError


class InMemoryDeliveryEventStore(DeliveryEventStore):
    """In-memory event log with de-duplication support."""

    def __init__(self) -> None:
        self._events: List[DeliveryEvent] = []
        self._seen_ids: set[str] = set()

    def append(self, event: DeliveryEvent) -> None:
        if event.event_id in self._seen_ids:
            return
        self._events.append(event)
        self._seen_ids.add(event.event_id)

    def list(self, client_id: str, stream_id: str) -> List[DeliveryEvent]:
        return [event for event in self._events if event.client_id == client_id and event.stream_id == stream_id]


class AlertEventStore:
    """Interface for alert history."""

    def append(self, alert: AlertEvent) -> None:
        raise NotImplementedError

    def resolve(self, alert_id: str, resolved_at: datetime) -> None:
        raise NotImplementedError

    def list(self, client_id: str, stream_id: str) -> List[AlertEvent]:
        raise NotImplementedError


class InMemoryAlertEventStore(AlertEventStore):
    """In-memory alert store with simple resolution support."""

    def __init__(self) -> None:
        self._alerts: Dict[str, AlertEvent] = {}

    def append(self, alert: AlertEvent) -> None:
        self._alerts[alert.alert_id] = alert

    def resolve(self, alert_id: str, resolved_at: datetime) -> None:
        alert = self._alerts.get(alert_id)
        if alert:
            self._alerts[alert_id] = replace(alert, resolved_at=resolved_at)

    def list(self, client_id: str, stream_id: str) -> List[AlertEvent]:
        return [alert for alert in self._alerts.values() if alert.client_id == client_id and alert.stream_id == stream_id]
