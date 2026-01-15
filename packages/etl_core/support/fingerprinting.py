"""Shared fingerprint normalization utilities."""
from __future__ import annotations

import hashlib
import re
from typing import Iterable

NORMALIZED_NUMBER = "<n>"
NORMALIZED_UUID = "<uuid>"
NORMALIZED_TIMESTAMP = "<ts>"

UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.I)
TIMESTAMP_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[tT ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b",
    re.I,
)
RUN_ID_RE = re.compile(r"\brun[_-]?id[:=]?\s*[a-z0-9-]+\b", re.I)
NUMBER_RE = re.compile(r"\b\d+\b")
WHITESPACE_RE = re.compile(r"\s+")


def normalize_error_message(message: str) -> str:
    """Normalize an error message to reduce false-unique fingerprints."""
    text = message.lower().strip()
    text = RUN_ID_RE.sub("run_id <n>", text)
    text = UUID_RE.sub(NORMALIZED_UUID, text)
    text = TIMESTAMP_RE.sub(NORMALIZED_TIMESTAMP, text)
    text = NUMBER_RE.sub(NORMALIZED_NUMBER, text)
    text = WHITESPACE_RE.sub(" ", text)
    return text


def compute_fingerprint(components: Iterable[str]) -> str:
    """Compute a deterministic SHA-256 fingerprint from ordered components."""
    joined = "|".join([c or "" for c in components])
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
