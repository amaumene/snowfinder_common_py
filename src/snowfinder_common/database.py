"""Shared PostgreSQL database interface for snowfinder services.

Usage::

    from snowfinder_common.database import Database

    # As a context manager (recommended):
    with Database(database_url) as db:
        with db.cursor() as cur:
            cur.execute("SELECT 1")

    # Manual lifecycle:
    db = Database(database_url)
    db.connect()
    try:
        with db.cursor() as cur:
            cur.execute("SELECT now()")
    finally:
        db.close()
"""

import logging
from contextlib import contextmanager
from collections.abc import Generator
from typing import Self

import psycopg2
import psycopg2.extensions
from psycopg2.extras import DictCursor

from .exceptions import DatabaseError

logger = logging.getLogger(__name__)


class Database:
    """PostgreSQL database interface.

    The caller is responsible for providing a valid ``database_url``; there is
    no implicit fallback to environment variables.  This keeps the class
    side-effect-free and easy to test.

    Parameters
    ----------
    database_url:
        A libpq connection string or DSN URL, e.g.
        ``"postgresql://user:pass@host:5432/dbname"``.
    """

    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise DatabaseError(
                "database_url is required and must not be empty.",
                context={"database_url": database_url},
            )
        self._database_url = database_url
        self._conn: psycopg2.extensions.connection | None = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open the database connection (idempotent if already open)."""
        if self._conn is None or self._conn.closed:
            try:
                self._conn = psycopg2.connect(self._database_url)
                logger.debug("Database connection established.")
            except psycopg2.Error as exc:
                raise DatabaseError(
                    f"Failed to connect to database: {exc}",
                    context={"url_prefix": self._database_url[:30]},
                ) from exc

    def close(self) -> None:
        """Close the database connection (idempotent if already closed)."""
        if self._conn is not None and not self._conn.closed:
            self._conn.close()
            logger.debug("Database connection closed.")

    # ------------------------------------------------------------------
    # Cursor context manager
    # ------------------------------------------------------------------

    @contextmanager
    def cursor(self) -> Generator[DictCursor, None, None]:
        """Yield a ``DictCursor``, committing on success or rolling back on error.

        Rolls back the current transaction and logs a warning if an exception
        is raised inside the ``with`` block, then re-raises the exception.

        Yields
        ------
        psycopg2.extras.DictCursor
        """
        self.connect()
        assert self._conn is not None  # guaranteed by connect()
        cur: DictCursor = self._conn.cursor(cursor_factory=DictCursor)
        try:
            yield cur
            self._conn.commit()
        except Exception:
            logger.warning(
                "Exception inside cursor block — rolling back transaction.",
                exc_info=True,
            )
            self._conn.rollback()
            raise
        finally:
            cur.close()

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        """Run ``SELECT 1`` and return ``True`` if the database is reachable.

        Returns ``False`` (and logs the error) rather than raising, so callers
        can use this as a simple liveness probe.
        """
        try:
            with self.cursor() as cur:
                cur.execute("SELECT 1")
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Database health check failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Context manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> Self:
        """Open connection and return self."""
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Close connection on exit (exceptions propagate normally)."""
        self.close()

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        # Truncate URL to avoid leaking credentials in logs/tracebacks.
        url_preview = self._database_url[:40] + ("…" if len(self._database_url) > 40 else "")
        connected = self._conn is not None and not self._conn.closed
        return f"Database(url={url_preview!r}, connected={connected})"
