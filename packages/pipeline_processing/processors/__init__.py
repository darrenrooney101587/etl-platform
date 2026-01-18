"""Compatibility adapters: lazy re-exports of etl_core processors under pipeline_processing.processors."""
from importlib import import_module
from typing import Any

__all__ = ["S3FileProcessor"]


def __getattr__(name: str) -> Any:
    if name == "S3FileProcessor":
        module = import_module("etl_core.processors.s3_file_processor")
        return getattr(module, "S3FileProcessor")
    raise AttributeError(f"module {__name__} has no attribute {name}")


def __dir__() -> list[str]:
    return sorted(__all__)
