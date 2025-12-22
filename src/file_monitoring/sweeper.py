"""Scheduled sweeper that marks overdue streams and emits alerts."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid
from typing import List, Optional

from .models import AckStatus, AlertEvent, Severity, StreamState, StreamStatus
from .sla import compute_schedule
from .stores import AlertEventStore, ExpectationStore, StreamStateStore


class Sweeper:
    """Periodically evaluates lateness across streams."""

    def __init__(
        self,
        expectation_store: ExpectationStore,
        state_store: StreamStateStore,
        alert_store: AlertEventStore,
    ) -> None:
        self.expectation_store = expectation_store
        self.state_store = state_store
        self.alert_store = alert_store

    def run(self, now: Optional[datetime] = None) -> List[AlertEvent]:
        """Evaluate all streams and emit alerts when overdue."""
        now_utc = now or datetime.now(timezone.utc)
        emitted: List[AlertEvent] = []
        for expectation in self.expectation_store.list():
            state = self.state_store.get(expectation.client_id, expectation.stream_id) or StreamState(
                client_id=expectation.client_id, stream_id=expectation.stream_id
            )
            if expectation.cadence_type.name == "AD_HOC":
                continue
            if state.computed_overdue_at_utc is None:
                next_due, overdue = compute_schedule(expectation, now_utc, state.last_seen_at_utc)
                state.computed_next_due_at_utc = next_due
                state.computed_overdue_at_utc = overdue
                state.status = StreamStatus.UNKNOWN
                self.state_store.upsert(state)
            snoozed_until = state.alert_state.get("ack_until_utc")
            if snoozed_until and isinstance(snoozed_until, datetime) and snoozed_until > now_utc:
                continue
            ack_status = state.alert_state.get("ack_status")
            open_alert = state.alert_state.get("open_alert_id")
            last_alert_at = state.alert_state.get("last_alert_at_utc")
            if (
                state.computed_overdue_at_utc
                and state.computed_overdue_at_utc <= now_utc
                and state.status != StreamStatus.OVERDUE
            ):
                alert = self._emit_alert(state, expectation, now_utc, escalation_level=0)
                emitted.append(alert)
            elif state.status == StreamStatus.OVERDUE and ack_status != AckStatus.ACKED.value:
                policy = expectation.escalation_policy
                if last_alert_at and isinstance(last_alert_at, datetime):
                    if last_alert_at + timedelta(minutes=policy.realert_minutes) <= now_utc:
                        next_level = int(state.alert_state.get("escalation_level") or 0) + 1
                        alert = self._emit_alert(state, expectation, now_utc, escalation_level=next_level)
                        emitted.append(alert)
        return emitted

    def _emit_alert(
        self,
        state: StreamState,
        expectation,
        triggered_at: datetime,
        escalation_level: int,
    ) -> AlertEvent:
        alert = AlertEvent(
            alert_id=str(uuid.uuid4()),
            client_id=state.client_id,
            stream_id=state.stream_id,
            triggered_at=triggered_at,
            resolved_at=None,
            severity=expectation.severity,
            message=self._build_message(expectation, state, escalation_level),
            recipients=expectation.alert_channels,
            escalation_level=escalation_level,
        )
        state.status = StreamStatus.OVERDUE
        state.alert_state["open_alert_id"] = alert.alert_id
        state.alert_state["last_alert_at_utc"] = triggered_at
        state.alert_state["escalation_level"] = escalation_level
        self.state_store.upsert(state)
        self.alert_store.append(alert)
        return alert

    @staticmethod
    def _build_message(expectation, state: StreamState, escalation_level: int) -> str:
        next_due = state.computed_next_due_at_utc.isoformat() if state.computed_next_due_at_utc else "unknown"
        overdue = state.computed_overdue_at_utc.isoformat() if state.computed_overdue_at_utc else "unknown"
        return (
            f"Stream {state.client_id}/{state.stream_id} missed expectation {expectation.cadence_type.name}. "
            f"Next due at {next_due}, overdue at {overdue}. Escalation level {escalation_level}."
        )
