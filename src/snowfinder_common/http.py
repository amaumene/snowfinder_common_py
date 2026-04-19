"""Shared HTTP utilities for snowfinder services.

Provides a robust ``download_file()`` helper with retry logic and
structured logging.
"""

import contextlib
import logging
import os
import tempfile
import time
from pathlib import Path

import requests

from .exceptions import FetchError

logger = logging.getLogger(__name__)


def _validate_retry_config(max_retries: int, retry_delay_s: float, timeout_s: float) -> None:
    """Validate download retry configuration values."""
    if max_retries < 1:
        raise ValueError("max_retries must be at least 1")
    if retry_delay_s <= 0:
        raise ValueError("retry_delay_s must be positive")
    if timeout_s <= 0:
        raise ValueError("timeout_s must be positive")


def download_file(
    url: str,
    dest_path: str,
    *,
    max_retries: int = 3,
    retry_delay_s: float = 2.0,
    timeout_s: float = 60.0,
) -> bool:
    """Download a file from *url* to *dest_path* with automatic retries.

    On success the file is written to *dest_path* and ``True`` is returned.
    On a clean HTTP 404 (data genuinely missing), ``False`` is returned
    without retrying — callers can treat this as an optional/absent file.
    On any other failure after exhausting all retries, a
    :class:`~snowfinder_common.exceptions.FetchError` is raised.

    Progress messages are emitted at ``DEBUG`` level; control visibility via
    ``LOG_LEVEL`` env var or ``configure_logging(verbose=True)``.

    Parameters
    ----------
    url:
        The URL to download.
    dest_path:
        Local filesystem path where the downloaded content will be written.
    max_retries:
        Maximum number of download attempts (including the first attempt).
    retry_delay_s:
        Base delay in seconds between retries; each subsequent retry waits
        ``retry_delay_s * attempt`` seconds (linear back-off).
    timeout_s:
        Per-request timeout in seconds passed to :func:`requests.get`.

    Returns
    -------
    bool
        ``True`` if the file was downloaded successfully, ``False`` if the
        server returned HTTP 404 (resource genuinely absent).

    Raises
    ------
    FetchError
        When all retry attempts are exhausted due to network errors,
        non-404 HTTP errors, or OS-level I/O failures.
    """
    _validate_retry_config(max_retries, retry_delay_s, timeout_s)
    filename = url.split("/")[-1] or url

    for attempt in range(max_retries):
        temp_path: str | None = None
        try:
            if attempt == 0:
                logger.debug("Downloading %s …", filename)

            dest_dir = Path(dest_path).parent or Path(".")
            with tempfile.NamedTemporaryFile(mode="wb", delete=False, dir=dest_dir) as tmp_fh:
                temp_path = tmp_fh.name

                body_deadline = time.monotonic() + 5 * timeout_s
                with requests.get(url, timeout=timeout_s, stream=True) as resp:
                    if resp.status_code == 404:
                        logger.debug("Not found (HTTP 404): %s", url)
                        os.unlink(temp_path)
                        temp_path = None  # prevent double-unlink in finally
                        return False

                    resp.raise_for_status()

                    for chunk in resp.iter_content(chunk_size=1024 * 1024):
                        if time.monotonic() > body_deadline:
                            raise requests.Timeout(
                                f"body read exceeded {5 * timeout_s:.0f}s for {url}"
                            )
                        if chunk:
                            tmp_fh.write(chunk)

            os.replace(temp_path, dest_path)
            temp_path = None

            size_mb = os.path.getsize(dest_path) / (1024 * 1024)
            logger.debug("Downloaded %s (%.1f MB)", filename, size_mb)

            return True

        except requests.HTTPError as exc:
            # Non-404 HTTP errors — log and retry
            logger.warning(
                "HTTP error on attempt %d/%d for %s: %s",
                attempt + 1,
                max_retries,
                url,
                exc,
            )
        except requests.RequestException as exc:
            logger.warning(
                "Download error on attempt %d/%d for %s: %s",
                attempt + 1,
                max_retries,
                url,
                exc,
            )
        except OSError as exc:
            logger.warning(
                "Download error on attempt %d/%d for %s: %s",
                attempt + 1,
                max_retries,
                url,
                exc,
            )
        finally:
            if temp_path is not None:
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(temp_path)

        if attempt < max_retries - 1:
            delay = retry_delay_s * (attempt + 1)
            logger.debug("Retrying in %.1f s …", delay)
            time.sleep(delay)

    logger.error(
        "Download failed after %d attempts: %s",
        max_retries,
        url,
    )
    raise FetchError(
        f"Download failed after {max_retries} attempts: {url}",
        context={"url": url, "attempts": max_retries},
    )
