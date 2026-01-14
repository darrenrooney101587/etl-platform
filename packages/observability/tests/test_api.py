"""API integration tests using Django test client."""
from __future__ import annotations

import json

from django.test import Client

from observability.tests.base import ObservabilityTestCase


class ApiTests(ObservabilityTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client = Client()
        self.payload = {
            "tenant_id": "tenant-api",
            "tenant_code": "TEN-A",
            "job_name": "job-api",
            "source": "airflow",
            "signal_type": "job_failed",
            "severity": 2,
            "summary": "api failure",
            "details_json": {"foo": "bar"},
        }

    def test_ingest_and_acknowledge_via_api(self) -> None:
        response = self.client.post("/api/signals", data=json.dumps(self.payload), content_type="application/json")
        self.assertEqual(response.status_code, 201, response.content)
        signal_group_id = response.json()["signal_group_id"]

        ack_resp = self.client.post(
            f"/api/signal-groups/{signal_group_id}/ack",
            data=json.dumps({"actor_user_id": "user-api"}),
            content_type="application/json",
        )
        self.assertEqual(ack_resp.status_code, 200, ack_resp.content)
        self.assertEqual(ack_resp.json()["status"], "acknowledged")

    def test_idempotency_key_reuses_response(self) -> None:
        headers = {"HTTP_IDEMPOTENCY_KEY": "abc123"}
        resp1 = self.client.post("/api/signals", data=json.dumps(self.payload), content_type="application/json", **headers)
        self.assertEqual(resp1.status_code, 201)
        resp2 = self.client.post("/api/signals", data=json.dumps(self.payload), content_type="application/json", **headers)
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp1.json()["signal_group_id"], resp2.json()["signal_group_id"])
