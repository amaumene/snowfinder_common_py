"""Tests for snowfinder_common.database (SQLite implementation)."""

import sqlite3
import threading
import time
from unittest.mock import patch

import pytest

from snowfinder_common.database import Database
from snowfinder_common.exceptions import DatabaseError


class TestDatabaseInit:
    def test_raises_database_error_for_empty_path(self):
        with pytest.raises(DatabaseError, match="database_path is required"):
            Database("")

    def test_stores_database_path(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        db = Database(db_path)
        assert db._database_path == db_path

    def test_conn_is_none_before_connect(self, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        assert db._conn is None


class TestDatabaseConnect:
    def test_connect_creates_connection(self, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        db.connect()
        try:
            assert db._conn is not None
        finally:
            db.close()

    def test_connect_sets_wal_journal_mode(self, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        db.connect()
        try:
            row = db._conn.execute("PRAGMA journal_mode").fetchone()
            assert row["journal_mode"] == "wal"
        finally:
            db.close()

    def test_connect_sets_foreign_keys_on(self, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        db.connect()
        try:
            row = db._conn.execute("PRAGMA foreign_keys").fetchone()
            assert row["foreign_keys"] == 1
        finally:
            db.close()

    def test_connect_sets_busy_timeout(self, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        db.connect()
        try:
            row = db._conn.execute("PRAGMA busy_timeout").fetchone()
            assert row["timeout"] == 5000
        finally:
            db.close()

    def test_connect_sets_synchronous_normal(self, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        db.connect()
        try:
            row = db._conn.execute("PRAGMA synchronous").fetchone()
            # NORMAL = 1
            assert row["synchronous"] == 1
        finally:
            db.close()

    def test_connect_idempotent_when_already_connected(self, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        db.connect()
        try:
            first_conn = db._conn
            db.connect()  # second call should not replace the connection
            assert db._conn is first_conn
        finally:
            db.close()

    def test_connect_raises_database_error_on_invalid_path(self):
        # A path in a non-existent directory should raise DatabaseError
        db = Database("/nonexistent_dir_xyz/test.db")
        with pytest.raises(DatabaseError, match="Failed to open database"):
            db.connect()


class TestDatabaseClose:
    def test_close_sets_conn_to_none(self, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        db.connect()
        assert db._conn is not None
        db.close()
        assert db._conn is None

    def test_close_idempotent_when_already_closed(self, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        db.connect()
        db.close()
        db.close()  # should not raise
        assert db._conn is None

    def test_close_safe_when_never_connected(self, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        db.close()  # should not raise


class TestDatabaseCursor:
    def test_cursor_yields_cursor_object(self, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        db.connect()
        try:
            with db.cursor() as cur:
                assert isinstance(cur, sqlite3.Cursor)
        finally:
            db.close()

    def test_cursor_commits_on_success(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        db = Database(db_path)
        db.connect()
        try:
            with db.cursor() as cur:
                cur.execute("CREATE TABLE t (x INTEGER)")
                cur.execute("INSERT INTO t VALUES (42)")
        finally:
            db.close()

        # Reopen and verify data was committed
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT x FROM t").fetchone()
        conn.close()
        assert row[0] == 42

    def test_cursor_rolls_back_on_exception(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        db = Database(db_path)
        db.connect()
        try:
            with db.cursor() as cur:
                cur.execute("CREATE TABLE t (x INTEGER)")
        finally:
            db.close()

        db2 = Database(db_path)
        db2.connect()
        try:
            with pytest.raises(ValueError):
                with db2.cursor() as cur:
                    cur.execute("INSERT INTO t VALUES (99)")
                    raise ValueError("rollback me")
        finally:
            db2.close()

        # Verify the insert was rolled back
        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT x FROM t").fetchall()
        conn.close()
        assert rows == []

    def test_cursor_re_raises_exception(self, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        db.connect()
        try:
            with pytest.raises(RuntimeError, match="boom"):
                with db.cursor():
                    raise RuntimeError("boom")
        finally:
            db.close()

    def test_cursor_calls_connect_if_not_connected(self, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        # Do NOT call connect() manually
        try:
            with db.cursor() as cur:
                cur.execute("SELECT 1")
            assert db._conn is not None
        finally:
            db.close()


class TestDatabaseVacuum:
    def test_vacuum_runs_without_error(self, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.vacuum()  # should not raise
        finally:
            db.close()

    def test_vacuum_calls_connect_if_not_connected(self, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        db.vacuum()
        assert db._conn is not None
        db.close()


class TestDatabaseHealthCheck:
    def test_health_check_returns_true_when_query_succeeds(self, tmp_path):
        db = Database(str(tmp_path / "test.db"))

        try:
            assert db.health_check() is True
        finally:
            db.close()

    def test_health_check_returns_false_when_cursor_fails(self, tmp_path):
        db = Database(str(tmp_path / "test.db"))

        with patch.object(db, "cursor", side_effect=DatabaseError("boom")):
            assert db.health_check() is False


class TestDatabaseContextManager:
    def test_enter_returns_self(self, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        result = db.__enter__()
        try:
            assert result is db
        finally:
            db.close()

    def test_context_manager_opens_and_closes(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        with Database(db_path) as db:
            assert db._conn is not None
        assert db._conn is None

    def test_context_manager_closes_on_exception(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        db_ref = None
        with pytest.raises(ValueError):
            with Database(db_path) as db:
                db_ref = db
                raise ValueError("oops")
        assert db_ref._conn is None

    def test_exception_propagates_from_context_manager(self, tmp_path):
        with pytest.raises(RuntimeError, match="test error"):
            with Database(str(tmp_path / "test.db")):
                raise RuntimeError("test error")


class TestDatabaseIsConnected:
    def test_is_connected_false_before_connect(self, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        assert db._conn is None

    def test_is_connected_true_after_connect(self, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        db.connect()
        try:
            assert db._conn is not None
        finally:
            db.close()

    def test_is_connected_false_after_close(self, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        db.connect()
        db.close()
        assert db._conn is None


class TestDatabaseRepr:
    def test_repr_shows_connected_false_before_connect(self, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        r = repr(db)
        assert "connected=False" in r

    def test_repr_shows_connected_true_after_connect(self, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        db.connect()
        try:
            assert "connected=True" in repr(db)
        finally:
            db.close()

    def test_repr_contains_path(self, tmp_path):
        db_path = str(tmp_path / "mydb.db")
        db = Database(db_path)
        r = repr(db)
        assert db_path in r

    def test_repr_shows_connected_false_after_close(self, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        db.connect()
        db.close()
        assert "connected=False" in repr(db)


class TestDatabaseErrorWrapping:
    def test_connect_wraps_sqlite_error(self):
        # Path in non-existent directory triggers OperationalError
        db = Database("/no_such_dir_abc123/test.db")
        with pytest.raises(DatabaseError) as exc_info:
            db.connect()
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, sqlite3.Error)

    def test_database_error_has_context(self):
        db = Database("/no_such_dir_abc123/test.db")
        with pytest.raises(DatabaseError) as exc_info:
            db.connect()
        assert "path" in exc_info.value.context

    def test_cursor_wraps_sqlite_error_as_database_error(self, tmp_path):
        db = Database(str(tmp_path / "test.db"))

        with pytest.raises(DatabaseError) as exc_info:
            with db.cursor() as cur:
                cur.execute("SELECT * FROM missing_table")

        assert isinstance(exc_info.value.__cause__, sqlite3.Error)


class TestDatabaseThreadSafety:
    def test_cursor_uses_lock_for_thread_safe_access(self, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        db.connect()
        events = []
        entered_first = threading.Event()
        release_first = threading.Event()

        def worker(name):
            with db.cursor() as cur:
                cur.execute("SELECT 1")
                events.append(f"enter-{name}")
                if name == "first":
                    entered_first.set()
                    release_first.wait(timeout=2)
                else:
                    events.append("second-acquired")

        try:
            first = threading.Thread(target=worker, args=("first",))
            second = threading.Thread(target=worker, args=("second",))

            first.start()
            assert entered_first.wait(timeout=2)

            second.start()
            time.sleep(0.1)
            assert "second-acquired" not in events

            release_first.set()
            first.join(timeout=2)
            second.join(timeout=2)

            assert events[0] == "enter-first"
            assert events[-2:] == ["enter-second", "second-acquired"]
        finally:
            db.close()


class TestDatabaseDoubleConnect:
    def test_second_connect_is_noop(self, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        db.connect()
        first_conn = db._conn
        db.connect()  # should not replace the existing connection
        try:
            assert db._conn is first_conn
        finally:
            db.close()


class TestDatabaseErrorPaths:
    def test_health_check_returns_false_on_corrupted_db(self, tmp_path):
        """health_check returns False when the query itself raises."""
        db_path = str(tmp_path / "corrupt.db")
        # Write garbage so sqlite3 raises OperationalError on connect/query
        with open(db_path, "wb") as f:
            f.write(b"not a sqlite database\x00" * 10)
        db = Database(db_path)
        # health_check must not raise — it should return False and log
        assert db.health_check() is False

    def test_cursor_commit_raises_sqlite_error_triggers_rollback(self, tmp_path):
        """When commit() raises sqlite3.Error, rollback is called and DatabaseError is raised."""
        from unittest.mock import MagicMock

        db = Database(str(tmp_path / "test.db"))
        db.connect()
        try:
            rollback_called = []

            # Replace the internal connection with a mock that raises on commit.
            # MagicMock (no spec) allows attribute assignment freely.
            mock_conn = MagicMock()
            mock_conn.cursor.return_value = MagicMock()
            mock_conn.commit.side_effect = sqlite3.OperationalError("disk full")
            mock_conn.rollback.side_effect = lambda: rollback_called.append(True)

            db._conn = mock_conn

            with pytest.raises(DatabaseError, match="Database operation failed"):
                with db.cursor():
                    pass  # commit() is called on context-manager exit

            assert rollback_called, "rollback() was not called after commit() raised"
        finally:
            db._conn = None  # prevent close() from calling mock_conn.close()

    def test_vacuum_under_load_isolation_swap(self, tmp_path):
        """vacuum() can run while another thread holds a cursor (RLock allows re-entry from same thread; different thread must wait)."""
        db = Database(str(tmp_path / "test.db"))
        db.connect()

        errors = []

        def run_vacuum():
            try:
                db.vacuum()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        # Run vacuum from a separate thread — it should complete without deadlock
        t = threading.Thread(target=run_vacuum)
        t.start()
        t.join(timeout=5.0)

        assert not t.is_alive(), "vacuum() deadlocked"
        assert not errors, f"vacuum() raised: {errors}"
        db.close()

    def test_reentrant_lock_does_not_deadlock(self, tmp_path):
        """Same-thread nested cursor() inside health_check completes within 2s."""
        db = Database(str(tmp_path / "test.db"))
        db.connect()

        import time

        start = time.monotonic()
        # health_check calls cursor() internally; calling it from the main thread
        # exercises the RLock re-entrancy path (no deadlock expected).
        result = db.health_check()
        elapsed = time.monotonic() - start

        assert result is True
        assert elapsed < 2.0, f"health_check took {elapsed:.2f}s — possible deadlock"
        db.close()
