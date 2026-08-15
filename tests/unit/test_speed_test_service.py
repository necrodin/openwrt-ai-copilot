"""Speed-test service unit tests: measurement math, gating, and state.

The measurement internals are patched so the math and orchestration are tested
deterministically without any real network traffic.
"""

from __future__ import annotations

import os
import ssl
import time
import urllib.error

import certifi
import pytest

from app.core.config import settings
from app.services import speed_test as speed_test_module
from app.services.speed_test import (
    SpeedTestBusy,
    SpeedTestCooldown,
    SpeedTestError,
    SpeedTestService,
)


def _base_result() -> dict:
    return {
        "download_mbps": 245.4,
        "upload_mbps": 38.2,
        "ping_ms": 12.4,
        "jitter_ms": 2.8,
        "limitations": [],
        "complete": True,
    }


def test_latest_is_none_before_first_run() -> None:
    assert SpeedTestService().latest() is None


def test_run_stores_and_returns_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "speed_test_cooldown_seconds", 0.0)
    service = SpeedTestService()
    monkeypatch.setattr(service, "_measure", lambda: _base_result())

    result = service.run()

    assert result["download_mbps"] == 245.4
    assert result["ping_ms"] == 12.4
    assert result["timestamp"]
    assert result["duration_ms"] >= 0
    assert service.latest() is result


def test_run_rejects_second_concurrent_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "speed_test_cooldown_seconds", 0.0)
    service = SpeedTestService()
    service._running = True  # simulate an in-flight test
    with pytest.raises(SpeedTestBusy):
        service.run()


def test_run_enforces_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "speed_test_cooldown_seconds", 60.0)
    service = SpeedTestService()
    monkeypatch.setattr(service, "_measure", lambda: _base_result())

    service.run()
    with pytest.raises(SpeedTestCooldown):
        service.run()


def test_run_resets_busy_after_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "speed_test_cooldown_seconds", 0.0)
    service = SpeedTestService()
    monkeypatch.setattr(service, "_measure", lambda: _base_result())

    service.run()
    assert service.is_running() is False
    # Cooldown zeroed, so a second run is allowed once the first finishes.
    service.run()
    assert service.latest() is not None


def test_latency_mean_and_jitter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "speed_test_latency_samples", 4)
    calls = {"n": 0}

    def fake_connect(addr: tuple[str, int], timeout: float) -> object:
        calls["n"] += 1
        delay = 0.15 if calls["n"] % 2 else 0.05  # 150ms, 50ms, 150ms, 50ms

        class FakeSocket:
            def __enter__(self):
                time.sleep(delay)
                return self

            def __exit__(self, *args: object) -> bool:
                return False

        return FakeSocket()

    monkeypatch.setattr(speed_test_module.socket, "create_connection", fake_connect)
    service = SpeedTestService()

    ping_ms, jitter_ms = service._measure_latency()

    # Mean of [150, 50, 150, 50] is 100 ms; population stddev is 50 ms. The
    # delays are large enough that scheduling overhead is negligible. A modest
    # tolerance is used because wall-clock sleeps measure scheduling gaps too.
    assert ping_ms == pytest.approx(100.0, abs=15.0)
    assert jitter_ms == pytest.approx(50.0, abs=15.0)


def test_latency_fails_closed_when_target_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_connect(addr: tuple[str, int], timeout: float) -> object:
        raise OSError("network unreachable")

    monkeypatch.setattr(speed_test_module.socket, "create_connection", fake_connect)
    service = SpeedTestService()

    with pytest.raises(SpeedTestError):
        service._measure_latency()


def test_download_computes_mbps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "speed_test_max_bytes", 10_000_000)

    class FakeResponse:
        def __init__(self) -> None:
            self._data = b"x" * 10_000_000
            self._pos = 0
            self._first = True

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> bool:
            return False

        def read(self, n: int) -> bytes:
            if self._first:
                time.sleep(0.2)
                self._first = False
            chunk = self._data[self._pos : self._pos + n]
            self._pos += len(chunk)
            return chunk

    def fake_urlopen(request: object, timeout: float, **kwargs: object) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr(speed_test_module.urllib.request, "urlopen", fake_urlopen)
    service = SpeedTestService()

    mbps = service._measure_download()

    # 10 MB in ~0.2s -> ~400 Mbps.
    assert mbps == pytest.approx(400.0, rel=0.2)


def test_download_raises_on_no_data(monkeypatch: pytest.MonkeyPatch) -> None:
    class EmptyResponse:
        def __enter__(self) -> EmptyResponse:
            return self

        def __exit__(self, *args: object) -> bool:
            return False

        def read(self, n: int) -> bytes:
            return b""

    def fake_urlopen(request: object, timeout: float, **kwargs: object) -> EmptyResponse:
        return EmptyResponse()

    monkeypatch.setattr(speed_test_module.urllib.request, "urlopen", fake_urlopen)
    service = SpeedTestService()

    with pytest.raises(SpeedTestError):
        service._measure_download()


def test_upload_computes_mbps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "speed_test_upload_bytes", 8_000_000)

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> bool:
            return False

        def read(self, n: int = -1) -> bytes:
            time.sleep(0.2)
            return b"ok"

    def fake_urlopen(request: object, timeout: float, **kwargs: object) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr(speed_test_module.urllib.request, "urlopen", fake_urlopen)
    service = SpeedTestService()

    mbps = service._measure_upload()

    # 8 MB in ~0.2s -> ~320 Mbps.
    assert mbps == pytest.approx(320.0, rel=0.2)


def test_missing_transfer_targets_degrade_with_limitations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "speed_test_download_url", "")
    monkeypatch.setattr(settings, "speed_test_upload_url", "")
    service = SpeedTestService()
    monkeypatch.setattr(service, "_measure_latency", lambda: (10.0, 1.0))

    result = service._measure()

    assert result["download_mbps"] is None
    assert result["upload_mbps"] is None
    assert result["ping_ms"] == 10.0
    assert result["complete"] is False
    assert len(result["limitations"]) == 2


# -- TLS / CA bundle ---------------------------------------------------------


def test_ssl_context_loads_valid_ca_bundle_with_verification_enabled() -> None:
    ctx = speed_test_module._ssl_context()
    # Verification is always on — never CERT_NONE, never hostname-less.
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True
    # The certifi bundle is loaded and contains real public roots.
    assert len(ctx.get_ca_certs()) > 0


def test_ssl_context_honors_configured_ca_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "speed_test_ca_bundle", certifi.where())
    ctx = speed_test_module._ssl_context()
    assert len(ctx.get_ca_certs()) > 0

    monkeypatch.setattr(settings, "speed_test_ca_bundle", "/nonexistent/bundle.pem")
    with pytest.raises(OSError):
        speed_test_module._ssl_context()


def test_transfer_error_maps_certificate_failure_cleanly() -> None:
    cause = ssl.SSLCertVerificationError(1, "certificate verify failed: self-signed")
    error = speed_test_module._transfer_error(
        urllib.error.URLError(cause), "Download"
    )
    assert isinstance(error, SpeedTestError)
    message = str(error)
    assert "TLS certificate verification failed" in message
    assert "SPEED_TEST_CA_BUNDLE" in message


def test_transfer_error_maps_timeout_cleanly() -> None:
    error = speed_test_module._transfer_error(
        urllib.error.URLError(TimeoutError("timed out")), "Download"
    )
    assert isinstance(error, SpeedTestError)
    assert "timed out" in str(error)


def test_transfer_error_maps_http_failure_cleanly() -> None:
    http_error = urllib.error.HTTPError(
        "https://speed.test/__up", 503, "Service Unavailable", {}, None
    )
    error = speed_test_module._transfer_error(http_error, "Upload")
    assert isinstance(error, SpeedTestError)
    assert "503" in str(error)


# -- bounded transfer --------------------------------------------------------


def test_download_bounded_to_max_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "speed_test_max_bytes", 200_000)
    served = {"total": 0}

    class InfiniteResponse:
        def __enter__(self) -> InfiniteResponse:
            return self

        def __exit__(self, *args: object) -> bool:
            return False

        def read(self, n: int) -> bytes:
            served["total"] += n
            return b"x" * n  # never terminates, so only the byte cap stops it

    def fake_urlopen(request: object, timeout: float, **kwargs: object) -> InfiniteResponse:
        return InfiniteResponse()

    monkeypatch.setattr(speed_test_module.urllib.request, "urlopen", fake_urlopen)
    service = SpeedTestService()

    mbps = service._measure_download()

    # The loop stops once max_bytes is reached (one read-chunk of slack).
    assert served["total"] < 200_000 + 2 * 65536
    assert mbps > 0


# -- real internet round-trip (gated; run with RUN_REAL_NETWORK_TESTS=1) -----


REAL_NETWORK_ENABLED = os.environ.get("RUN_REAL_NETWORK_TESTS") == "1"


@pytest.mark.skipif(
    not REAL_NETWORK_ENABLED,
    reason="set RUN_REAL_NETWORK_TESTS=1 to run the real internet speed test",
)
def test_real_internet_roundtrip() -> None:
    """One real, un-mocked measurement against the live endpoints.

    Asserts real bytes were transferred over verified TLS for both directions —
    a fake/mock upload is never counted as success.
    """
    service = SpeedTestService()
    result = service.run()

    assert result["ping_ms"] is not None and result["ping_ms"] > 0
    assert result["download_mbps"] is not None and result["download_mbps"] > 0
    assert result["upload_mbps"] is not None and result["upload_mbps"] > 0
    assert result["complete"] is True
    assert not any(
        "CERTIFICATE_VERIFY_FAILED" in str(limitation)
        for limitation in result["limitations"]
    )
