"""PDF Generator Processor using Playwright for headless browser rendering.

This processor renders a frontend page using a headless browser (Chromium via Playwright)
and saves it as a PDF. This ensures 100% visual fidelity with the UI.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class PDFGeneratorConfig:
    """Configuration for PDF generation."""

    def __init__(
        self,
        url: Optional[str] = None,
        timeout_ms: int = 30000,
        output_dir: str = "/tmp/pdf_reports",
    ) -> None:
        """Initialize PDF generator configuration.

        Args:
            url: URL to render as PDF. Defaults to env var PDF_REPORT_URL.
            timeout_ms: Page load timeout in milliseconds. Defaults to env var PDF_REPORT_TIMEOUT_MS or 30000.
            output_dir: Directory to save generated PDFs. Defaults to /tmp/pdf_reports.
        """
        self.url = url or os.getenv("PDF_REPORT_URL", "http://localhost:3000/data-quality-report")
        self.timeout_ms = timeout_ms or int(os.getenv("PDF_REPORT_TIMEOUT_MS", "30000"))
        self.output_dir = output_dir


class PDFGenerator:
    """Generates PDFs from frontend pages using Playwright headless browser.

    This processor uses Playwright to launch a headless Chromium browser,
    navigate to a URL, and save the rendered page as a PDF file.
    """

    def __init__(self, config: Optional[PDFGeneratorConfig] = None) -> None:
        """Initialize PDF generator.

        Args:
            config: Optional PDFGeneratorConfig. Defaults to environment-based config.
        """
        self._config = config or PDFGeneratorConfig()
        self._playwright = None
        self._browser = None

    def generate_pdf(
        self,
        url: Optional[str] = None,
        output_filename: Optional[str] = None,
        query_params: Optional[dict] = None,
    ) -> str:
        """Generate a PDF from a URL using headless browser.

        Args:
            url: URL to render. If None, uses config default.
            output_filename: Output filename (without path). If None, generates timestamp-based name.
            query_params: Optional dict of query parameters to append to URL.

        Returns:
            Absolute path to the generated PDF file.

        Raises:
            RuntimeError: If PDF generation fails.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            logger.error("Playwright not installed. Run: playwright install chromium")
            raise RuntimeError(
                "Playwright is required for PDF generation. "
                "Install with: pip install playwright && playwright install chromium"
            ) from exc

        target_url = url or self._config.url

        # Append query parameters if provided
        if query_params:
            from urllib.parse import urlencode
            params_str = urlencode(query_params)
            separator = "&" if "?" in target_url else "?"
            target_url = f"{target_url}{separator}{params_str}"

        # Ensure output directory exists
        output_dir = Path(self._config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate output filename if not provided
        if output_filename is None:
            from datetime import datetime
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            output_filename = f"data_quality_report_{timestamp}.pdf"

        output_path = output_dir / output_filename
        abs_output_path = str(output_path.resolve())

        logger.info(
            "Generating PDF from URL",
            extra={
                "url": target_url,
                "output_path": abs_output_path,
                "timeout_ms": self._config.timeout_ms,
            },
        )

        try:
            with sync_playwright() as playwright:
                # Launch headless Chromium browser
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()

                # Navigate to the URL with timeout
                page.goto(target_url, timeout=self._config.timeout_ms)

                # Wait for page to be fully loaded
                page.wait_for_load_state("networkidle", timeout=self._config.timeout_ms)

                # Generate PDF with A4 format
                page.pdf(
                    path=abs_output_path,
                    format="A4",
                    print_background=True,
                    margin={"top": "1cm", "right": "1cm", "bottom": "1cm", "left": "1cm"},
                )

                browser.close()

            logger.info("PDF generated successfully", extra={"output_path": abs_output_path})
            return abs_output_path

        except Exception as exc:
            logger.exception("Failed to generate PDF")
            raise RuntimeError(f"PDF generation failed: {exc}") from exc

    def cleanup(self) -> None:
        """Clean up browser resources.

        Note: When using sync_playwright context manager, cleanup is automatic.
        This method is provided for explicit cleanup if needed in the future.
        """
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None
