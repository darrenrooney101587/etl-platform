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
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Optional
from urllib.request import urlopen

from etl_core.support.circuit_breaker import CircuitBreaker

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
        # Admin endpoint to inspect/reset circuit breaker (dev only)
        if self.path == "/breaker":
            server = getattr(self, "server", None)
            circuit_breaker = getattr(server, "circuit_breaker", None)
            if circuit_breaker is None:
                self._send_json_response(404, {"error": "no circuit breaker"})
                return
            # Compute cooldown remaining if active
            last = circuit_breaker.last_failure_time
            cooldown_remaining = None
            if last is not None:
                try:
                    cooldown_remaining = max(
                        0, circuit_breaker.cooldown_seconds - (time.time() - last)
                    )
                except Exception:
                    cooldown_remaining = None

            resp = {
                "active": bool(circuit_breaker.active),
                "consecutive_failures": circuit_breaker.consecutive_failures,
                "last_failure_time": circuit_breaker.last_failure_time,
                "cooldown_remaining": cooldown_remaining,
            }
            self._send_json_response(200, resp)
            return

        if self.path == "/breaker/reset":
            server = getattr(self, "server", None)
            circuit_breaker = getattr(server, "circuit_breaker", None)
            if circuit_breaker is None:
                self._send_json_response(404, {"error": "no circuit breaker"})
                return
            circuit_breaker.record_success()
            self._send_json_response(200, {"status": "reset"})
            return

        if self.path in ("/", "/healthz"):
            logger.debug("Health check received: %s", self.path)
            self._send_json_response(200, {"status": "ok"})
            return

        # For any other GET, return 404
        self._send_json_response(404, {"error": "not found"})

    def do_HEAD(self) -> None:
        """Respond to HEAD requests with the same status as GET but no body.

        Some HTTP clients (including `curl -I`) use HEAD to probe the endpoint.
        BaseHTTPRequestHandler does not implement do_HEAD by default which
        results in a 501. Implementing do_HEAD avoids that and keeps health
        checks from failing.
        """
        # Mirror the GET health-check responses but do not write a body.
        if self.path in ("/", "/healthz"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if self.path == "/breaker":
            server = getattr(self, "server", None)
            circuit_breaker = getattr(server, "circuit_breaker", None)
            if circuit_breaker is None:
                self.send_response(404)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        # Other HEADs: 404
        self.send_response(404)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", "0")
        self.end_headers()

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
            if (
                not isinstance(decoded_message, dict)
                or "Records" not in decoded_message
            ):
                logger.error(
                    "Decoded SNS Message does not contain 'Records': %s",
                    type(decoded_message),
                )
                self._send_json_response(400, {"error": "message missing Records"})
                return

            # At this point we have a decoded S3 event JSON ready to forward
            logger.info("SNS Notification received; forwarding inner S3 event")
            # Acknowledge immediately and submit to the server's executor to keep HTTP response quick
            event_json_str = json.dumps(decoded_message)
            try:
                # Attach executor to the HTTPServer instance in main(); use it if present.
                server = getattr(self, "server", None)
                executor = getattr(server, "executor", None)
                if executor is not None:
                    # Generate a short trace ID
                    import uuid

                    trace_id = str(uuid.uuid4())[:8]

                    # Check circuit breaker before submitting the job
                    circuit_breaker = getattr(server, "circuit_breaker", None)
                    if circuit_breaker is not None and not circuit_breaker.allow():
                        logger.warning("Circuit breaker active; skipping message")
                        self._send_json_response(
                            200, {"status": "skipped", "reason": "circuit_breaker_active"}
                        )
                        return

                    executor.submit(self._run_job, event_json_str, trace_id)
                else:
                    # Fallback to daemon thread if executor not set (very unlikely)
                    import threading as _threading
                    import uuid

                    trace_id = str(uuid.uuid4())[:8]
                    _threading.Thread(
                        target=self._run_job,
                        args=(event_json_str, trace_id),
                        daemon=True,
                    ).start()

                self._send_json_response(200, {"status": "accepted"})
            except Exception:
                logger.exception("Failed to submit job to executor")
                self._send_json_response(500, {"error": "executor error"})

        except Exception as exc:
            logger.exception("Unhandled error processing SNS Notification: %s", exc)
            self._send_json_response(500, {"error": "internal error"})

    def _handle_subscription(self, payload: Dict[str, Any]) -> None:
        subscribe_url = payload.get("SubscribeURL")
        if not subscribe_url:
            logger.error("SubscriptionConfirmation missing SubscribeURL")
            self._send_json_response(400, {"error": "missing SubscribeURL"})
            return

        logger.info(
            "Received SubscriptionConfirmation. Visiting SubscribeURL: %s", subscribe_url
        )
        try:
            with urlopen(subscribe_url) as response:
                status = getattr(response, "status", None)
                if status is None:
                    # older Python urllib may not expose status; treat as success if no exception
                    logger.info(
                        "Subscription confirmation request completed (no status available)"
                    )
                elif status == 200:
                    logger.info("Subscription confirmed successfully.")
                else:
                    logger.error("Failed to confirm subscription: HTTP %s", status)
        except Exception:
            logger.exception("Error visiting SubscribeURL")

        self._send_json_response(200, {"status": "subscription_confirmed"})

    def _run_job(self, event_json: str, trace_id: str = "") -> None:
        """Invoke the existing job entrypoint with the decoded S3 event JSON.

        We pass the event JSON as the value for --event-json. The job's entrypoint
        is expected to accept the same CLI flag used interactively.
        """
        circuit_breaker = getattr(self, "server", None)
        circuit_breaker = getattr(circuit_breaker, "circuit_breaker", None)
        try:
            # Import the job entrypoint at runtime to avoid import-time Django/ORM
            from file_processing.jobs.s3_data_quality_job import (
                entrypoint,
            )  # type: ignore

            argv = ["--event-json", event_json]
            if trace_id:
                argv.extend(["--trace-id", trace_id])

            logger.info("[%s] Starting s3_data_quality_job for SNS message", trace_id)
            ret = entrypoint(argv)
            if ret != 0:
                logger.error(
                    "[%s] s3_data_quality_job returned non-zero exit code: %s",
                    trace_id,
                    ret,
                )
                if circuit_breaker is not None:
                    circuit_breaker.record_failure()
            else:
                logger.info("[%s] s3_data_quality_job completed successfully", trace_id)
                if circuit_breaker is not None:
                    circuit_breaker.record_success()
        except SystemExit as e:
            # entrypoint may call sys.exit(); log and continue
            logger.error(
                "[%s] s3_data_quality_job exited with SystemExit: %s", trace_id, e
            )
            if circuit_breaker is not None:
                circuit_breaker.record_failure()
        except Exception:
            logger.exception("[%s] s3_data_quality_job crashed", trace_id)
            if circuit_breaker is not None:
                circuit_breaker.record_failure()


def entrypoint(argv: List[str]) -> int:
    """Start the SNS HTTP listener.

    Args:
        argv: Command line arguments (passed to the job, though sns_main
              mostly relies on environment variables).

    Returns:
        Exit code (SNS main runs forever until interrupted).
    """
    # Bootstrap Django early so that importing etl_database_schema models works
    # inside worker threads or repository modules. Allow DJANGO_SETTINGS_MODULE to
    # be configured via env (preferred) otherwise default to package settings.
    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE",
        os.getenv("DJANGO_SETTINGS_MODULE", "file_processing.settings"),
    )
    try:
        # Deferred import so Django is only required at runtime when running the server.
        import django  # type: ignore

        django.setup()
    except Exception:
        # If Django isn't installed or bootstrap fails, we want the server to fail
        # loudly during startup rather than crash unpredictably on the first job.
        logger.exception(
            "Failed to bootstrap Django. Ensure DJANGO_SETTINGS_MODULE and DB env are set."
        )
        return 1

    port = int(os.getenv("PORT", "8080"))
    server_address = ("", port)
    # Ignoring type error for now because HTTPServer expects Type[BaseRequestHandler] but
    # BaseHTTPRequestHandler doesn't perfectly align with that in complex inheritance.
    # In practice this works fine.
    httpd = HTTPServer(server_address, SNSRequestHandler) # type: ignore

    try:
        max_workers = int(os.getenv("SNS_WORKER_MAX", "10"))
    except Exception:
        max_workers = 10
    httpd.executor = ThreadPoolExecutor(max_workers=max_workers)  # type: ignore

    try:
        circuit_breaker_max_failures = int(
            os.getenv("CIRCUIT_BREAKER_MAX_FAILURES", "5")
        )
        circuit_breaker_cooldown_seconds = int(
            os.getenv("CIRCUIT_BREAKER_COOLDOWN_SECONDS", "60")
        )
    except Exception:
        circuit_breaker_max_failures = 5
        circuit_breaker_cooldown_seconds = 60

    # Attach a CircuitBreaker instance to the server
    httpd.circuit_breaker = CircuitBreaker(  # type: ignore
        max_failures=int(os.getenv("CIRCUIT_MAX_FAILURES", "5")),
        reset_seconds=int(os.getenv("CIRCUIT_COOLDOWN_SECONDS", "300")),
    )

    logging.basicConfig(level=logging.INFO)
    logger.info(
        "Starting SNS listener on port %s with max_workers=%d...", port, max_workers
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping SNS listener.")
        # Shutdown executor to stop accepting new tasks and attempt graceful shutdown
        try:
            httpd.executor.shutdown(wait=False)  # type: ignore
        except Exception:
            logger.exception("Failed to shutdown executor cleanly")
        httpd.server_close()
    except Exception:
        logger.exception("SNS listener crashed")
        return 1
    return 0


JOB = (entrypoint, "Start the SNS HTTP listener service")
