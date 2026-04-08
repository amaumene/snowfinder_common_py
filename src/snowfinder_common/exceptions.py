"""Custom exception hierarchy for snowfinder services.

All exceptions carry a structured ``context`` dict for machine-readable
diagnostic information alongside the human-readable message.
"""


class SnowfinderError(Exception):
    """Base exception for all snowfinder errors.

    Carries an optional ``context`` dict with structured diagnostic data
    so callers can inspect failure details programmatically.
    """

    def __init__(self, message: str, context: dict | None = None) -> None:
        super().__init__(message)
        self.context: dict = context or {}

    def __repr__(self) -> str:
        ctx = f", context={self.context!r}" if self.context else ""
        return f"{type(self).__name__}({str(self)!r}{ctx})"


class ConfigError(SnowfinderError):
    """Raised when configuration is missing, invalid, or inconsistent.

    Examples: missing required environment variable, out-of-range parameter,
    conflicting option combination.
    """


class DatabaseError(SnowfinderError):
    """Raised when a database operation fails.

    Examples: connection refused, query error, constraint violation,
    unexpected result shape.
    """


class FetchError(SnowfinderError):
    """Raised when an HTTP fetch or file download fails.

    Examples: 404 Not Found, connection timeout, too many retries exhausted,
    unexpected HTTP status code.
    """


class ParseError(SnowfinderError):
    """Raised when parsing or deserialising data fails.

    Examples: malformed NetCDF file, unexpected JSON schema, missing required
    field in an API response.
    """


class AnalysisError(SnowfinderError):
    """Raised when a statistical or algorithmic analysis step fails.

    Examples: insufficient data for peak detection, singular matrix in
    regression, NaN propagation that cannot be recovered.
    """


class ValidationError(SnowfinderError):
    """Raised when input data fails validation checks.

    Examples: resort ID not found, date range outside supported bounds,
    coordinate outside the model grid extent.
    """
