"""Generic FTPS client implementation moved to etl_core."""
from __future__ import annotations

import socket
import ssl
from dataclasses import dataclass
from ftplib import FTP_TLS, error_perm
from typing import List, Optional, Tuple


class FTPSAuthError(Exception):
    """Raised when authentication fails."""


class FTPSTLSError(Exception):
    """Raised when the TLS handshake or verification fails."""


class FTPSDataChannelError(Exception):
    """Raised when a data-channel command (LIST/RETR/STOR) fails."""


@dataclass(frozen=True)
class FTPSLoginAttempt:
    username: str
    stage: str
    message: str
    success: bool


class FTPSClient:

    def __init__(
            self,
            host: str,
            port: int = 21,
            timeout: int = 12,
            cafile: Optional[str] = None,
            insecure: bool = False,
            passive: bool = True,
            tls_min_version: ssl.TLSVersion = ssl.TLSVersion.TLSv1,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.passive = passive
        self._ftp: Optional[FTP_TLS] = None

        if insecure:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        else:
            ctx = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH, cafile=cafile)
            ctx.check_hostname = True
        ctx.minimum_version = tls_min_version
        self._ssl_context = ctx

    def connect(self) -> None:
        ftp = FTP_TLS(timeout=self.timeout, context=self._ssl_context)
        try:
            ftp.connect(host=self.host, port=self.port, timeout=self.timeout)
            ftp.auth()
        except ssl.SSLError as e:
            raise FTPSTLSError(f"TLS error: {e}") from e
        except (OSError, socket.error) as e:
            raise
        self._ftp = ftp

    def close(self) -> None:
        if self._ftp is not None:
            try:
                self._ftp.quit()
            except Exception:
                try:
                    self._ftp.close()
                except Exception:
                    pass
            finally:
                self._ftp = None

    def __enter__(self) -> "FTPSClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @staticmethod
    def _username_candidates(raw_user: Optional[str]) -> List[str]:
        candidates: List[str] = []
        if raw_user:
            candidates.append(raw_user)
        seen: set[str] = set()
        uniq: List[str] = []
        for c in candidates:
            if c not in seen:
                uniq.append(c)
                seen.add(c)
        return uniq

    def login(self, username: str, password: str) -> None:
        if self._ftp is None:
            raise RuntimeError("Not connected. Call connect() or use context manager.")
        try:
            self._ftp.login(user=username, passwd=password)
        except error_perm as e:
            raise FTPSAuthError(str(e)) from e

        self._ftp.prot_p()
        self._ftp.set_pasv(self.passive)

    def login_with_variants(
            self,
            password: str,
            raw_user: Optional[str] = None,
    ) -> Tuple[str, List[FTPSLoginAttempt]]:
        attempts: List[FTPSLoginAttempt] = []
        for candidate in self._username_candidates(raw_user=raw_user):
            try:
                self.login(candidate, password)
                attempts.append(FTPSLoginAttempt(candidate, "ok", "Logged in", True))
                return candidate, attempts
            except FTPSAuthError as e:
                msg = str(e)
                attempts.append(FTPSLoginAttempt(candidate, "auth", msg, False))
                continue
        raise FTPSAuthError("All username variants failed")

    def pwd(self) -> str:
        self._ensure_open()
        return self._ftp.pwd()

    def chdir(self, path: str) -> None:
        self._ensure_open()
        self._ftp.cwd(path)

    def listdir(self, path: Optional[str] = None, max_lines: int = 0) -> List[str]:
        self._ensure_open()
        lines: List[str] = []
        try:
            if path:
                self._ftp.retrlines(f"LIST {path}", callback=lines.append)
            else:
                self._ftp.retrlines("LIST", callback=lines.append)
        except error_perm as e:
            raise FTPSDataChannelError(str(e)) from e
        return lines if max_lines <= 0 else lines[:max_lines]

    def download(self, remote_path: str, local_path: str, blocksize: int = 64 * 1024) -> None:
        self._ensure_open()
        try:
            with open(local_path, "wb") as fp:
                self._ftp.retrbinary(f"RETR {remote_path}", fp.write, blocksize=blocksize)
        except error_perm as e:
            raise FTPSDataChannelError(str(e)) from e

    def upload(self, local_path: str, remote_path: str, blocksize: int = 64 * 1024) -> None:
        self._ensure_open()
        try:
            with open(local_path, "rb") as fp:
                self._ftp.storbinary(f"STOR {remote_path}", fp, blocksize=blocksize)
        except error_perm as e:
            raise FTPSDataChannelError(str(e)) from e

    def _ensure_open(self) -> None:
        if self._ftp is None:
            raise RuntimeError("Not connected. Call connect() or use context manager.")
