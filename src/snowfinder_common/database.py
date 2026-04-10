"""Shared SQLite database interface for snowfinder services.

Usage::

    from snowfinder_common.database import Database

    # As a context manager (recommended):
    with Database(database_path) as db:
        with db.cursor() as cur:
            cur.execute("SELECT 1")

    # Manual lifecycle:
    db = Database(database_path)
    db.connect()
    try:
        with db.cursor() as cur:
            cur.execute("SELECT 1")
    finally:
        db.close()
"""

import logging
import sqlite3
import threading
from contextlib import contextmanager
from collections.abc import Generator
from typing import Self

from .exceptions import DatabaseError

logger = logging.getLogger(__name__)


def _dict_factory(cursor: sqlite3.Cursor, row: tuple) -> dict:
    """Row factory that returns rows as dicts keyed by column name."""
    fields = [column[0] for column in cursor.description]
    return dict(zip(fields, row))


class Database:
    """SQLite database interface.

    The caller is responsible for providing a valid ``database_path``; there is
    no implicit fallback to environment variables.  This keeps the class
    side-effect-free and easy to test.

    Parameters
    ----------
    database_path:
        Path to the SQLite database file, e.g. ``"./snowfinder.db"``.
    """

    def __init__(self, database_path: str) -> None:
        if not database_path:
            raise DatabaseError(
                "database_path is required and must not be empty.",
                context={"database_path": database_path},
            )
        self._database_path = database_path
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open the database connection (idempotent if already open)."""
        with self._lock:
            if self._conn is None:
                conn: sqlite3.Connection | None = None
                try:
                    conn = sqlite3.connect(
                        self._database_path,
                        check_same_thread=False,
                    )
                    conn.row_factory = _dict_factory
                    # Performance and safety pragmas
                    conn.execute("PRAGMA journal_mode = WAL")
                    conn.execute("PRAGMA foreign_keys = ON")
                    conn.execute("PRAGMA busy_timeout = 5000")
                    conn.execute("PRAGMA synchronous = NORMAL")
                    self._conn = conn
                    logger.debug("Database connection established: %s", self._database_path)
                except sqlite3.Error as exc:
                    if conn is not None:
                        conn.close()
                    raise DatabaseError(
                        f"Failed to open database: {exc}",
                        context={"path": self._database_path},
                    ) from exc

    def close(self) -> None:
        """Close the database connection (idempotent if already closed)."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
                logger.debug("Database connection closed.")

    # ------------------------------------------------------------------
    # Cursor context manager
    # ------------------------------------------------------------------

    @contextmanager
    def cursor(self) -> Generator[sqlite3.Cursor, None, None]:
        """Yield a cursor, committing on success or rolling back on error.

        Rolls back the current transaction and logs a warning if an exception
        is raised inside the ``with`` block, then re-raises the exception.

        Yields
        ------
        sqlite3.Cursor
            A cursor whose rows are returned as dicts.
        """
        self.connect()
        if self._conn is None:
            raise RuntimeError("unreachable: connect() succeeded but _conn is None")
        with self._lock:
            cur = self._conn.cursor()
            try:
                yield cur
                self._conn.commit()
            except sqlite3.Error as exc:
                logger.warning(
                    "Database error inside cursor block — rolling back transaction.",
                    exc_info=True,
                )
                self._conn.rollback()
                raise DatabaseError(f"Database operation failed: {exc}") from exc
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
    # Maintenance
    # ------------------------------------------------------------------

    def vacuum(self) -> None:
        """Run VACUUM to reclaim unused space.

        VACUUM cannot run inside a transaction, so this commits any pending
        work and temporarily switches to autocommit mode.
        """
        self.connect()
        if self._conn is None:
            raise RuntimeError("unreachable: connect() succeeded but _conn is None")
        with self._lock:
            logger.debug("VACUUM")
            self._conn.commit()
            old_isolation = self._conn.isolation_level
            self._conn.isolation_level = None
            try:
                self._conn.execute("VACUUM")
            except sqlite3.Error as exc:
                raise DatabaseError(f"Database operation failed: {exc}") from exc
            finally:
                self._conn.isolation_level = old_isolation

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
            logger.warning("Database health check failed: %s", exc)
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
        connected = self._conn is not None
        return f"Database(path={self._database_path!r}, connected={connected})"
