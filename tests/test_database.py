"""Tests for snowfinder_common.database."""

from unittest.mock import MagicMock, patch

import psycopg
import pytest

from snowfinder_common.database import Database
from snowfinder_common.exceptions import DatabaseError


def _make_mock_pool(closed: bool = False):
    """Return a mock ConnectionPool."""
    pool = MagicMock()
    pool.closed = closed
    conn = MagicMock()
    cursor = MagicMock()
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cursor
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    pool.connection.return_value = conn
    return pool


class TestDatabaseInit:
    def test_raises_database_error_for_empty_url(self):
        with pytest.raises(DatabaseError, match="database_url is required"):
            Database("")

    def test_stores_database_url(self):
        db = Database("postgresql://user:pass@host/db")
        assert db._database_url == "postgresql://user:pass@host/db"

    def test_pool_is_none_before_connect(self):
        db = Database("postgresql://localhost/test")
        assert db._pool is None

    def test_default_pool_sizes(self):
        db = Database("postgresql://localhost/test")
        assert db._min_size == 1
        assert db._max_size == 5

    def test_custom_pool_sizes(self):
        db = Database("postgresql://localhost/test", min_size=2, max_size=10)
        assert db._min_size == 2
        assert db._max_size == 10


class TestDatabaseConnect:
    def test_connect_creates_pool(self):
        db = Database("postgresql://localhost/test")
        mock_pool = _make_mock_pool()

        with patch("snowfinder_common.database.ConnectionPool", return_value=mock_pool):
            db.connect()

        assert db._pool is mock_pool

    def test_connect_passes_correct_args(self):
        db = Database("postgresql://localhost/test", min_size=2, max_size=8)
        mock_pool = _make_mock_pool()

        with patch("snowfinder_common.database.ConnectionPool", return_value=mock_pool) as cls:
            db.connect()

        _, kwargs = cls.call_args
        assert kwargs["conninfo"] == "postgresql://localhost/test"
        assert kwargs["min_size"] == 2
        assert kwargs["max_size"] == 8
        assert "row_factory" in kwargs["kwargs"]

    def test_connect_idempotent_when_pool_open(self):
        db = Database("postgresql://localhost/test")
        mock_pool = _make_mock_pool(closed=False)

        with patch("snowfinder_common.database.ConnectionPool", return_value=mock_pool) as cls:
            db.connect()
            db.connect()  # second call should not create a new pool

        assert cls.call_count == 1

    def test_connect_raises_database_error_on_psycopg_error(self):
        db = Database("postgresql://localhost/test")

        with patch(
            "snowfinder_common.database.ConnectionPool",
            side_effect=psycopg.Error("connection refused"),
        ):
            with pytest.raises(DatabaseError, match="Failed to connect"):
                db.connect()

    def test_connect_reopens_closed_pool(self):
        db = Database("postgresql://localhost/test")
        closed_pool = _make_mock_pool(closed=True)
        new_pool = _make_mock_pool(closed=False)
        db._pool = closed_pool

        with patch("snowfinder_common.database.ConnectionPool", return_value=new_pool) as cls:
            db.connect()

        assert cls.call_count == 1
        assert db._pool is new_pool


class TestDatabaseClose:
    def test_close_closes_pool(self):
        db = Database("postgresql://localhost/test")
        mock_pool = _make_mock_pool(closed=False)
        db._pool = mock_pool

        db.close()

        mock_pool.close.assert_called_once()

    def test_close_idempotent_when_already_closed(self):
        db = Database("postgresql://localhost/test")
        mock_pool = _make_mock_pool(closed=True)
        db._pool = mock_pool

        db.close()  # should not call pool.close() on an already-closed pool

        mock_pool.close.assert_not_called()

    def test_close_safe_when_pool_is_none(self):
        db = Database("postgresql://localhost/test")
        db.close()  # should not raise


class TestDatabaseContextManager:
    def test_enter_returns_self(self):
        db = Database("postgresql://localhost/test")
        mock_pool = _make_mock_pool()

        with patch("snowfinder_common.database.ConnectionPool", return_value=mock_pool):
            result = db.__enter__()

        assert result is db

    def test_context_manager_opens_and_closes(self):
        mock_pool = _make_mock_pool()

        with patch("snowfinder_common.database.ConnectionPool", return_value=mock_pool):
            with Database("postgresql://localhost/test"):
                assert mock_pool.closed is False

        mock_pool.close.assert_called_once()

    def test_context_manager_closes_on_exception(self):
        mock_pool = _make_mock_pool()

        with patch("snowfinder_common.database.ConnectionPool", return_value=mock_pool):
            with pytest.raises(ValueError):
                with Database("postgresql://localhost/test"):
                    raise ValueError("oops")

        mock_pool.close.assert_called_once()

    def test_exception_propagates_from_context_manager(self):
        mock_pool = _make_mock_pool()

        with patch("snowfinder_common.database.ConnectionPool", return_value=mock_pool):
            with pytest.raises(RuntimeError, match="test error"):
                with Database("postgresql://localhost/test"):
                    raise RuntimeError("test error")


class TestDatabaseCursor:
    def _setup_db_with_pool(self):
        db = Database("postgresql://localhost/test")
        mock_pool = _make_mock_pool()
        db._pool = mock_pool
        return db, mock_pool

    def test_cursor_yields_cursor_object(self):
        db, mock_pool = self._setup_db_with_pool()

        with patch("snowfinder_common.database.ConnectionPool", return_value=mock_pool):
            with db.cursor() as cur:
                assert cur is not None

    def test_cursor_commits_on_success(self):
        db, mock_pool = self._setup_db_with_pool()
        conn = mock_pool.connection.return_value.__enter__.return_value

        with patch("snowfinder_common.database.ConnectionPool", return_value=mock_pool):
            with db.cursor():
                pass

        conn.commit.assert_called_once()

    def test_cursor_rolls_back_on_exception(self):
        db, mock_pool = self._setup_db_with_pool()
        conn = mock_pool.connection.return_value.__enter__.return_value

        with patch("snowfinder_common.database.ConnectionPool", return_value=mock_pool):
            with pytest.raises(ValueError):
                with db.cursor():
                    raise ValueError("query failed")

        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()

    def test_cursor_re_raises_exception(self):
        db, mock_pool = self._setup_db_with_pool()

        with patch("snowfinder_common.database.ConnectionPool", return_value=mock_pool):
            with pytest.raises(RuntimeError, match="boom"):
                with db.cursor():
                    raise RuntimeError("boom")

    def test_cursor_calls_connect_if_not_connected(self):
        db = Database("postgresql://localhost/test")
        mock_pool = _make_mock_pool()

        with patch("snowfinder_common.database.ConnectionPool", return_value=mock_pool):
            with db.cursor():
                pass

        assert db._pool is mock_pool


class TestDatabaseHealthCheck:
    def test_returns_true_when_query_succeeds(self):
        db = Database("postgresql://localhost/test")
        mock_pool = _make_mock_pool()

        with patch("snowfinder_common.database.ConnectionPool", return_value=mock_pool):
            result = db.health_check()

        assert result is True

    def test_returns_false_when_query_raises(self):
        db = Database("postgresql://localhost/test")

        with patch.object(db, "cursor", side_effect=Exception("db down")):
            result = db.health_check()

        assert result is False

    def test_does_not_raise_on_failure(self):
        db = Database("postgresql://localhost/test")

        with patch.object(db, "cursor", side_effect=psycopg.Error("timeout")):
            result = db.health_check()  # should not raise

        assert result is False


class TestDatabaseRepr:
    def test_repr_shows_connected_false_before_connect(self):
        db = Database("postgresql://localhost/test")
        r = repr(db)
        assert "connected=False" in r

    def test_repr_shows_connected_true_after_connect(self):
        db = Database("postgresql://localhost/test")
        mock_pool = _make_mock_pool(closed=False)

        with patch("snowfinder_common.database.ConnectionPool", return_value=mock_pool):
            db.connect()

        assert "connected=True" in repr(db)

    def test_repr_truncates_long_url(self):
        long_url = "postgresql://user:verylongpassword@very-long-hostname.example.com:5432/mydb"
        db = Database(long_url)
        r = repr(db)
        assert "…" in r

    def test_repr_no_truncation_for_short_url(self):
        short_url = "postgresql://localhost/db"
        db = Database(short_url)
        r = repr(db)
        assert "…" not in r
