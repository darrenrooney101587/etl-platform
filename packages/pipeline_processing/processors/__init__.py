"""Compatibility adapters: lazy re-exports of etl_core processors under pipeline_processing.processors."""
from importlib import import_module
from typing import Any

from pipeline_processing.processors.s3_data_quality_processor import (
    S3DataQualityProcessor,
    S3DataQualityProcessorConfig,
)
from pipeline_processing.processors.profiler import DataProfiler
from pipeline_processing.processors.pdf_generator import PDFGenerator, PDFGeneratorConfig
from pipeline_processing.processors.email_sender import EmailSender, EmailSenderConfig

__all__ = [
    "S3FileProcessor",
    "S3DataQualityProcessor",
    "S3DataQualityProcessorConfig",
    "DataProfiler",
    "PDFGenerator",
    "PDFGeneratorConfig",
    "EmailSender",
    "EmailSenderConfig",
]


def __getattr__(name: str) -> Any:
    if name == "S3FileProcessor":
        module = import_module("etl_core.processors.s3_file_processor")
        return getattr(module, "S3FileProcessor")
    raise AttributeError(f"module {__name__} has no attribute {name}")


def __dir__() -> list[str]:
    return sorted(__all__)
