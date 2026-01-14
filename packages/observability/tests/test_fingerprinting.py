"""Tests for fingerprint normalization and stability."""
from __future__ import annotations

import unittest

from observability.fingerprinting import compute_fingerprint, normalize_error_message


class FingerprintingTests(unittest.TestCase):
    def test_normalization_removes_runids_and_numbers(self) -> None:
        raw = "Run_ID=abc-123 failure at 2024-01-01T10:00:00Z uuid 550e8400-e29b-41d4-a716-446655440000"
        normalized = normalize_error_message(raw)
        self.assertNotIn("abc-123", normalized)
        self.assertIn("<ts>", normalized)
        self.assertIn("<uuid>", normalized)
        self.assertIn("<n>", normalized)
        self.assertNotIn("2024", normalized)

    def test_fingerprint_is_stable(self) -> None:
        base = ["tenant", "job_failed", "job", "stage", "ValueError", "timeout after <n>s"]
        fp1 = compute_fingerprint(base)
        fp2 = compute_fingerprint(list(base))
        self.assertEqual(fp1, fp2)


if __name__ == "__main__":
    unittest.main()
