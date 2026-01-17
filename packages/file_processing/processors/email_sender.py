"""Email Sender Processor using SendGrid.

This processor sends emails with optional PDF attachments using SendGrid's SMTP API.
"""
from __future__ import annotations

import base64
import logging
import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class EmailSenderConfig:
    """Configuration for email sending via SendGrid."""

    def __init__(
        self,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        from_address: Optional[str] = None,
        from_name: Optional[str] = None,
        default_recipient: Optional[str] = None,
    ) -> None:
        """Initialize email sender configuration.

        All parameters default to environment variables if not provided.

        Args:
            smtp_host: SMTP server host. Defaults to env var SMTP_HOST.
            smtp_port: SMTP server port. Defaults to env var SMTP_PORT.
            smtp_user: SMTP username. Defaults to env var SMTP_USER.
            smtp_password: SMTP password. Defaults to env var SMTP_PASSWORD.
            from_address: Email from address. Defaults to env var EMAIL_FROM_ADDRESS.
            from_name: Email from name. Defaults to env var EMAIL_FROM_NAME.
            default_recipient: Default recipient. Defaults to env var DEFAULT_EMAIL_RECIPIENT.
        """
        self.smtp_host = smtp_host or os.getenv("SMTP_HOST", "smtp.sendgrid.net")
        self.smtp_port = smtp_port or int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = smtp_user or os.getenv("SMTP_USER", "apikey")
        self.smtp_password = smtp_password or os.getenv("SMTP_PASSWORD", "")
        self.from_address = from_address or os.getenv(
            "EMAIL_FROM_ADDRESS", "noreply@etl-platform.example.com"
        )
        self.from_name = from_name or os.getenv("EMAIL_FROM_NAME", "ETL Platform Data Quality")
        self.default_recipient = default_recipient or os.getenv(
            "DEFAULT_EMAIL_RECIPIENT", "admin@example.com"
        )


class EmailSender:
    """Sends emails with optional attachments via SendGrid SMTP.

    This processor handles email delivery using SMTP with TLS encryption.
    It supports HTML and plain text content, as well as PDF attachments.
    """

    def __init__(self, config: Optional[EmailSenderConfig] = None) -> None:
        """Initialize email sender.

        Args:
            config: Optional EmailSenderConfig. Defaults to environment-based config.
        """
        self._config = config or EmailSenderConfig()

    def send_email(
        self,
        to_addresses: Optional[List[str]] = None,
        subject: str = "Data Quality Report",
        body_text: Optional[str] = None,
        body_html: Optional[str] = None,
        attachment_paths: Optional[List[str]] = None,
    ) -> None:
        """Send an email with optional PDF attachments.

        Args:
            to_addresses: List of recipient email addresses. If None, uses default from config.
            subject: Email subject line.
            body_text: Plain text email body. If None, generates default text.
            body_html: HTML email body. Optional.
            attachment_paths: List of file paths to attach. Typically PDF files.

        Raises:
            RuntimeError: If email sending fails.
        """
        # Use default recipient if none provided
        if not to_addresses:
            to_addresses = [self._config.default_recipient]

        # Validate SMTP configuration
        if not self._config.smtp_password:
            raise RuntimeError(
                "SMTP password not configured. Set SMTP_PASSWORD or SENDGRID_API_KEY environment variable."
            )

        # Generate default body if not provided
        if body_text is None:
            body_text = (
                "Please find attached the data quality report.\n\n"
                "This is an automated message from the ETL Platform Data Quality system."
            )

        logger.info(
            "Sending email",
            extra={
                "to_addresses": to_addresses,
                "subject": subject,
                "attachment_count": len(attachment_paths) if attachment_paths else 0,
            },
        )

        try:
            # Create multipart message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self._config.from_name} <{self._config.from_address}>"
            msg["To"] = ", ".join(to_addresses)

            # Attach plain text body
            msg.attach(MIMEText(body_text, "plain"))

            # Attach HTML body if provided
            if body_html:
                msg.attach(MIMEText(body_html, "html"))

            # Attach files if provided
            if attachment_paths:
                for file_path in attachment_paths:
                    self._attach_file(msg, file_path)

            # Send via SMTP
            with smtplib.SMTP(self._config.smtp_host, self._config.smtp_port) as server:
                server.starttls()
                server.login(self._config.smtp_user, self._config.smtp_password)
                server.send_message(msg)

            logger.info("Email sent successfully", extra={"to_addresses": to_addresses})

        except Exception as exc:
            logger.exception("Failed to send email")
            raise RuntimeError(f"Email sending failed: {exc}") from exc

    def _attach_file(self, msg: MIMEMultipart, file_path: str) -> None:
        """Attach a file to the email message.

        Args:
            msg: MIMEMultipart message to attach to.
            file_path: Path to the file to attach.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Attachment file not found: {file_path}")

        filename = path.name

        with open(path, "rb") as f:
            file_data = f.read()

        # Determine MIME type based on file extension
        mime_type = "application/pdf" if path.suffix.lower() == ".pdf" else "application/octet-stream"

        attachment = MIMEApplication(file_data, _subtype=mime_type.split("/")[1])
        attachment.add_header("Content-Disposition", "attachment", filename=filename)

        msg.attach(attachment)

        logger.debug("Attached file to email", extra={"filename": filename, "size_bytes": len(file_data)})
