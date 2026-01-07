"""SQS entrypoint for file_processing.

This CLI polls an SQS queue and forwards each received message body to the
existing s3_data_quality_job event extraction + processing pipeline.

It reuses the same code path as local CLI runs: pass an event JSON (possibly
SNS/SQS-wrapped) and let _extract_s3_events parse and handle it.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

from etl_core.sqs.consumer import SQSConfig, SQSConsumer
from file_processing.jobs.s3_data_quality_job import _extract_s3_events, entrypoint

logger = logging.getLogger(__name__)


def _handle_message(body: str) -> int:
    """Translate a raw message body to the job entrypoint invocation.

    We feed the body through the same --event-json path used by the CLI,
    so all SNS/SQS/S3 formats supported by _extract_s3_events are accepted.
    """
    # Build argv as if the user passed: --event-json '<body>'
    argv = ["--event-json", body]
    return entrypoint(argv)


def main() -> None:
    queue_url = os.getenv("SQS_QUEUE_URL", "")
    if not queue_url:
        print("SQS_QUEUE_URL not set", file=sys.stderr)
        raise SystemExit(2)

    config = SQSConfig(queue_url=queue_url)
    consumer = SQSConsumer(config)

    def _handler(body: str, receipt: str) -> None:
        code = _handle_message(body)
        if code != 0:
            # Non-zero exit indicates a processing error; raise so the consumer
            # leaves the message and it can be retried after visibility timeout.
            raise RuntimeError(f"Job failed with exit code {code}")

    consumer.run(_handler)


if __name__ == "__main__":
    main()
