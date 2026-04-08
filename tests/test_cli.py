"""Tests for snowfinder_common.cli."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from snowfinder_common.cli import run_service
from snowfinder_common.database import Database


def _make_mock_db_class(raises: Exception | None = None):
    """Return a (mock_db_class, mock_db_instance) pair."""
    mock_db_instance = MagicMock()
    mock_db_instance.__enter__ = MagicMock(return_value=mock_db_instance)
    mock_db_instance.__exit__ = MagicMock(return_value=False)
    if raises is not None:
        mock_db_instance.__enter__.side_effect = raises
    mock_db_class = MagicMock(return_value=mock_db_instance)
    return mock_db_class, mock_db_instance


class TestRunServiceSuccess:
    def test_calls_pipeline_fn_with_db(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        pipeline_fn = MagicMock()
        mock_db_class, mock_db_instance = _make_mock_db_class()

        with (
            patch("snowfinder_common.cli.load_dotenv"),
            patch("sys.argv", ["prog"]),
            patch("snowfinder_common.cli.configure_logging"),
        ):
            run_service("myservice", pipeline_fn, db_class=mock_db_class)

        pipeline_fn.assert_called_once_with(mock_db_instance)

    def test_instantiates_db_with_database_url(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/mydb")
        pipeline_fn = MagicMock()
        mock_db_class, _ = _make_mock_db_class()

        with (
            patch("snowfinder_common.cli.load_dotenv"),
            patch("sys.argv", ["prog"]),
            patch("snowfinder_common.cli.configure_logging"),
        ):
            run_service("myservice", pipeline_fn, db_class=mock_db_class)

        mock_db_class.assert_called_once_with("postgresql://localhost/mydb")

    def test_verbose_flag_passed_to_configure_logging(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        pipeline_fn = MagicMock()
        mock_db_class, _ = _make_mock_db_class()

        with (
            patch("snowfinder_common.cli.load_dotenv"),
            patch("sys.argv", ["prog", "--verbose"]),
            patch("snowfinder_common.cli.configure_logging") as mock_conf,
        ):
            run_service("myservice", pipeline_fn, db_class=mock_db_class)

        mock_conf.assert_called_once_with(verbose=True)

    def test_verbose_defaults_to_false(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        pipeline_fn = MagicMock()
        mock_db_class, _ = _make_mock_db_class()

        with (
            patch("snowfinder_common.cli.load_dotenv"),
            patch("sys.argv", ["prog"]),
            patch("snowfinder_common.cli.configure_logging") as mock_conf,
        ):
            run_service("myservice", pipeline_fn, db_class=mock_db_class)

        mock_conf.assert_called_once_with(verbose=False)

    def test_database_url_from_cli_flag(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        pipeline_fn = MagicMock()
        mock_db_class, _ = _make_mock_db_class()

        with (
            patch("snowfinder_common.cli.load_dotenv"),
            patch("sys.argv", ["prog", "--database-url", "postgresql://host/flagdb"]),
            patch("snowfinder_common.cli.configure_logging"),
        ):
            run_service("myservice", pipeline_fn, db_class=mock_db_class)

        mock_db_class.assert_called_once_with("postgresql://host/flagdb")

    def test_db_used_as_context_manager(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        pipeline_fn = MagicMock()
        mock_db_class, mock_db_instance = _make_mock_db_class()

        with (
            patch("snowfinder_common.cli.load_dotenv"),
            patch("sys.argv", ["prog"]),
            patch("snowfinder_common.cli.configure_logging"),
        ):
            run_service("myservice", pipeline_fn, db_class=mock_db_class)

        mock_db_instance.__enter__.assert_called_once()
        mock_db_instance.__exit__.assert_called_once()

    def test_db_class_parameter_has_default_database_as_default(self):
        """The db_class default should be the common Database class."""
        import inspect
        from snowfinder_common.database import Database

        sig = inspect.signature(run_service)
        default = sig.parameters["db_class"].default
        assert default is Database


class TestRunServiceMissingDatabaseUrl:
    def test_exits_with_code_1_when_no_database_url(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        pipeline_fn = MagicMock()

        with (
            patch("snowfinder_common.cli.load_dotenv"),
            patch("sys.argv", ["prog"]),
            patch("snowfinder_common.cli.configure_logging"),
            pytest.raises(SystemExit) as exc_info,
        ):
            run_service("myservice", pipeline_fn)

        assert exc_info.value.code == 1

    def test_pipeline_not_called_when_no_database_url(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        pipeline_fn = MagicMock()

        with (
            patch("snowfinder_common.cli.load_dotenv"),
            patch("sys.argv", ["prog"]),
            patch("snowfinder_common.cli.configure_logging"),
            pytest.raises(SystemExit),
        ):
            run_service("myservice", pipeline_fn)

        pipeline_fn.assert_not_called()


class TestRunServicePipelineError:
    def test_exits_with_code_1_when_pipeline_raises(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        pipeline_fn = MagicMock(side_effect=RuntimeError("pipeline boom"))
        mock_db_class, _ = _make_mock_db_class()

        with (
            patch("snowfinder_common.cli.load_dotenv"),
            patch("sys.argv", ["prog"]),
            patch("snowfinder_common.cli.configure_logging"),
            pytest.raises(SystemExit) as exc_info,
        ):
            run_service("myservice", pipeline_fn, db_class=mock_db_class)

        assert exc_info.value.code == 1

    def test_exits_when_db_context_manager_raises(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        pipeline_fn = MagicMock()
        mock_db_class, _ = _make_mock_db_class(raises=ConnectionError("db refused"))

        with (
            patch("snowfinder_common.cli.load_dotenv"),
            patch("sys.argv", ["prog"]),
            patch("snowfinder_common.cli.configure_logging"),
            pytest.raises(SystemExit) as exc_info,
        ):
            run_service("myservice", pipeline_fn, db_class=mock_db_class)

        assert exc_info.value.code == 1

    def test_pipeline_called_once_before_error(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        pipeline_fn = MagicMock(side_effect=ValueError("bad data"))
        mock_db_class, _ = _make_mock_db_class()

        with (
            patch("snowfinder_common.cli.load_dotenv"),
            patch("sys.argv", ["prog"]),
            patch("snowfinder_common.cli.configure_logging"),
            pytest.raises(SystemExit),
        ):
            run_service("myservice", pipeline_fn, db_class=mock_db_class)

        pipeline_fn.assert_called_once()
