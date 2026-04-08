"""Shared HTTP utilities for snowfinder services.

Provides a robust ``download_file()`` helper with retry logic and
structured logging, extracted from the MSM fetcher in snowfinder_predictor.
"""

import logging
import os
import time

import requests

from .exceptions import FetchError

logger = logging.getLogger(__name__)


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
    On a permanent failure (e.g. HTTP 404) or after exhausting all retries,
    ``False`` is returned — a :class:`~snowfinder_common.exceptions.FetchError`
    is **not** raised so that callers can treat missing files as optional.

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
        ``True`` if the file was downloaded successfully, ``False`` otherwise.

    Raises
    ------
    FetchError
        Only raised for unexpected programming errors (e.g. ``dest_path``
        directory does not exist).  Network failures are returned as ``False``.
    """
    filename = url.split("/")[-1] or url

    for attempt in range(max_retries):
        try:
            if attempt == 0:
                logger.debug("Downloading %s …", filename)

            resp = requests.get(url, timeout=timeout_s, stream=True)

            if resp.status_code == 404:
                logger.debug("Not found (HTTP 404): %s", url)
                return False

            resp.raise_for_status()

            with open(dest_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    fh.write(chunk)

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
        except OSError as exc:
            # Filesystem error writing dest_path — this is a programming error
            raise FetchError(
                f"Cannot write to destination path {dest_path!r}: {exc}",
                context={"url": url, "dest_path": dest_path},
            ) from exc
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Download error on attempt %d/%d for %s: %s",
                attempt + 1,
                max_retries,
                url,
                exc,
            )

        if attempt < max_retries - 1:
            delay = retry_delay_s * (attempt + 1)
            logger.debug("Retrying in %.1f s …", delay)
            time.sleep(delay)

    logger.error("Download failed after %d attempts: %s", max_retries, url)
    return False
