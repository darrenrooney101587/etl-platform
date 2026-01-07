"""Simple SQS consumer helper (DI-friendly).

Provides a minimal long-polling loop that receives messages and invokes a
user-supplied handler with the raw message body. The caller is responsible
for parsing the body (SNS-wrapped, S3 event, etc.) and performing any work.

This module adheres to repo standards:
- Python 3.10, PEP-8, full type annotations
- Dependency injection for the boto3 SQS client
- No Django imports
"""
from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import boto3
from botocore.client import BaseClient

logger = logging.getLogger(__name__)


@dataclass
class SQSConfig:
    """Runtime configuration for the SQS consumer."""

    queue_url: str
    wait_time_seconds: int = 20  # long poll
    max_messages: int = 10
    visibility_timeout: Optional[int] = None
    aws_region: str = os.getenv("AWS_REGION", "us-gov-west-1")
    aws_access_key_id: Optional[str] = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = os.getenv("AWS_SECRET_ACCESS_KEY")


class SQSConsumer:
    """A simple SQS long-polling consumer with graceful shutdown.

    Usage:
        consumer = SQSConsumer(config)
        consumer.run(lambda body, receipt_handle: ...)
    """

    def __init__(self, config: SQSConfig, sqs_client: Optional[BaseClient] = None) -> None:
        self._config = config
        self._sqs = sqs_client or self._build_client(config)
        self._stopping = False
        signal.signal(signal.SIGTERM, self._handle_stop)
        signal.signal(signal.SIGINT, self._handle_stop)

    def _build_client(self, config: SQSConfig) -> BaseClient:
        if config.aws_access_key_id and config.aws_secret_access_key:
            return boto3.client(
                "sqs",
                aws_access_key_id=config.aws_access_key_id,
                aws_secret_access_key=config.aws_secret_access_key,
                region_name=config.aws_region,
            )
        return boto3.client("sqs", region_name=config.aws_region)

    def _handle_stop(self, signum: int, frame: Any) -> None:  # type: ignore[override]
        logger.info("Received signal %s; stopping SQS consumer", signum)
        self._stopping = True

    def run(self, handler: Callable[[str, str], None]) -> None:
        """Start long-polling the queue and invoke handler for each message.

        Args:
            handler: Callable that receives (body, receipt_handle). It should
                     raise on unrecoverable errors. On success it should return;
                     we will delete the message. If it raises, the message will
                     remain (or you can change visibility here if desired).
        """
        backoff: float = 1.0
        while not self._stopping:
            try:
                params: Dict[str, Any] = {
                    "QueueUrl": self._config.queue_url,
                    "MaxNumberOfMessages": self._config.max_messages,
                    "WaitTimeSeconds": self._config.wait_time_seconds,
                }
                if self._config.visibility_timeout is not None:
                    params["VisibilityTimeout"] = self._config.visibility_timeout

                resp = self._sqs.receive_message(**params)
                messages: List[Dict[str, Any]] = resp.get("Messages", [])

                if not messages:
                    backoff = 1.0  # reset backoff on idle
                    continue

                for msg in messages:
                    body = msg.get("Body", "")
                    receipt = msg.get("ReceiptHandle", "")
                    try:
                        handler(body, receipt)
                        # On success, delete the message
                        self._sqs.delete_message(QueueUrl=self._config.queue_url, ReceiptHandle=receipt)
                    except Exception as exc:  # pragma: no cover (caller-specific)
                        logger.exception("Handler failed; leaving message (will be retried): %s", exc)

                # small yield
                time.sleep(0.01)

            except Exception as exc:
                logger.exception("SQS polling error: %s", exc)
                time.sleep(backoff)
                backoff = min(backoff * 2.0, 30.0)

        logger.info("SQS consumer stopped")
