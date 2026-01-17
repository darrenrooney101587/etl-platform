"""Unit tests for PDF Generator processor."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from file_processing.processors.pdf_generator import PDFGenerator, PDFGeneratorConfig


class TestPDFGeneratorConfig(unittest.TestCase):
    """Test PDFGeneratorConfig initialization."""

    def test_default_config(self):
        """Test config with all defaults."""
        config = PDFGeneratorConfig()
        self.assertEqual(config.url, "http://localhost:3000/data-quality-report")
        self.assertEqual(config.timeout_ms, 30000)
        self.assertEqual(config.output_dir, "/tmp/pdf_reports")

    def test_custom_config(self):
        """Test config with custom values."""
        config = PDFGeneratorConfig(
            url="http://example.com/report",
            timeout_ms=60000,
            output_dir="/tmp/custom",
        )
        self.assertEqual(config.url, "http://example.com/report")
        self.assertEqual(config.timeout_ms, 60000)
        self.assertEqual(config.output_dir, "/tmp/custom")

    def test_config_from_env(self):
        """Test config reads from environment variables."""
        with patch.dict(
            os.environ,
            {
                "PDF_REPORT_URL": "http://env-url.com",
                "PDF_REPORT_TIMEOUT_MS": "45000",
            },
        ):
            config = PDFGeneratorConfig()
            self.assertEqual(config.url, "http://env-url.com")
            self.assertEqual(config.timeout_ms, 45000)


class TestPDFGenerator(unittest.TestCase):
    """Test PDFGenerator processor."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.config = PDFGeneratorConfig(
            url="http://example.com/test",
            output_dir=self.temp_dir,
        )
        self.generator = PDFGenerator(config=self.config)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    @patch("file_processing.processors.pdf_generator.sync_playwright")
    def test_generate_pdf_success(self, mock_sync_playwright):
        """Test successful PDF generation."""
        # Mock Playwright components
        mock_playwright_ctx = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()

        mock_sync_playwright.return_value.__enter__.return_value = mock_playwright_ctx
        mock_playwright_ctx.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page

        # Generate PDF
        output_path = self.generator.generate_pdf(
            output_filename="test_report.pdf"
        )

        # Verify Playwright calls
        mock_playwright_ctx.chromium.launch.assert_called_once_with(headless=True)
        mock_browser.new_page.assert_called_once()
        mock_page.goto.assert_called_once()
        mock_page.wait_for_load_state.assert_called_once_with(
            "networkidle", timeout=self.config.timeout_ms
        )
        mock_page.pdf.assert_called_once()
        mock_browser.close.assert_called_once()

        # Verify output path
        self.assertTrue(output_path.endswith("test_report.pdf"))
        self.assertIn(self.temp_dir, output_path)

    @patch("file_processing.processors.pdf_generator.sync_playwright")
    def test_generate_pdf_with_query_params(self, mock_sync_playwright):
        """Test PDF generation with query parameters."""
        mock_playwright_ctx = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()

        mock_sync_playwright.return_value.__enter__.return_value = mock_playwright_ctx
        mock_playwright_ctx.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page

        query_params = {"run_id": "123", "timestamp": "456"}
        self.generator.generate_pdf(
            output_filename="test.pdf",
            query_params=query_params,
        )

        # Verify URL includes query params
        call_args = mock_page.goto.call_args
        called_url = call_args[0][0]
        self.assertIn("run_id=123", called_url)
        self.assertIn("timestamp=456", called_url)

    @patch("file_processing.processors.pdf_generator.sync_playwright")
    def test_generate_pdf_creates_output_dir(self, mock_sync_playwright):
        """Test that output directory is created if it doesn't exist."""
        mock_playwright_ctx = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()

        mock_sync_playwright.return_value.__enter__.return_value = mock_playwright_ctx
        mock_playwright_ctx.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page

        # Use a non-existent directory
        non_existent_dir = os.path.join(self.temp_dir, "subdir", "nested")
        config = PDFGeneratorConfig(output_dir=non_existent_dir)
        generator = PDFGenerator(config=config)

        generator.generate_pdf(output_filename="test.pdf")

        # Verify directory was created
        self.assertTrue(os.path.exists(non_existent_dir))

    def test_generate_pdf_playwright_not_installed(self):
        """Test error handling when Playwright is not installed."""
        with patch(
            "file_processing.processors.pdf_generator.sync_playwright",
            side_effect=ImportError("No module named 'playwright'"),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                self.generator.generate_pdf()

            self.assertIn("Playwright is required", str(ctx.exception))

    @patch("file_processing.processors.pdf_generator.sync_playwright")
    def test_generate_pdf_browser_error(self, mock_sync_playwright):
        """Test error handling when browser fails."""
        mock_playwright_ctx = MagicMock()
        mock_playwright_ctx.chromium.launch.side_effect = Exception("Browser launch failed")

        mock_sync_playwright.return_value.__enter__.return_value = mock_playwright_ctx

        with self.assertRaises(RuntimeError) as ctx:
            self.generator.generate_pdf()

        self.assertIn("PDF generation failed", str(ctx.exception))

    @patch("file_processing.processors.pdf_generator.sync_playwright")
    def test_generate_pdf_auto_filename(self, mock_sync_playwright):
        """Test automatic filename generation with timestamp."""
        mock_playwright_ctx = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()

        mock_sync_playwright.return_value.__enter__.return_value = mock_playwright_ctx
        mock_playwright_ctx.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page

        # Generate PDF without specifying filename
        output_path = self.generator.generate_pdf()

        # Verify filename contains timestamp pattern
        filename = os.path.basename(output_path)
        self.assertTrue(filename.startswith("data_quality_report_"))
        self.assertTrue(filename.endswith(".pdf"))


if __name__ == "__main__":
    unittest.main()
