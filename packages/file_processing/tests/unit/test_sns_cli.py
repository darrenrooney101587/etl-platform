"""Tests for SNS CLI entrypoint."""
import json
import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch

from file_processing.cli.sns_main import SNSRequestHandler


class MockRequest(BytesIO):
    """Mock wfile for RequestHandler."""
    def __init__(self) -> None:
        super().__init__()
        self._content = b""

    def write(self, b: bytes) -> int:
        self._content += b
        return len(b)


class MockServer:
    """Mock HTTPServer."""
    pass


class SnsCliTest(unittest.TestCase):
    """Test SNS request handler."""

    @patch("file_processing.cli.sns_main.urlopen")
    def test_do_POST_subscription(self, mock_urlopen: MagicMock) -> None:
        """Test POST with SubscriptionConfirmation."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # Use partial mock to avoid socket stuff
        handler = SNSRequestHandler

        # Instantiate without calling __init__
        req = handler.__new__(handler)
        req.rfile = BytesIO(json.dumps({
            "Type": "SubscriptionConfirmation",
            "SubscribeURL": "http://example.com/confirm",
            "Message": "",
            "TopicArn": "arn:aws:sns:..."
        }).encode("utf-8"))
        req.wfile = BytesIO()  # type: ignore
        req.headers = {"Content-Length": str(len(req.rfile.getvalue()))}
        req.send_error = MagicMock() # type: ignore
        req.send_response = MagicMock() # type: ignore
        req.end_headers = MagicMock() # type: ignore

        # Run
        req.do_POST()

        mock_urlopen.assert_called_with("http://example.com/confirm")
        req.send_response.assert_called_with(200)

    @patch("file_processing.cli.sns_main.entrypoint")
    @patch("file_processing.cli.sns_main.threading.Thread")
    def test_do_POST_notification(self, mock_thread: MagicMock, mock_entrypoint: MagicMock) -> None:
        """Test POST with Notification."""
        handler = SNSRequestHandler

        # Instantiate without calling __init__
        req = handler.__new__(handler)

        # Payload mimicking SNS body
        payload = {
            "Type": "Notification",
            "TopicArn": "arn:aws:sns:...",
            "Message": '{"bucket": "b", "key": "k"}'
        }

        req.rfile = BytesIO(json.dumps(payload).encode("utf-8"))
        req.wfile = BytesIO() # type: ignore
        req.headers = {"Content-Length": str(len(req.rfile.getvalue()))}
        req.send_error = MagicMock() # type: ignore
        req.send_response = MagicMock() # type: ignore
        req.end_headers = MagicMock() # type: ignore

        # Run
        req.do_POST()

        req.send_response.assert_called_with(200)

        # Check thread started with correct args
        mock_thread.assert_called()

        # Get arguments passed to Thread constructor
        call_kwargs = mock_thread.call_args[1]
        target = call_kwargs.get("target")
        thread_args = call_kwargs.get("args")

        self.assertEqual(target, req._run_job)
        self.assertIsNotNone(thread_args)

        # Check the constructed event JSON
        event_json_str = thread_args[0]
        event_json = json.loads(event_json_str)

        self.assertIn("Records", event_json)
        self.assertEqual(len(event_json["Records"]), 1)
        self.assertIn("Sns", event_json["Records"][0])
        self.assertEqual(event_json["Records"][0]["Sns"], payload)

if __name__ == "__main__":
    unittest.main()
