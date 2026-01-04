"""Data quality processor for attachment readiness checks."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from file_processing.repositories.data_quality_repository import DataQualityRepository


@dataclass
class DataQualityMetrics:
    """Computed metrics for attachment quality checks."""

    agency_id: int
    total_files: int
    forms: int
    user_documents: int
    missing_output_filenames: int

    def as_dict(self) -> Dict[str, int]:
        """Return metrics as a plain dictionary."""
        return {
            "agency_id": self.agency_id,
            "total_files": self.total_files,
            "forms": self.forms,
            "user_documents": self.user_documents,
            "missing_output_filenames": self.missing_output_filenames,
        }


class DataQualityProcessor:
    """Processor that performs read-only quality checks against attachment data."""

    def __init__(self, repository: DataQualityRepository) -> None:
        self._repository = repository

    def run_checks(self, agency_id: int) -> Dict[str, object]:
        """Run data quality checks for the given agency."""
        try:
            attachments = self._repository.get_attachment_files_for_s3_processing(agency_id)
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Failed to read attachment data: {exc}",
                "metrics": {},
                "issues": [],
            }

        missing_output = [
            row for row in attachments
            if not (str(row.get("output_filename") or "").strip())
        ]
        forms = [row for row in attachments if row.get("attachable_type") == "Form"]
        user_docs = [row for row in attachments if row.get("attachable_type") == "UserDocument"]

        metrics = DataQualityMetrics(
            agency_id=agency_id,
            total_files=len(attachments),
            forms=len(forms),
            user_documents=len(user_docs),
            missing_output_filenames=len(missing_output),
        )

        issues: List[Dict[str, object]] = []
        if missing_output:
            issues.append(
                {
                    "type": "missing_output_filename",
                    "count": len(missing_output),
                    "examples": [
                        row.get("filename") or row.get("original_filename")
                        for row in missing_output[:3]
                    ],
                }
            )

        status = "warning" if issues else "success"
        message = (
            "Data quality checks completed with warnings"
            if issues
            else "Data quality checks passed"
        )

        return {
            "status": status,
            "message": message,
            "metrics": metrics.as_dict(),
            "issues": issues,
        }
