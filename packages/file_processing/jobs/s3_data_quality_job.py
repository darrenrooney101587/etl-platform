"""SNS HTTP entrypoint for file_processing.

This CLI runs a simple HTTP server to receive AWS SNS notifications.
It handles:
1. SubscriptionConfirmation: Visits the SubscribeURL to confirm.
2. Notification: Extracts the inner S3 event JSON from the SNS envelope's 'Message'
   field and forwards that S3 event payload to s3_data_quality_job.

Notes:
- When S3 publishes to SNS, SNS delivers an HTTP POST containing an SNS envelope.
  The actual S3 event JSON is in payload['Message'] (usually as a JSON string).
- The s3_data_quality_job expects an AWS-style S3 event (with 'Records'), not the
  outer SNS envelope.

Usage:
    python -m file_processing.cli.sns_main
    # Listens on port 8080 by default. Set PORT env var to change.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional
from urllib.request import urlopen

from file_processing.jobs.s3_data_quality_job import entrypoint

logger = logging.getLogger(__name__)


def _json_loads_maybe(raw: Any) -> Any:
    """Parse a JSON string if needed; otherwise return the value as-is.

    :param raw: Candidate JSON string or object
    :type raw: Any
    :returns: Parsed object or original value
    :rtype: Any
    """
    if isinstance(raw, str):
        return json.loads(raw)
    return raw


def _extract_s3_event_from_sns_envelope(sns_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the S3 event JSON from an SNS HTTP envelope.

    SNS HTTP POST payload (envelope) includes:
      - Type: "Notification"
      - Message: "<json string of S3 event>"  OR sometimes already a dict
    The S3 event JSON should have a top-level "Records" list.

    :param sns_payload: Decoded SNS envelope JSON
    :type sns_payload: Dict[str, Any]
    :returns: Decoded S3 event JSON dict (must include 'Records')
    :rtype: Dict[str, Any]
    :raises ValueError: if Message is missing/unparseable or doesn't resemble an S3 event
    """
    if "Message" not in sns_payload:
        raise ValueError("SNS Notification missing 'Message' field")

    message_obj = _json_loads_maybe(sns_payload["Message"])
    if not isinstance(message_obj, dict):
        raise ValueError(f"Unsupported SNS Message type: {type(message_obj)}")

    # S3 event notifications should contain Records
    if "Records" not in message_obj:
        # Provide a small hint about what we saw (without dumping huge payloads)
        keys = sorted(list(message_obj.keys()))
        raise ValueError(f"Decoded SNS Message does not contain 'Records'. Keys={keys}")

    return message_obj


class SNSRequestHandler(BaseHTTPRequestHandler):
    """Handles SNS HTTP requests."""

    def do_GET(self) -> None:
        """Health/simple endpoints.

        - GET /healthz returns 200 OK
        - GET / returns 200 OK
        """
        if self.path in ("/healthz", "/"):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
            return

        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"Not Found")

    def do_POST(self) -> None:
        """Handle SNS POST request."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")

        try:
            payload: Dict[str, Any] = json.loads(body)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON in POST body")
            self.send_error(400, "Invalid JSON")
            return

        msg_type = self.headers.get("x-amz-sns-message-type") or payload.get("Type")

        if msg_type == "SubscriptionConfirmation":
            self._handle_subscription(payload)
            return

        if msg_type == "Notification":
            self._handle_notification(payload)
            return

        logger.warning("Unknown SNS message type: %s", msg_type)
        self.send_response(200)  # Acknowledge anyway
        self.end_headers()

    def _handle_subscription(self, payload: Dict[str, Any]) -> None:
        """Confirm the subscription by visiting SubscribeURL."""
        subscribe_url = payload.get("SubscribeURL")
        if not subscribe_url:
            logger.error("SubscriptionConfirmation missing SubscribeURL")
            self.send_error(400, "Missing SubscribeURL")
            return

        logger.info("Received SubscriptionConfirmation. Visiting URL: %s", subscribe_url)
        try:
            with urlopen(subscribe_url) as response:
                if response.status == 200:
                    logger.info("Subscription confirmed successfully.")
                else:
                    logger.error("Failed to confirm subscription: HTTP %s", response.status)
        except Exception as exc:
            logger.exception("Error visiting SubscribeURL: %s", exc)

        self.send_response(200)
        self.end_headers()

    def _handle_notification(self, payload: Dict[str, Any]) -> None:
        """Process an SNS Notification.

        Extracts the inner S3 event JSON from payload['Message'] and passes that
        to the s3_data_quality_job as --event-json.
        """
        logger.info("Received SNS Notification.")

        try:
            s3_event = _extract_s3_event_from_sns_envelope(payload)
            event_json_str = json.dumps(s3_event)

            # Offload job execution to a thread to avoid blocking the HTTP response
            threading.Thread(target=self._run_job, args=(event_json_str,), daemon=True).start()

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        except Exception as exc:
            logger.exception("Error processing SNS Notification: %s", exc)
            self.send_error(500, str(exc))

    def _run_job(self, event_json: str) -> None:
        """Run the job entrypoint."""
        try:
            argv = ["--event-json", event_json]
            logger.info("Starting job for S3 event (from SNS)")
            ret = entrypoint(argv)
            if ret != 0:
                logger.error("Job failed with exit code %s", ret)
            else:
                logger.info("Job completed successfully")
        except SystemExit as exc:
            logger.error("Job raised SystemExit: %s", exc)
        except Exception as exc:
            logger.exception("Job crashed: %s", exc)


def main() -> None:
    """Start the HTTP server."""
    port = int(os.getenv("PORT", "8080"))
    server_address = ("", port)
    httpd = HTTPServer(server_address, SNSRequestHandler)
    logger.info("Starting SNS listener on port %s...", port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping SNS listener.")
        httpd.server_close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
