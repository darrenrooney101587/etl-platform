"""Unit tests for the SQS CLI entrypoint wrapper."""
from __future__ import annotations

import json
import unittest
from typing import Any, Dict, List, Optional
from unittest.mock import patch

from file_processing.cli import sqs_main


class SqsCliTest(unittest.TestCase):
    def test_handle_message_passes_through_to_entrypoint(self) -> None:
        sample = {"Records": [{"s3": {"bucket": {"name": "b"}, "object": {"key": "k"}}}]}
        body = json.dumps(sample)

        with patch("file_processing.cli.sqs_main.entrypoint") as mock_entry:
            mock_entry.return_value = 0
            rc = sqs_main._handle_message(body)
            self.assertEqual(rc, 0)
            mock_entry.assert_called_once()
            # Ensure argv contains the body
            args, kwargs = mock_entry.call_args
            self.assertIn("--event-json", args[0])
            self.assertIn(body, args[0])


if __name__ == "__main__":
    unittest.main()
