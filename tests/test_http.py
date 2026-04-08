"""Tests for snowfinder_common.http."""

from unittest.mock import MagicMock, call, patch

import pytest
import requests

from snowfinder_common.exceptions import FetchError
from snowfinder_common.http import download_file


def _make_mock_response(status_code: int = 200, chunks: list[bytes] | None = None):
    """Build a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.iter_content.return_value = chunks or [b"data chunk"]
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status_code}", response=resp)
    else:
        resp.raise_for_status.return_value = None
    return resp


class TestDownloadFileSuccess:
    def test_returns_true_on_success(self, tmp_path):
        dest = tmp_path / "output.bin"
        mock_resp = _make_mock_response(200, [b"hello world"])

        with patch("snowfinder_common.http.requests.get", return_value=mock_resp) as mock_get:
            result = download_file("http://example.com/file.bin", str(dest))

        assert result is True
        mock_get.assert_called_once_with("http://example.com/file.bin", timeout=60.0, stream=True)

    def test_writes_content_to_dest_path(self, tmp_path):
        dest = tmp_path / "data.bin"
        chunks = [b"chunk1", b"chunk2", b"chunk3"]
        mock_resp = _make_mock_response(200, chunks)

        with patch("snowfinder_common.http.requests.get", return_value=mock_resp):
            download_file("http://example.com/data.bin", str(dest))

        assert dest.read_bytes() == b"chunk1chunk2chunk3"

    def test_custom_timeout_passed_to_requests(self, tmp_path):
        dest = tmp_path / "out.bin"
        mock_resp = _make_mock_response(200, [b"x"])

        with patch("snowfinder_common.http.requests.get", return_value=mock_resp) as mock_get:
            download_file("http://example.com/out.bin", str(dest), timeout_s=120.0)

        mock_get.assert_called_once_with("http://example.com/out.bin", timeout=120.0, stream=True)

    def test_single_attempt_on_success(self, tmp_path):
        dest = tmp_path / "f.bin"
        mock_resp = _make_mock_response(200, [b"ok"])

        with patch("snowfinder_common.http.requests.get", return_value=mock_resp) as mock_get:
            download_file("http://example.com/f.bin", str(dest), max_retries=3)

        assert mock_get.call_count == 1


class TestDownloadFileHttp404:
    def test_returns_false_on_404(self, tmp_path):
        dest = tmp_path / "missing.bin"
        mock_resp = _make_mock_response(404)
        mock_resp.raise_for_status.return_value = None  # 404 is handled specially

        with patch("snowfinder_common.http.requests.get", return_value=mock_resp):
            result = download_file("http://example.com/missing.bin", str(dest))

        assert result is False

    def test_no_retries_on_404(self, tmp_path):
        dest = tmp_path / "missing.bin"
        mock_resp = _make_mock_response(404)
        mock_resp.raise_for_status.return_value = None

        with (
            patch("snowfinder_common.http.requests.get", return_value=mock_resp) as mock_get,
            patch("snowfinder_common.http.time.sleep") as mock_sleep,
        ):
            download_file("http://example.com/missing.bin", str(dest), max_retries=3)

        assert mock_get.call_count == 1
        mock_sleep.assert_not_called()

    def test_file_not_created_on_404(self, tmp_path):
        dest = tmp_path / "missing.bin"
        mock_resp = _make_mock_response(404)
        mock_resp.raise_for_status.return_value = None

        with patch("snowfinder_common.http.requests.get", return_value=mock_resp):
            download_file("http://example.com/missing.bin", str(dest))

        assert not dest.exists()


class TestDownloadFileRetries:
    def test_retries_on_http_error(self, tmp_path):
        dest = tmp_path / "retry.bin"
        fail_resp = _make_mock_response(500)
        ok_resp = _make_mock_response(200, [b"success"])

        with (
            patch(
                "snowfinder_common.http.requests.get",
                side_effect=[fail_resp, ok_resp],
            ) as mock_get,
            patch("snowfinder_common.http.time.sleep"),
        ):
            result = download_file("http://example.com/retry.bin", str(dest), max_retries=3)

        assert result is True
        assert mock_get.call_count == 2

    def test_returns_false_after_exhausting_retries(self, tmp_path):
        dest = tmp_path / "fail.bin"
        fail_resp = _make_mock_response(503)

        with (
            patch(
                "snowfinder_common.http.requests.get",
                return_value=fail_resp,
            ) as mock_get,
            patch("snowfinder_common.http.time.sleep"),
        ):
            result = download_file("http://example.com/fail.bin", str(dest), max_retries=3)

        assert result is False
        assert mock_get.call_count == 3

    def test_retry_delay_is_linear_backoff(self, tmp_path):
        dest = tmp_path / "backoff.bin"
        fail_resp = _make_mock_response(503)

        with (
            patch("snowfinder_common.http.requests.get", return_value=fail_resp),
            patch("snowfinder_common.http.time.sleep") as mock_sleep,
        ):
            download_file(
                "http://example.com/backoff.bin",
                str(dest),
                max_retries=3,
                retry_delay_s=2.0,
            )

        # After attempt 0 → sleep(2.0*1=2.0), after attempt 1 → sleep(2.0*2=4.0)
        # No sleep after the last attempt
        assert mock_sleep.call_count == 2
        mock_sleep.assert_has_calls([call(2.0), call(4.0)])

    def test_no_sleep_after_final_attempt(self, tmp_path):
        dest = tmp_path / "nofinal.bin"
        fail_resp = _make_mock_response(503)

        with (
            patch("snowfinder_common.http.requests.get", return_value=fail_resp),
            patch("snowfinder_common.http.time.sleep") as mock_sleep,
        ):
            download_file(
                "http://example.com/nofinal.bin",
                str(dest),
                max_retries=1,
                retry_delay_s=5.0,
            )

        mock_sleep.assert_not_called()

    def test_retries_on_generic_exception(self, tmp_path):
        # requests.ConnectionError and Timeout are OSError subclasses (requests
        # inherits from IOError), so they hit the FetchError branch.  Use a plain
        # non-OSError exception to exercise the generic `except Exception` retry path.
        dest = tmp_path / "conn_err.bin"

        with (
            patch(
                "snowfinder_common.http.requests.get",
                side_effect=ValueError("unexpected decode error"),
            ) as mock_get,
            patch("snowfinder_common.http.time.sleep"),
        ):
            result = download_file("http://example.com/conn_err.bin", str(dest), max_retries=2)

        assert result is False
        assert mock_get.call_count == 2


class TestDownloadFileOsError:
    def test_oserror_raises_fetch_error(self, tmp_path):
        # Use a directory as dest_path to provoke IsADirectoryError (an OSError subclass)
        dest = str(tmp_path)  # writing to a directory path raises IsADirectoryError
        ok_resp = _make_mock_response(200, [b"data"])

        with patch("snowfinder_common.http.requests.get", return_value=ok_resp):
            with pytest.raises(FetchError) as exc_info:
                download_file("http://example.com/file.bin", dest)

        assert "dest_path" in exc_info.value.context
        assert exc_info.value.context["url"] == "http://example.com/file.bin"

    def test_fetch_error_context_contains_url_and_dest(self, tmp_path):
        url = "http://example.com/target.bin"
        dest = str(tmp_path)
        ok_resp = _make_mock_response(200, [b"x"])

        with patch("snowfinder_common.http.requests.get", return_value=ok_resp):
            with pytest.raises(FetchError) as exc_info:
                download_file(url, dest)

        ctx = exc_info.value.context
        assert ctx["url"] == url
        assert ctx["dest_path"] == dest
