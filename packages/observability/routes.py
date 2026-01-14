"""URL routes for the observability API."""
from __future__ import annotations

from django.urls import path

from observability import api

urlpatterns = [
    path("api/signals", api.ingest_signal, name="ingest_signal"),
    path("api/signal-groups", api.list_signal_groups, name="list_signal_groups"),
    path("api/signal-groups/<uuid:group_id>", api.get_signal_group, name="get_signal_group"),
    path("api/signal-groups/<uuid:group_id>/ack", api.acknowledge_group, name="ack_signal_group"),
    path("api/signal-groups/<uuid:group_id>/snooze", api.snooze_group, name="snooze_signal_group"),
    path("api/signal-groups/<uuid:group_id>/assign", api.assign_group, name="assign_signal_group"),
    path("api/signal-groups/<uuid:group_id>/close", api.close_group, name="close_signal_group"),
    path("api/slack/interactions", api.slack_interactions, name="slack_interactions"),
]
