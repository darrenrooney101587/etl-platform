"""Repository for recording refresh history and metrics using Django ORM.

This implementation uses the upstream models from
`etl_core.models.apps.bms_reporting.models` (or other layout variants)
and performs ORM operations. Django must be configured (set DJANGO_SETTINGS_MODULE
and call django.setup()) before instantiating or using this repository.
"""

from __future__ import annotations

from typing import Any, Dict, List


class HistoryRepository:
    """Django ORM-backed repository for seeder run history and job status.

    Usage:
        from reporting_seeder.django_bootstrap import bootstrap_django
        bootstrap_django('reporting_models.settings')
        repo = HistoryRepository()
        repo.record_start(run_id, manifest)

    Note: This class intentionally does NOT provide an SQL fallback. If Django
    or the upstream models are unavailable a RuntimeError will be raised with
    instructions to bootstrap the ORM.
    """

    def __init__(self) -> None:
        # no constructor args; repository always uses ORM models
        pass

    def _ensure_models(self):
        """Import and return the two ORM models we need.

        Returns:
            (SeederRunHistory, SeederJobStatus)

        Raises:
            RuntimeError: if Django or the models are not available. The
            message explains how to bootstrap Django for callers.
        """
        # Try a few known import paths to support different etl_core.models layouts
        candidates = (
            "etl_core.models.apps.bms_reporting.models",
            "etl_core.models.apps.reporting.models",
            "etl_core.models.apps.bms.models",
        )
        last_exc: Exception | None = None
        for mod_path in candidates:
            try:
                module = __import__(mod_path, fromlist=["*"])
                # Models may live in the imported module directly
                SeederRunHistory = getattr(module, "SeederRunHistory", None)
                SeederJobStatus = getattr(module, "SeederJobStatus", None)
                if SeederRunHistory is not None and SeederJobStatus is not None:
                    return SeederRunHistory, SeederJobStatus
            except Exception as exc:  # pragma: no cover - runtime dependency
                last_exc = exc
                continue

        # If we didn't find models, raise a helpful error directing callers to bootstrap Django
        raise RuntimeError(
            "Django ORM models are not available. Ensure DJANGO_SETTINGS_MODULE is set "
            "and that reporting_seeder.django_bootstrap.bootstrap_django(...) has been called before using HistoryRepository."
        ) from last_exc

    def record_start(self, run_id: str, manifest: Dict[str, object]) -> None:
        SeederRunHistory, SeederJobStatus = self._ensure_models()
        # Deferred import of timezone to avoid importing Django at module import
        from django.utils import timezone  # type: ignore

        manifest_id = int(manifest["id"])

        SeederRunHistory.objects.create(
            run_id=run_id,
            manifest_id=manifest_id,
            table_name=manifest.get("table_name"),
            report_name=manifest.get("report_name"),
            agency_id=manifest.get("agency_id"),
            agency_slug=manifest.get("agency_slug"),
            report_type=manifest.get("report_type"),
            status="running",
            start_time=timezone.now(),
            consecutive_failures=manifest.get("consecutive_failures", 0),
        )

        defaults = {
            "manifest_id": manifest_id,
            "report_name": manifest.get("report_name"),
            "report_type": manifest.get("report_type"),
            "agency_id": manifest.get("agency_id"),
            "agency_slug": manifest.get("agency_slug"),
            "status": "running",
            "start_time": timezone.now(),
            "last_run_id": run_id,
            "consecutive_failures": manifest.get("consecutive_failures", 0),
            "updated_at": timezone.now(),
        }
        SeederJobStatus.objects.update_or_create(table_name=manifest.get("table_name"), defaults=defaults)

    def record_success(
        self,
        run_id: str,
        manifest: Dict[str, object],
        duration_seconds: int,
        records_processed: int,
        bytes_processed: int,
        memory_usage_mb: int,
        cpu_percentage: int,
    ) -> None:
        SeederRunHistory, SeederJobStatus = self._ensure_models()
        from django.utils import timezone  # type: ignore

        manifest_id = int(manifest["id"])
        SeederRunHistory.objects.filter(run_id=run_id, manifest_id=manifest_id).update(
            status="success",
            finish_time=timezone.now(),
            duration_seconds=duration_seconds,
            records_processed=records_processed,
            bytes_processed=bytes_processed,
            memory_usage_mb=memory_usage_mb,
            cpu_percentage=cpu_percentage,
            consecutive_failures=0,
        )

        SeederJobStatus.objects.filter(table_name=manifest.get("table_name")).update(
            status="success",
            duration_seconds=duration_seconds,
            consecutive_failures=0,
            last_errors=None,
            updated_at=timezone.now(),
        )

    def record_error(self, run_id: str, manifest: Dict[str, object], errors: str) -> None:
        SeederRunHistory, SeederJobStatus = self._ensure_models()
        from django.utils import timezone  # type: ignore
        from django.db.models import F  # type: ignore

        manifest_id = int(manifest["id"])
        SeederRunHistory.objects.filter(run_id=run_id, manifest_id=manifest_id).update(
            status="error",
            finish_time=timezone.now(),
            errors=errors,
            consecutive_failures=F("consecutive_failures") + 1,
        )

        SeederJobStatus.objects.filter(table_name=manifest.get("table_name")).update(
            status="error",
            consecutive_failures=F("consecutive_failures") + 1,
            last_errors=errors,
            updated_at=timezone.now(),
        )

    def list_recent_runs(self, limit: int = 100) -> List[Dict[str, Any]]:
        SeederRunHistory, _ = self._ensure_models()
        qs = (
            SeederRunHistory.objects.order_by("-start_time")
            .values(
                "run_id",
                "manifest_id",
                "status",
                "start_time",
                "finish_time",
                "duration_seconds",
                "records_processed",
                "bytes_processed",
                "memory_usage_mb",
                "cpu_percentage",
                "errors",
            )[:limit]
        )
        return list(qs)
