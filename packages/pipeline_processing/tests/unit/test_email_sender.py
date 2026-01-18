"""Unit tests for Email Sender processor."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from pipeline_processing.processors.email_sender import EmailSender, EmailSenderConfig


class TestEmailSenderConfig(unittest.TestCase):
    """Test EmailSenderConfig initialization."""

    def test_default_config(self):
        """Test config with all defaults."""
        config = EmailSenderConfig()
        self.assertEqual(config.smtp_host, "smtp.sendgrid.net")
        self.assertEqual(config.smtp_port, 587)
        self.assertEqual(config.smtp_user, "apikey")
        self.assertEqual(config.from_address, "noreply@etl-platform.example.com")
        self.assertEqual(config.from_name, "ETL Platform Data Quality")
        self.assertEqual(config.default_recipient, "admin@example.com")

    def test_custom_config(self):
        """Test config with custom values."""
        config = EmailSenderConfig(
            smtp_host="custom.smtp.com",
            smtp_port=465,
            smtp_user="custom_user",
            smtp_password="custom_pass",
            from_address="custom@example.com",
            from_name="Custom Name",
            default_recipient="recipient@example.com",
        )
        self.assertEqual(config.smtp_host, "custom.smtp.com")
        self.assertEqual(config.smtp_port, 465)
        self.assertEqual(config.smtp_user, "custom_user")
        self.assertEqual(config.smtp_password, "custom_pass")
        self.assertEqual(config.from_address, "custom@example.com")
        self.assertEqual(config.from_name, "Custom Name")
        self.assertEqual(config.default_recipient, "recipient@example.com")

    def test_config_from_env(self):
        """Test config reads from environment variables."""
        with patch.dict(
            os.environ,
            {
                "SMTP_HOST": "env.smtp.com",
                "SMTP_PORT": "2525",
                "SMTP_USER": "env_user",
                "SMTP_PASSWORD": "env_pass",
                "EMAIL_FROM_ADDRESS": "env@example.com",
                "EMAIL_FROM_NAME": "Env Name",
                "DEFAULT_EMAIL_RECIPIENT": "env_recipient@example.com",
            },
        ):
            config = EmailSenderConfig()
            self.assertEqual(config.smtp_host, "env.smtp.com")
            self.assertEqual(config.smtp_port, 2525)
            self.assertEqual(config.smtp_user, "env_user")
            self.assertEqual(config.smtp_password, "env_pass")
            self.assertEqual(config.from_address, "env@example.com")
            self.assertEqual(config.from_name, "Env Name")
            self.assertEqual(config.default_recipient, "env_recipient@example.com")


class TestEmailSender(unittest.TestCase):
    """Test EmailSender processor."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = EmailSenderConfig(
            smtp_host="test.smtp.com",
            smtp_port=587,
            smtp_user="test_user",
            smtp_password="test_password",
            from_address="test@example.com",
            from_name="Test Sender",
            default_recipient="default@example.com",
        )
        self.sender = EmailSender(config=self.config)

    @patch("pipeline_processing.processors.email_sender.smtplib.SMTP")
    def test_send_email_success(self, mock_smtp_class):
        """Test successful email sending."""
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        self.sender.send_email(
            to_addresses=["recipient@example.com"],
            subject="Test Subject",
            body_text="Test body",
        )

        # Verify SMTP calls
        mock_smtp_class.assert_called_once_with("test.smtp.com", 587)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("test_user", "test_password")
        mock_server.send_message.assert_called_once()

    @patch("pipeline_processing.processors.email_sender.smtplib.SMTP")
    def test_send_email_default_recipient(self, mock_smtp_class):
        """Test email sending with default recipient."""
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        self.sender.send_email(subject="Test", body_text="Body")

        # Verify send_message was called
        mock_server.send_message.assert_called_once()

        # Verify message contains default recipient
        sent_message = mock_server.send_message.call_args[0][0]
        self.assertIn("default@example.com", sent_message["To"])

    @patch("pipeline_processing.processors.email_sender.smtplib.SMTP")
    def test_send_email_with_html(self, mock_smtp_class):
        """Test email sending with HTML body."""
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        self.sender.send_email(
            to_addresses=["recipient@example.com"],
            subject="Test",
            body_text="Plain text",
            body_html="<html><body>HTML body</body></html>",
        )

        mock_server.send_message.assert_called_once()

    @patch("pipeline_processing.processors.email_sender.smtplib.SMTP")
    def test_send_email_with_attachment(self, mock_smtp_class):
        """Test email sending with PDF attachment."""
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        # Create a temporary PDF file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"PDF content")
            tmp_path = tmp.name

        try:
            self.sender.send_email(
                to_addresses=["recipient@example.com"],
                subject="Test",
                body_text="Body",
                attachment_paths=[tmp_path],
            )

            mock_server.send_message.assert_called_once()

        finally:
            os.unlink(tmp_path)

    @patch("pipeline_processing.processors.email_sender.smtplib.SMTP")
    def test_send_email_attachment_not_found(self, mock_smtp_class):
        """Test error handling when attachment file is not found."""
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        with self.assertRaises(FileNotFoundError):
            self.sender.send_email(
                to_addresses=["recipient@example.com"],
                subject="Test",
                body_text="Body",
                attachment_paths=["/nonexistent/file.pdf"],
            )

    @patch("pipeline_processing.processors.email_sender.smtplib.SMTP")
    def test_send_email_multiple_recipients(self, mock_smtp_class):
        """Test email sending to multiple recipients."""
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        recipients = ["user1@example.com", "user2@example.com", "user3@example.com"]

        self.sender.send_email(
            to_addresses=recipients,
            subject="Test",
            body_text="Body",
        )

        mock_server.send_message.assert_called_once()

        sent_message = mock_server.send_message.call_args[0][0]
        to_field = sent_message["To"]
        for recipient in recipients:
            self.assertIn(recipient, to_field)

    def test_send_email_no_password(self):
        """Test error when SMTP password is not configured."""
        config = EmailSenderConfig(smtp_password="")
        sender = EmailSender(config=config)

        with self.assertRaises(RuntimeError) as ctx:
            sender.send_email(subject="Test", body_text="Body")

        self.assertIn("SMTP password not configured", str(ctx.exception))

    @patch("pipeline_processing.processors.email_sender.smtplib.SMTP")
    def test_send_email_smtp_error(self, mock_smtp_class):
        """Test error handling when SMTP fails."""
        mock_smtp_class.return_value.__enter__.side_effect = Exception("SMTP connection failed")

        with self.assertRaises(RuntimeError) as ctx:
            self.sender.send_email(
                to_addresses=["recipient@example.com"],
                subject="Test",
                body_text="Body",
            )

        self.assertIn("Email sending failed", str(ctx.exception))

    @patch("pipeline_processing.processors.email_sender.smtplib.SMTP")
    def test_send_email_default_body(self, mock_smtp_class):
        """Test default body text is used when none provided."""
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        self.sender.send_email(subject="Test")

        mock_server.send_message.assert_called_once()

        sent_message = mock_server.send_message.call_args[0][0]
        # Message should have a default body
        self.assertIsNotNone(sent_message.get_payload())


if __name__ == "__main__":
    unittest.main()
