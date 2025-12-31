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
    """
    :param username: Username string attempted.
    :type username: str
    :param stage: Stage of failure ('tls', 'connect', 'auth', 'list', 'ok').
    :type stage: str
    :param message: Diagnostic message from server or exception.
    :type message: str
    :param success: True if the attempt ended in success.
    :type success: bool
    """
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
        """
        :param host: FTP host name.
        :type host: str
        :param port: Control port (default 21).
        :type port: int
        :param timeout: Socket timeout in seconds.
        :type timeout: int
        :param cafile: Optional PEM bundle to trust in addition to system CAs.
        :type cafile: Optional[str]
        :param insecure: If True, disable certificate and hostname verification.
        :type insecure: bool
        :param passive: If True use PASV mode; otherwise active (PORT).
        :type passive: bool
        :param tls_min_version: Minimum TLS protocol to allow.
        :type tls_min_version: ssl.TLSVersion
        """
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
        """
        Establish control connection and perform explicit TLS negotiation.

        :raises FTPSTLSError: On TLS failures.
        :raises OSError: On socket/connect errors.
        """
        ftp = FTP_TLS(timeout=self.timeout, context=self._ssl_context)
        try:
            ftp.connect(host=self.host, port=self.port, timeout=self.timeout)
            ftp.auth()  # 234 AUTH TLS
        except ssl.SSLError as e:
            raise FTPSTLSError(f"TLS error: {e}") from e
        except (OSError, socket.error) as e:
            raise
        self._ftp = ftp

    def close(self) -> None:
        """Close the session if open."""
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
        """
        :param user: Base username (e.g., 'TSWS2').
        :type user: Optional[str]
        :param domain: Optional domain/tenant (e.g., '030').
        :type domain: Optional[str]
        :param raw_user: Exact user string
        :type raw_user: Optional[str]
        :returns: Ordered unique username variants to try.
        :rtype: list[str]
        """
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
        """
        Login once with an exact username.

        :param username: Username to use.
        :type username: str
        :param password: Password to use.
        :type password: str
        :raises FTPSAuthError: On authentication failure.
        :raises RuntimeError: If connect() has not been called.
        """
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
        """
        Try multiple username formats until one logs in successfully.

        :param password: Password to use for all attempts.
        :type password: str
        :param raw_user: Exact string to try first (e.g., '030|TSWS2').
        :type raw_user: Optional[str]
        :returns: (winning_username, attempt_log)
        :rtype: tuple[str, list[FTPSLoginAttempt]]
        :raises FTPSAuthError: If all variants fail.
        """
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
        raise FTPSAuthError("All username variants failed")  # attempts contain diagnostics

    def pwd(self) -> str:
        """
        :returns: Current working directory on the server.
        :rtype: str
        """
        self._ensure_open()
        return self._ftp.pwd()

    def chdir(self, path: str) -> None:
        """
        :param path: Directory to change into.
        :type path: str
        """
        self._ensure_open()
        self._ftp.cwd(path)

    def listdir(self, path: Optional[str] = None, max_lines: int = 0) -> List[str]:
        """
        :param path: Optional path to list; defaults to current directory.
        :type path: Optional[str]
        :param max_lines: If > 0, limit returned listing lines.
        :type max_lines: int
        :returns: Listing lines as returned by LIST.
        :rtype: list[str]
        :raises FTPSDataChannelError: On LIST failure.
        """
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
        """
        :param remote_path: Remote file to retrieve.
        :type remote_path: str
        :param local_path: Local destination path.
        :type local_path: str
        :param blocksize: Read size per chunk.
        :type blocksize: int
        :raises FTPSDataChannelError: On RETR failure.
        """
        self._ensure_open()
        try:
            with open(local_path, "wb") as fp:
                self._ftp.retrbinary(f"RETR {remote_path}", fp.write, blocksize=blocksize)
        except error_perm as e:
            raise FTPSDataChannelError(str(e)) from e

    def upload(self, local_path: str, remote_path: str, blocksize: int = 64 * 1024) -> None:
        """
        :param local_path: Local file to send.
        :type local_path: str
        :param remote_path: Target path on server.
        :type remote_path: str
        :param blocksize: Write size per chunk.
        :type blocksize: int
        :raises FTPSDataChannelError: On STOR failure.
        """
        self._ensure_open()
        try:
            with open(local_path, "rb") as fp:
                self._ftp.storbinary(f"STOR {remote_path}", fp, blocksize=blocksize)
        except error_perm as e:
            raise FTPSDataChannelError(str(e)) from e

    def _ensure_open(self) -> None:
        if self._ftp is None:
            raise RuntimeError("Not connected. Call connect() or use context manager.")


if __name__ == "__main__":

    """
    To browser in an interactive session use the following CLI command:
    lftp -u 'BenchmarkMDPD','< PASSWORD >' \
    -e "set ftp:ssl-force true; set ftp:ssl-protect-data true; set ssl:verify-certificate true; set ftp:passive-mode true" \
    ftp://ftp.mdpd.net
    """

    HOST = "FTP.mdpd.net"
    PASSWORD = "< PASSWORD >"
    RAW_USER = "BenchmarkMDPD"

    client = FTPSClient(host=HOST, cafile=None, insecure=True, passive=True)
    try:
        client.connect()
        winner, log = client.login_with_variants(
            password=PASSWORD,
            raw_user=RAW_USER,
        )
        print(f"Logged in as: {winner}")
        print("PWD:", client.pwd())
        for line in client.listdir(max_lines=25):
            print(line)
    finally:
        client.close()
