"""Compatibility adapters: lazy re-exports of etl_core processors under pipeline_processing.processors."""
from importlib import import_module
from typing import Any

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
    elif name == "S3DataQualityProcessor":
        module = import_module("pipeline_processing.processors.s3_data_quality_processor")
        return getattr(module, "S3DataQualityProcessor")
    elif name == "S3DataQualityProcessorConfig":
        module = import_module("pipeline_processing.processors.s3_data_quality_processor")
        return getattr(module, "S3DataQualityProcessorConfig")
    elif name == "DataProfiler":
        module = import_module("pipeline_processing.processors.profiler")
        return getattr(module, "DataProfiler")
    elif name == "PDFGenerator":
        module = import_module("pipeline_processing.processors.pdf_generator")
        return getattr(module, "PDFGenerator")
    elif name == "PDFGeneratorConfig":
        module = import_module("pipeline_processing.processors.pdf_generator")
        return getattr(module, "PDFGeneratorConfig")
    elif name == "EmailSender":
        module = import_module("pipeline_processing.processors.email_sender")
        return getattr(module, "EmailSender")
    elif name == "EmailSenderConfig":
        module = import_module("pipeline_processing.processors.email_sender")
        return getattr(module, "EmailSenderConfig")
    raise AttributeError(f"module {__name__} has no attribute {name}")


def __dir__() -> list[str]:
    return sorted(__all__)
