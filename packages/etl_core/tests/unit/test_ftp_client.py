from __future__ import annotations

"""Unit tests for the FTPSClient in etl_core.

Covers connect error handling, login behavior, listing, download and upload
operations. All external network operations are mocked.
"""

import ssl
import tempfile
import os
import unittest
from unittest.mock import Mock, patch
from ftplib import error_perm

from etl_core.ftp.client import (
    FTPSClient,
    FTPSAuthError,
    FTPSTLSError,
    FTPSDataChannelError,
    FTPSLoginAttempt,
)


class TestFTPSClient(unittest.TestCase):
    def test_username_candidates(self) -> None:
        # _username_candidates is static; when given None returns empty list,
        # when given a raw string returns a single-item unique list
        self.assertEqual(FTPSClient._username_candidates(None), [])
        self.assertEqual(FTPSClient._username_candidates("USER1"), ["USER1"])

    @patch("etl_core.ftp.client.FTP_TLS")
    def test_connect_raises_on_ssl_error(self, mock_ftp_tls: Mock) -> None:
        # Simulate an SSL error during connect
        mock_ftp = mock_ftp_tls.return_value
        mock_ftp.connect.side_effect = ssl.SSLError("tls fail")

        client = FTPSClient(host="example.com")

        with self.assertRaises(FTPSTLSError):
            client.connect()

    def test_login_without_connect_raises(self) -> None:
        client = FTPSClient(host="example.com")
        with self.assertRaises(RuntimeError):
            client.login("user", "password")

    @patch("etl_core.ftp.client.FTP_TLS")
    def test_login_raises_ftps_auth_error_on_perm(self, mock_ftp_tls: Mock) -> None:
        mock_ftp = mock_ftp_tls.return_value
        # Connect will succeed (no exception) but login will raise permission error
        mock_ftp.connect.return_value = None
        mock_ftp.auth.return_value = None
        mock_ftp.login.side_effect = error_perm("530 Login incorrect.")

        client = FTPSClient(host="example.com")
        client.connect()

        with self.assertRaises(FTPSAuthError):
            client.login("user", "badpass")

    @patch("etl_core.ftp.client.FTP_TLS")
    def test_login_with_variants_success(self, mock_ftp_tls: Mock) -> None:
        mock_ftp = mock_ftp_tls.return_value
        mock_ftp.connect.return_value = None
        mock_ftp.auth.return_value = None

        # login succeeds (no exception)
        mock_ftp.login.return_value = None
        mock_ftp.prot_p.return_value = None
        mock_ftp.set_pasv.return_value = None

        client = FTPSClient(host="example.com")
        client.connect()

        winner, attempts = client.login_with_variants(password="pw", raw_user="AUSER")

        self.assertEqual(winner, "AUSER")
        self.assertIsInstance(attempts, list)
        self.assertTrue(any(isinstance(a, FTPSLoginAttempt) for a in attempts))
        self.assertTrue(attempts[-1].success)

    @patch("etl_core.ftp.client.FTP_TLS")
    def test_listdir_success_and_permission_error(self, mock_ftp_tls: Mock) -> None:
        mock_ftp = mock_ftp_tls.return_value
        mock_ftp.connect.return_value = None
        mock_ftp.auth.return_value = None

        # Make retrlines call the callback for two lines
        def retrlines_side_effect(cmd, callback=None):
            if callback:
                callback("line1")
                callback("line2")

        mock_ftp.retrlines.side_effect = retrlines_side_effect

        client = FTPSClient(host="example.com")
        client.connect()

        lines = client.listdir()
        self.assertEqual(lines, ["line1", "line2"])

        # Now simulate permission error
        mock_ftp.retrlines.side_effect = error_perm("550 Permission denied")
        with self.assertRaises(FTPSDataChannelError):
            client.listdir()

    @patch("etl_core.ftp.client.FTP_TLS")
    def test_download_and_upload(self, mock_ftp_tls: Mock) -> None:
        mock_ftp = mock_ftp_tls.return_value
        mock_ftp.connect.return_value = None
        mock_ftp.auth.return_value = None

        # retrbinary should call the provided callback with bytes
        def retrbinary_side_effect(cmd, callback, blocksize=65536):
            # simulate sending two chunks
            callback(b"hello")
            callback(b"world")

        mock_ftp.retrbinary.side_effect = retrbinary_side_effect

        # storbinary just records the call
        mock_ftp.storbinary.return_value = None

        client = FTPSClient(host="example.com")
        client.connect()
        # create a temp file path to download into
        fd, path = tempfile.mkstemp()
        os.close(fd)
        upload_path: str | None = None
        try:
            # download should write bytes to the local file
            client.download("/remote/path/file.bin", path)
            with open(path, "rb") as fp:
                data = fp.read()
            self.assertEqual(data, b"helloworld")

            # create a file to upload
            upload_fd, upload_path = tempfile.mkstemp()
            os.close(upload_fd)
            with open(upload_path, "wb") as fp:
                fp.write(b"upload-data")

            client.upload(upload_path, "/remote/target.bin")
            # ensure storbinary called with expected STOR command
            mock_ftp.storbinary.assert_called()
            called_args = mock_ftp.storbinary.call_args[0]
            self.assertTrue(str(called_args[0]).upper().startswith("STOR "))
        finally:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
            try:
                if upload_path and os.path.exists(upload_path):
                    os.remove(upload_path)
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
