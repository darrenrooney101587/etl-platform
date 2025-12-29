import json
import logging
import time
from typing import Iterable

import boto3
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from monitoring.services.ingestion import process_s3_file

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Poll the SQS queue for S3 events and process files."

    def handle(self, *args, **options):
        queue_url = settings.SQS_QUEUE_URL
        if not queue_url:
            raise CommandError("SQS_QUEUE_URL is not configured")

        sqs = boto3.client("sqs", region_name=settings.AWS_REGION)
        logger.info("Starting SQS worker", extra={"queue_url": queue_url})

        while True:
            response = sqs.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=20,
            )
            messages = response.get("Messages", [])
            if not messages:
                continue

            for message in messages:
                receipt_handle = message.get("ReceiptHandle")
                try:
                    for record in _parse_s3_records(message.get("Body", "")):
                        bucket = record["s3"]["bucket"]["name"]
                        key = record["s3"]["object"]["key"]
                        process_s3_file(bucket, key)
                except Exception:  # noqa: BLE001
                    logger.exception("Failed to process message")
                else:
                    if receipt_handle:
                        sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)

            time.sleep(1)


def _parse_s3_records(body: str) -> Iterable[dict]:
    if not body:
        return []
    payload = json.loads(body)
    if "Message" in payload:
        payload = json.loads(payload["Message"])
    return payload.get("Records", [])
