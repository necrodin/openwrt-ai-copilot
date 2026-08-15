"""Dependency-free internet speed test.

Measures the *management host's* internet link using only the Python standard
library — no API key, no router command execution:

- **Latency / jitter** — TCP connect timings to a public host (default
  ``1.1.1.1:443``). ``socket.create_connection`` needs no privileges and the
  handshake RTT is a faithful latency proxy; jitter is the population standard
  deviation across the samples.
- **Download / upload** — bounded HTTPS transfers to public, credential-free
  endpoints (default Cloudflare's public speed-test endpoints, which require
  no key). Both targets are operator-configurable via settings; leaving a URL
  empty skips that measurement and reports it as a limitation.

TLS is always verified against a real trust store. The default store is
``certifi``'s portable CA bundle (an explicit project dependency) so the test
works on Homebrew macOS and other platforms whose system Python lacks a usable
CA bundle; an operator-configured ``SPEED_TEST_CA_BUNDLE`` overrides it. The
download endpoint requires a browser-like ``User-Agent`` (Cloudflare's speed
service rejects scripted user agents), which is set explicitly — it is the
same request their public speed-test page performs.

Why the backend and not the router: stock OpenWrt has no safe read-only
speed-test tool, and running one over SSH would execute commands on the device
(outside the project's read-only router contract) or require installing
packages. The management host's measurement is the most reliable, dependency-
free proxy available; the limitation is surfaced in the API response and UI.

Limits: at most one test runs at a time (``SpeedTestBusy``), a cooldown applies
between runs (``SpeedTestCooldown``), and every transfer is bounded by a byte
cap and a wall-clock timeout so a hung upstream can never block the API. The
latest result is retained in-memory (per application instance) so the dashboard
and a future Copilot feature can read it without re-running the test.
"""

from __future__ import annotations

import socket
import ssl
import statistics
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

import certifi

from app.core.config import settings

# Cloudflare's speed-test endpoints reject non-browser user agents (403), so a
# realistic browser UA is sent — the same one their public speed-test page uses.
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


class SpeedTestError(Exception):
    """The speed test could not be completed at all (e.g. no latency signal)."""


class SpeedTestBusy(SpeedTestError):
    """Another speed test is already in progress."""


class SpeedTestCooldown(SpeedTestError):
    """A speed test completed too recently to run again."""


def _ssl_context() -> ssl.SSLContext:
    """TLS context for speed-test transfers.

    Always verifies certificates (``CERT_REQUIRED`` + hostname checking) against
    a valid trust store. Prefers an operator-configured ``SPEED_TEST_CA_BUNDLE``
    PEM file, otherwise uses ``certifi``'s portable CA bundle — the platform
    default store is *not* relied on because Homebrew-built Pythons and slim
    containers often ship with an empty/broken trust store. Verification is
    never disabled.
    """
    cafile = settings.speed_test_ca_bundle.strip() or certifi.where()
    return ssl.create_default_context(cafile=cafile)


def _transfer_error(exc: BaseException, kind: str) -> SpeedTestError:
    """Map a transfer failure to a clean, user-facing message.

    ``urllib`` wraps TLS failures in ``URLError``, so the root cause is
    unwrapped before classifying. Certificate problems are surfaced distinctly
    (and actionably) instead of a raw ``CERTIFICATE_VERIFY_FAILED`` trace;
    never includes credentials.
    """
    if isinstance(exc, urllib.error.HTTPError):
        return SpeedTestError(f"{kind} endpoint returned HTTP {exc.code}.")
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    if isinstance(reason, ssl.SSLCertVerificationError):
        return SpeedTestError(
            f"{kind} could not be measured: TLS certificate verification failed. "
            "If the endpoint uses a private certificate authority, configure "
            "SPEED_TEST_CA_BUNDLE with the PEM bundle and retry."
        )
    if isinstance(reason, ssl.SSLError):
        return SpeedTestError(f"{kind} could not be measured: TLS error ({reason}).")
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return SpeedTestError(f"{kind} timed out.")
    if isinstance(exc, urllib.error.URLError):
        return SpeedTestError(f"{kind} could not be measured: {reason}.")
    return SpeedTestError(f"{kind} could not be measured: {exc}.")


class SpeedTestService:
    """Runs bounded speed tests and keeps the latest result.

    Thread-safe: the run gate (busy flag + cooldown) is guarded by a lock, and
    the blocking measurement is intended to run in a worker thread via
    ``asyncio.to_thread``.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._last_completed_at: float | None = None
        self._latest: dict | None = None

    # -- state ----------------------------------------------------------------
    def latest(self) -> dict | None:
        """The most recent result, or ``None`` before the first completed run."""
        with self._lock:
            return self._latest

    def is_running(self) -> bool:
        with self._lock:
            return self._running

    # -- orchestration --------------------------------------------------------
    def run(self) -> dict:
        """Run one speed test and store/return the result.

        Raises :class:`SpeedTestBusy` when another test is in flight and
        :class:`SpeedTestCooldown` when a test completed too recently.
        Individual download/upload failures are *not* fatal: they degrade to
        ``null`` values with an explanatory limitation entry. Only a total
        failure (no latency signal) raises :class:`SpeedTestError`.
        """
        with self._lock:
            if self._running:
                raise SpeedTestBusy("A speed test is already running.")
            if self._last_completed_at is not None:
                elapsed = time.monotonic() - self._last_completed_at
                if elapsed < settings.speed_test_cooldown_seconds:
                    raise SpeedTestCooldown(
                        "A speed test ran too recently; try again shortly."
                    )
            self._running = True

        started = time.monotonic()
        try:
            result = self._measure()
        finally:
            with self._lock:
                self._running = False
                self._last_completed_at = time.monotonic()

        result["duration_ms"] = int((time.monotonic() - started) * 1000)
        result["timestamp"] = datetime.now(UTC).isoformat()
        with self._lock:
            self._latest = result
        return result

    # -- measurement ----------------------------------------------------------
    def _measure(self) -> dict:
        limitations: list[str] = []

        ping_ms, jitter_ms = self._measure_latency()

        download_mbps = None
        if settings.speed_test_download_url:
            try:
                download_mbps = self._measure_download()
            except SpeedTestError as exc:
                limitations.append(str(exc))
            except OSError as exc:
                limitations.append(f"Download could not be measured: {exc}")
        else:
            limitations.append("Download measurement is disabled (no URL configured).")

        upload_mbps = None
        if settings.speed_test_upload_url:
            try:
                upload_mbps = self._measure_upload()
            except SpeedTestError as exc:
                limitations.append(str(exc))
            except OSError as exc:
                limitations.append(f"Upload could not be measured: {exc}")
        else:
            limitations.append("Upload measurement is disabled (no URL configured).")

        return {
            "download_mbps": download_mbps,
            "upload_mbps": upload_mbps,
            "ping_ms": ping_ms,
            "jitter_ms": jitter_ms,
            "limitations": limitations,
            "complete": not limitations,
        }

    def _measure_latency(self) -> tuple[float, float]:
        """Mean RTT (ping) and jitter via TCP connect timings, in ms."""
        host = settings.speed_test_latency_host
        port = settings.speed_test_latency_port
        samples = max(1, settings.speed_test_latency_samples)
        timeout = max(0.2, settings.speed_test_latency_timeout_seconds)

        timings: list[float] = []
        failures = 0
        for _ in range(samples):
            start = time.monotonic()
            try:
                with socket.create_connection((host, port), timeout=timeout):
                    pass
                timings.append((time.monotonic() - start) * 1000.0)
            except OSError:
                failures += 1
                if failures >= 3:
                    raise SpeedTestError(
                        f"Could not reach latency target {host}:{port}."
                    ) from None
        if not timings:
            raise SpeedTestError(f"Could not reach latency target {host}:{port}.")

        ping_ms = statistics.fmean(timings)
        jitter_ms = statistics.pstdev(timings) if len(timings) > 1 else 0.0
        return round(ping_ms, 1), round(jitter_ms, 1)

    def _measure_download(self) -> float:
        """Bounded HTTPS download; returns Mbps or raises :class:`SpeedTestError`."""
        url = settings.speed_test_download_url
        max_bytes = max(65536, settings.speed_test_max_bytes)
        max_duration = max(1.0, settings.speed_test_max_duration_seconds)

        start = time.monotonic()
        received = 0
        request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(
                request, timeout=max_duration, context=_ssl_context()
            ) as response:
                while True:
                    if time.monotonic() - start >= max_duration:
                        break
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received >= max_bytes:
                        break
        except (OSError, ssl.SSLError) as exc:
            raise _transfer_error(exc, "Download") from exc
        elapsed = time.monotonic() - start
        if received < 1024:
            raise SpeedTestError("Download returned no usable data.")
        return round(received * 8 / elapsed / 1_000_000, 1)

    def _measure_upload(self) -> float:
        """Bounded HTTPS upload; returns Mbps or raises :class:`SpeedTestError`."""
        url = settings.speed_test_upload_url
        size = max(65536, settings.speed_test_upload_bytes)
        max_duration = max(1.0, settings.speed_test_max_duration_seconds)

        payload = b"0" * size
        request = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={
                "User-Agent": _USER_AGENT,
                "Content-Type": "application/octet-stream",
            },
        )
        start = time.monotonic()
        try:
            with urllib.request.urlopen(
                request, timeout=max_duration, context=_ssl_context()
            ) as response:
                response.read()
        except (OSError, ssl.SSLError) as exc:
            raise _transfer_error(exc, "Upload") from exc
        elapsed = time.monotonic() - start
        if elapsed <= 0:
            return 0.0
        return round(size * 8 / elapsed / 1_000_000, 1)
