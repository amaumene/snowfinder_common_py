"""Logging configuration helpers for snowfinder services.

Quick start::

    from snowfinder_common.logging_config import configure_logging

    configure_logging(verbose=True)          # DEBUG to stderr, plain text
    configure_logging(json_output=True)      # INFO to stderr, JSON lines

The ``LOG_LEVEL`` environment variable (``DEBUG``, ``INFO``, ``WARNING``,
``ERROR`` — case-insensitive) takes precedence over the *verbose* parameter
when set.

JSON output requires the ``python-json-logger`` package, declared as an
optional dependency (``pip install snowfinder-common[json-logging]``).
If the package is not installed and ``json_output=True`` is requested,
a warning is emitted and the plain-text formatter is used as a fallback.
"""

import logging
import os
import sys


_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"

_VALID_LEVELS: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def configure_logging(
    verbose: bool = False,
    json_output: bool = False,
) -> None:
    """Configure the root logger for a snowfinder service.

    Calling this function is idempotent: subsequent calls reconfigure the root
    logger in place (existing handlers are replaced).

    Level priority: ``LOG_LEVEL`` env var (if set and valid) > *verbose* >
    default ``INFO``.

    Parameters
    ----------
    verbose:
        ``True``  → set root log level to ``DEBUG``.
        ``False`` → set root log level to ``INFO``.
        Ignored when the ``LOG_LEVEL`` env var is set.
    json_output:
        When ``True``, attempt to use :class:`pythonjsonlogger.jsonlogger.JsonFormatter`
        for structured JSON-lines output.  Falls back to plain text if the
        ``python-json-logger`` package is not installed.
    """
    level = _level_from_env()
    if level is None:
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
    for existing_handler in root.handlers[:]:
        existing_handler.close()
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


def _level_from_env() -> int | None:
    """Return the log level from ``LOG_LEVEL`` env var, or ``None``."""
    raw = os.environ.get("LOG_LEVEL", "").strip().upper()
    if not raw:
        return None
    level = _VALID_LEVELS.get(raw)
    if level is None:
        logging.getLogger(__name__).warning(
            "Ignoring invalid LOG_LEVEL=%r (accepted: %s)",
            raw,
            ", ".join(sorted(_VALID_LEVELS)),
        )
    return level
