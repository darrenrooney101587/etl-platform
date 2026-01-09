"""SNS HTTP entrypoint for file_processing.

This module provides a minimal HTTP server used in development and in-cluster
deployments to accept AWS SNS HTTPS notifications. It handles Subscription
confirmation and Notification message types. For Notification messages it
unwraps the SNS envelope, decodes the inner JSON Message (expected to be the
S3 event JSON with a top-level "Records" array) and forwards that decoded
S3 event JSON to the existing s3_data_quality_job entrypoint via the
`--event-json` CLI argument.

Design goals:
- Do not wrap the SNS envelope in a fake structure; extract and pass the
  inner event JSON directly.
- Keep the HTTP server long-running (serve_forever).
- Respond quickly to SNS by offloading work to a background thread.
- Add a lightweight health endpoint at GET / and GET /healthz.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional
from urllib.request import urlopen

# Import the correct entrypoint within the file_processing package
from file_processing.jobs.s3_data_quality_job import entrypoint


logger = logging.getLogger(__name__)


class SNSRequestHandler(BaseHTTPRequestHandler):
    """HTTP handler that accepts SNS POSTs and forwards the inner S3 event.

    Expected SNS Notification body (example):
    {
      "Type": "Notification",
      "Message": "{\"Records\": [...]}",
      ...
    }

    The handler extracts payload['Message'], JSON-decodes it (if a string),
    validates that the decoded object contains a top-level "Records" key,
    and invokes the job entrypoint with `--event-json <decoded-json>`.
    """

    server_version = "file-processing-sns/1.0"

    def _send_json_response(self, code: int, payload: Optional[Dict[str, Any]] = None) -> None:
        body = b""
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self) -> None:  # health endpoints
        if self.path in ("/", "/healthz"):
            logger.debug("Health check received: %s", self.path)
            self._send_json_response(200, {"status": "ok"})
            return

        # For any other GET, return 404
        self._send_json_response(404, {"error": "not found"})

    def do_POST(self) -> None:
        # Read and parse incoming SNS HTTP POST body
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length).decode("utf-8")

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            logger.exception("Failed to parse incoming POST body as JSON")
            self._send_json_response(400, {"error": "invalid json"})
            return

        # Determine message type (header x-amz-sns-message-type is common)
        msg_type = self.headers.get("x-amz-sns-message-type") or payload.get("Type")

        if msg_type == "SubscriptionConfirmation":
            self._handle_subscription(payload)
            return

        if msg_type != "Notification":
            # Unknown/unsupported message types are acknowledged but not processed
            logger.warning("Unknown SNS message type: %s", msg_type)
            self._send_json_response(200, {"status": "ignored"})
            return

        # Handle Notification: extract and decode payload['Message']
        try:
            message_field = payload.get("Message")
            if message_field is None:
                logger.error("SNS Notification missing 'Message' field")
                self._send_json_response(400, {"error": "missing Message"})
                return

            # If Message is a JSON string, decode it. If it's already a dict/list, use as-is.
            decoded_message: Any
            if isinstance(message_field, str):
                try:
                    decoded_message = json.loads(message_field)
                except json.JSONDecodeError:
                    logger.exception("SNS Message field is not valid JSON")
                    self._send_json_response(400, {"error": "Message not JSON"})
                    return
            else:
                decoded_message = message_field

            # Validate that decoded_message is a dict containing 'Records'
            if not isinstance(decoded_message, dict) or "Records" not in decoded_message:
                logger.error("Decoded SNS Message does not contain 'Records': %s", type(decoded_message))
                self._send_json_response(400, {"error": "message missing Records"})
                return

            # At this point we have a decoded S3 event JSON ready to forward
            logger.info("SNS Notification received; forwarding inner S3 event")
            # Acknowledge immediately and process in background to keep HTTP response quick
            event_json_str = json.dumps(decoded_message)
            threading.Thread(target=self._run_job, args=(event_json_str,), daemon=True).start()
            self._send_json_response(200, {"status": "accepted"})

        except Exception as exc:
            logger.exception("Unhandled error processing SNS Notification: %s", exc)
            self._send_json_response(500, {"error": "internal error"})

    def _handle_subscription(self, payload: Dict[str, Any]) -> None:
        subscribe_url = payload.get("SubscribeURL")
        if not subscribe_url:
            logger.error("SubscriptionConfirmation missing SubscribeURL")
            self._send_json_response(400, {"error": "missing SubscribeURL"})
            return

        logger.info("Received SubscriptionConfirmation. Visiting SubscribeURL: %s", subscribe_url)
        try:
            with urlopen(subscribe_url) as response:
                status = getattr(response, "status", None)
                if status is None:
                    # older Python urllib may not expose status; treat as success if no exception
                    logger.info("Subscription confirmation request completed (no status available)")
                elif status == 200:
                    logger.info("Subscription confirmed successfully.")
                else:
                    logger.error("Failed to confirm subscription: HTTP %s", status)
        except Exception:
            logger.exception("Error visiting SubscribeURL")

        self._send_json_response(200, {"status": "subscription_confirmed"})

    def _run_job(self, event_json: str) -> None:
        """Invoke the existing job entrypoint with the decoded S3 event JSON.

        We pass the event JSON as the value for --event-json. The job's entrypoint
        is expected to accept the same CLI flag used interactively.
        """
        try:
            argv = ["--event-json", event_json]
            logger.info("Starting s3_data_quality_job for SNS message")
            ret = entrypoint(argv)
            if ret != 0:
                logger.error("s3_data_quality_job returned non-zero exit code: %s", ret)
            else:
                logger.info("s3_data_quality_job completed successfully")
        except SystemExit as e:
            # entrypoint may call sys.exit(); log and continue
            logger.error("s3_data_quality_job exited with SystemExit: %s", e)
        except Exception:
            logger.exception("s3_data_quality_job crashed")


def main() -> None:
    port = int(os.getenv("PORT", "8080"))
    server_address = ("", port)
    httpd = HTTPServer(server_address, SNSRequestHandler)
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting SNS listener on port %s...", port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping SNS listener.")
        httpd.server_close()


if __name__ == "__main__":
    main()
