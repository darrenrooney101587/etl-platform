"""Minimal FastAPI admin surface for CRUD and state inspection."""
from __future__ import annotations

import os
from datetime import datetime, time, timedelta, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .arrival_consumer import ArrivalConsumer
from .mock_data import load_mock_data
from .models import CadenceType, Expectation, StreamState
from .sweeper import Sweeper
from .stores import (
    AlertEventStore,
    DeliveryEventStore,
    ExpectationStore,
    InMemoryAlertEventStore,
    InMemoryDeliveryEventStore,
    InMemoryExpectationStore,
    InMemoryStreamStateStore,
    StreamStateStore,
)

app = FastAPI(title="File Delivery Monitoring")
expectations: ExpectationStore = InMemoryExpectationStore()
states: StreamStateStore = InMemoryStreamStateStore()
delivery_events: DeliveryEventStore = InMemoryDeliveryEventStore()
alerts: AlertEventStore = InMemoryAlertEventStore()
consumer = ArrivalConsumer(expectations, states, delivery_events)
sweeper = Sweeper(expectations, states, alerts)


@app.on_event("startup")
def _seed_mock_data_if_requested() -> None:
    """Auto-load mock expectations/events when enabled for local demos."""
    if os.getenv("LOAD_MOCK_DATA", "").lower() in {"1", "true", "yes", "on"}:
        load_mock_data(expectations, states, delivery_events, alerts, consumer, sweeper)


class ExpectationPayload(BaseModel):
    client_id: str
    stream_id: str
    s3_bucket: str
    s3_prefix: str
    timezone: Optional[str]
    cadence_type: CadenceType
    optional_pattern: Optional[str] = None
    cutoff_time_local: Optional[str] = None
    grace_minutes: int = 0
    max_gap_minutes: Optional[int] = None
    active_start_local: Optional[str] = None
    active_end_local: Optional[str] = None
    active_days_of_week: Optional[List[int]] = None
    alert_channels: List[str] = Field(default_factory=list)


class ManualActionPayload(BaseModel):
    ack_until_utc: Optional[datetime] = None
    snooze_until_utc: Optional[datetime] = None


@app.post("/expectations")
def create_expectation(payload: ExpectationPayload) -> Expectation:
    cutoff_time = None
    if payload.cutoff_time_local:
        hour, minute = map(int, payload.cutoff_time_local.split(":"))
        cutoff_time = time(hour, minute)
    active_start = None
    active_end = None

    if payload.active_start_local:
        hour, minute = map(int, payload.active_start_local.split(":"))
        active_start = time(hour, minute)
    if payload.active_end_local:
        hour, minute = map(int, payload.active_end_local.split(":"))
        active_end = time(hour, minute)
    expectation = Expectation(
        client_id=payload.client_id,
        stream_id=payload.stream_id,
        s3_bucket=payload.s3_bucket,
        s3_prefix=payload.s3_prefix,
        timezone=payload.timezone,
        cadence_type=payload.cadence_type,
        optional_pattern=payload.optional_pattern,
        cutoff_time_local=cutoff_time,
        grace_minutes=payload.grace_minutes,
        max_gap_minutes=payload.max_gap_minutes,
        active_start_local=active_start,
        active_end_local=active_end,
        active_days_of_week=payload.active_days_of_week,
        alert_channels=payload.alert_channels,
    )
    expectation.validate()
    expectations.upsert(expectation)
    return expectation


@app.get("/expectations")
def list_expectations() -> List[Expectation]:
    return expectations.list()


@app.get("/state")
def list_state() -> List[StreamState]:
    return list(states.list())


@app.post("/manual/{client_id}/{stream_id}")
def manual_ack(client_id: str, stream_id: str, payload: ManualActionPayload) -> StreamState:
    state = states.get(client_id, stream_id)
    if not state:
        raise HTTPException(status_code=404, detail="state not found")
    if payload.snooze_until_utc:
        state.alert_state["ack_status"] = "snoozed"
        state.alert_state["ack_until_utc"] = payload.snooze_until_utc
    elif payload.ack_until_utc:
        state.alert_state["ack_status"] = "acked"
        state.alert_state["ack_until_utc"] = payload.ack_until_utc
    else:
        state.alert_state["ack_status"] = "acked"
        state.alert_state["ack_until_utc"] = datetime.now(timezone.utc) + timedelta(hours=1)  # type: ignore[name-defined]
    states.upsert(state)
    return state


@app.post("/sweeper/run")
def run_sweeper() -> List[dict]:
    alerts_emitted = sweeper.run()
    return [alert.__dict__ for alert in alerts_emitted]


@app.post("/ingest")
def ingest_event(event: dict) -> dict:
    events = consumer.process(event)
    return {"processed": len(events)}


@app.post("/mock/reseed")
def reseed_mock_data() -> dict:
    """Reload mock expectations/events; useful for local testing."""
    load_mock_data(expectations, states, delivery_events, alerts, consumer, sweeper)
    return {"expectations": len(expectations.list())}


@app.get("/alerts/{client_id}/{stream_id}")
def list_alerts(client_id: str, stream_id: str) -> List[dict]:
    return [alert.__dict__ for alert in alerts.list(client_id, stream_id)]
