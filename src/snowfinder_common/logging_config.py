"""Logging configuration helpers for snowfinder services.

Quick start::

    from snowfinder_common.logging_config import configure_logging

    configure_logging(verbose=True)          # DEBUG to stderr, plain text
    configure_logging(json_output=True)      # INFO to stderr, JSON lines

JSON output requires the ``python-json-logger`` package
(``pip install python-json-logger``).  If the package is not installed and
``json_output=True`` is requested, a warning is emitted and the plain-text
formatter is used as a fallback.
"""

import logging
import sys


_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


def configure_logging(
    verbose: bool = False,
    json_output: bool = False,
) -> None:
    """Configure the root logger for a snowfinder service.

    Calling this function is idempotent: subsequent calls reconfigure the root
    logger in place (existing handlers are replaced).

    Parameters
    ----------
    verbose:
        ``True``  → set root log level to ``DEBUG``.
        ``False`` → set root log level to ``INFO``.
    json_output:
        When ``True``, attempt to use :class:`pythonjsonlogger.jsonlogger.JsonFormatter`
        for structured JSON-lines output.  Falls back to plain text if the
        ``python-json-logger`` package is not installed.
    """
    level = logging.DEBUG if verbose else logging.INFO

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)

    formatter: logging.Formatter
    if json_output:
        formatter = _make_json_formatter()
    else:
        formatter = logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT)

    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    # Replace existing handlers so repeated calls don't duplicate output.
    root.handlers.clear()
    root.addHandler(handler)


def _make_json_formatter() -> logging.Formatter:
    """Return a JSON formatter, falling back to plain text if unavailable."""
    try:
        from pythonjsonlogger import jsonlogger  # type: ignore[import-untyped]

        return jsonlogger.JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt=_DATE_FORMAT,
        )
    except ImportError:
        logging.getLogger(__name__).warning(
            "python-json-logger is not installed; falling back to plain-text logging. "
            "Install it with: pip install python-json-logger"
        )
        return logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT)
