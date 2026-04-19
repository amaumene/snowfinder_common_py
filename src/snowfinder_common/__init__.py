"""Shared utilities for snowfinder Python services.

Top-level re-exports allow consumers to write::

    from snowfinder_common import Database, download_file, configure_logging

Deep imports (``from snowfinder_common.database import Database``) continue
to work unchanged.
"""

from .database import Database
from .exceptions import (
    AnalysisError,
    ConfigError,
    DatabaseError,
    FetchError,
    ParseError,
    SnowfinderError,
    ValidationError,
)
from .http import download_file
from .logging_config import configure_logging

__all__ = [
    "AnalysisError",
    "ConfigError",
    "Database",
    "DatabaseError",
    "FetchError",
    "ParseError",
    "SnowfinderError",
    "ValidationError",
    "configure_logging",
    "download_file",
]
