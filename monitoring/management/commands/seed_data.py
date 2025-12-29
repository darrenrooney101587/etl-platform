import logging
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Load seed data for local schema and monitoring file entries."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fixture",
            default="fixtures/monitoring_seed.json",
            help="Path to fixture JSON file",
        )

    def handle(self, *args, **options):
        fixture_path = Path(options["fixture"])
        if not fixture_path.is_file():
            raise FileNotFoundError(f"Fixture not found: {fixture_path}")

        logger.info("Loading fixture", extra={"fixture": str(fixture_path)})
        call_command("loaddata", str(fixture_path))

        if settings.S3_BUCKET_NAME:
            self.stdout.write(
                self.style.SUCCESS(
                    "Seed data loaded. Use: python manage.py process_file --key data/sample_monitoring_file.csv"
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "Seed data loaded. Set S3_BUCKET_NAME or pass --bucket when running process_file."
                )
            )
