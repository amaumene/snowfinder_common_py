"""Tests for snowfinder_common.cli."""

import argparse
from unittest.mock import MagicMock, patch

import pytest

from snowfinder_common.cli import run_service


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
    def test_setup_parser_registers_extra_arguments(self, monkeypatch):
        monkeypatch.setenv("DATABASE_PATH", "/tmp/test.db")
        pipeline_fn = MagicMock()
        mock_db_class, _ = _make_mock_db_class()

        def setup_parser(parser):
            parser.add_argument("--extract-msm", action="store_true")

        with (
            patch("snowfinder_common.cli.load_dotenv"),
            patch("sys.argv", ["prog", "--extract-msm"]),
            patch("snowfinder_common.cli.configure_logging"),
        ):
            run_service(
                "myservice",
                pipeline_fn,
                db_class=mock_db_class,
                setup_parser=setup_parser,
            )

        args = pipeline_fn.call_args.args[1]
        assert args.extract_msm is True

    def test_setup_parser_receives_argument_parser_with_expected_arguments(self, monkeypatch):
        monkeypatch.setenv("DATABASE_PATH", "/tmp/test.db")
        pipeline_fn = MagicMock()
        mock_db_class, _ = _make_mock_db_class()
        seen = {}

        def setup_parser(parser):
            seen["parser"] = parser

        with (
            patch("snowfinder_common.cli.load_dotenv"),
            patch("sys.argv", ["prog"]),
            patch("snowfinder_common.cli.configure_logging"),
        ):
            run_service(
                "myservice",
                pipeline_fn,
                db_class=mock_db_class,
                setup_parser=setup_parser,
            )

        parser = seen["parser"]
        assert isinstance(parser, argparse.ArgumentParser)
        action_by_dest = {action.dest: action for action in parser._actions}
        assert "verbose" in action_by_dest
        assert "database_path" in action_by_dest
        assert action_by_dest["verbose"].option_strings == ["--verbose", "-v"]
        assert action_by_dest["database_path"].option_strings == ["--database-path"]

    def test_calls_pipeline_fn_with_db(self, monkeypatch):
        monkeypatch.setenv("DATABASE_PATH", "/tmp/test.db")
        pipeline_fn = MagicMock()
        mock_db_class, mock_db_instance = _make_mock_db_class()
        args_instance = None

        with (
            patch("snowfinder_common.cli.load_dotenv"),
            patch("sys.argv", ["prog"]),
            patch("snowfinder_common.cli.configure_logging"),
        ):
            run_service("myservice", pipeline_fn, db_class=mock_db_class)
            args_instance = pipeline_fn.call_args.args[1]

        pipeline_fn.assert_called_once_with(mock_db_instance, args_instance)

    def test_instantiates_db_with_database_path(self, monkeypatch):
        monkeypatch.setenv("DATABASE_PATH", "/tmp/mydb.db")
        pipeline_fn = MagicMock()
        mock_db_class, _ = _make_mock_db_class()

        with (
            patch("snowfinder_common.cli.load_dotenv"),
            patch("sys.argv", ["prog"]),
            patch("snowfinder_common.cli.configure_logging"),
        ):
            run_service("myservice", pipeline_fn, db_class=mock_db_class)

        mock_db_class.assert_called_once_with("/tmp/mydb.db")

    def test_verbose_flag_passed_to_configure_logging(self, monkeypatch):
        monkeypatch.setenv("DATABASE_PATH", "/tmp/test.db")
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
        monkeypatch.setenv("DATABASE_PATH", "/tmp/test.db")
        pipeline_fn = MagicMock()
        mock_db_class, _ = _make_mock_db_class()

        with (
            patch("snowfinder_common.cli.load_dotenv"),
            patch("sys.argv", ["prog"]),
            patch("snowfinder_common.cli.configure_logging") as mock_conf,
        ):
            run_service("myservice", pipeline_fn, db_class=mock_db_class)

        mock_conf.assert_called_once_with(verbose=False)

    def test_database_path_from_cli_flag(self, monkeypatch):
        monkeypatch.delenv("DATABASE_PATH", raising=False)
        pipeline_fn = MagicMock()
        mock_db_class, _ = _make_mock_db_class()

        with (
            patch("snowfinder_common.cli.load_dotenv"),
            patch("sys.argv", ["prog", "--database-path", "/tmp/flagdb.db"]),
            patch("snowfinder_common.cli.configure_logging"),
        ):
            run_service("myservice", pipeline_fn, db_class=mock_db_class)

        mock_db_class.assert_called_once_with("/tmp/flagdb.db")

    def test_db_used_as_context_manager(self, monkeypatch):
        monkeypatch.setenv("DATABASE_PATH", "/tmp/test.db")
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


class TestRunServiceMissingDatabasePath:
    def test_exits_with_code_1_when_no_database_path(self, monkeypatch):
        monkeypatch.delenv("DATABASE_PATH", raising=False)
        pipeline_fn = MagicMock()

        with (
            patch("snowfinder_common.cli.load_dotenv"),
            patch("sys.argv", ["prog"]),
            patch("snowfinder_common.cli.configure_logging"),
            pytest.raises(SystemExit) as exc_info,
        ):
            run_service("myservice", pipeline_fn)

        assert exc_info.value.code == 1

    def test_pipeline_not_called_when_no_database_path(self, monkeypatch):
        monkeypatch.delenv("DATABASE_PATH", raising=False)
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
        monkeypatch.setenv("DATABASE_PATH", "/tmp/test.db")
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
        monkeypatch.setenv("DATABASE_PATH", "/tmp/test.db")
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
        monkeypatch.setenv("DATABASE_PATH", "/tmp/test.db")
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
