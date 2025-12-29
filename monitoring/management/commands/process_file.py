import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from monitoring.services.ingestion import process_s3_file

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Trigger ingestion for a specific S3 object."

    def add_arguments(self, parser):
        parser.add_argument("--bucket", required=False, help="S3 bucket name")
        parser.add_argument("--key", required=True, help="S3 object key")

    def handle(self, *args, **options):
        bucket = options.get("bucket") or settings.S3_BUCKET_NAME
        key = options.get("key")
        if not bucket:
            raise CommandError("Bucket is required (set S3_BUCKET_NAME or --bucket)")
        if not key:
            raise CommandError("Key is required (--key)")

        logger.info("Triggering ingestion", extra={"bucket": bucket, "key": key})
        process_s3_file(bucket, key)
