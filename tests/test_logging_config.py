"""Tests for snowfinder_common.logging_config."""

import builtins
import logging

import pytest

from snowfinder_common.logging_config import _level_from_env, configure_logging


@pytest.fixture(autouse=True)
def reset_root_logger():
    root = logging.getLogger()
    original_level = root.level
    original_handlers = root.handlers[:]
    root.handlers.clear()
    try:
        yield
    finally:
        current_handlers = root.handlers[:]
        for handler in current_handlers:
            if handler not in original_handlers:
                handler.close()
        root.handlers.clear()
        root.setLevel(original_level)
        root.handlers[:] = original_handlers


class TestLevelFromEnv:
    def test_returns_none_when_env_not_set(self, monkeypatch):
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        assert _level_from_env() is None

    def test_returns_none_for_empty_string(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "")
        assert _level_from_env() is None

    def test_returns_none_for_whitespace(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "   ")
        assert _level_from_env() is None

    @pytest.mark.parametrize(
        ("env_value", "expected"),
        [
            ("DEBUG", logging.DEBUG),
            ("INFO", logging.INFO),
            ("WARNING", logging.WARNING),
            ("ERROR", logging.ERROR),
        ],
    )
    def test_returns_correct_level_for_valid_values(self, monkeypatch, env_value, expected):
        monkeypatch.setenv("LOG_LEVEL", env_value)
        assert _level_from_env() == expected

    @pytest.mark.parametrize("env_value", ["debug", "info", "warning", "error"])
    def test_case_insensitive(self, monkeypatch, env_value):
        monkeypatch.setenv("LOG_LEVEL", env_value)
        assert _level_from_env() is not None

    def test_returns_none_for_invalid_level(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "VERBOSE")
        result = _level_from_env()
        assert result is None

    def test_strips_leading_trailing_whitespace(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "  INFO  ")
        assert _level_from_env() == logging.INFO


class TestConfigureLogging:
    def test_default_sets_info_level(self, monkeypatch):
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        configure_logging()
        assert logging.getLogger().level == logging.INFO

    def test_verbose_sets_debug_level(self, monkeypatch):
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        configure_logging(verbose=True)
        assert logging.getLogger().level == logging.DEBUG

    def test_env_var_overrides_verbose_flag(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "ERROR")
        configure_logging(verbose=True)
        assert logging.getLogger().level == logging.ERROR

    def test_env_var_debug_overrides_default(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        configure_logging(verbose=False)
        assert logging.getLogger().level == logging.DEBUG

    def test_adds_exactly_one_handler(self, monkeypatch):
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        configure_logging()
        root = logging.getLogger()
        assert len(root.handlers) == 1

    def test_idempotent_does_not_duplicate_handlers(self, monkeypatch):
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        configure_logging()
        configure_logging()
        configure_logging()
        root = logging.getLogger()
        assert len(root.handlers) == 1

    def test_handler_is_stream_handler(self, monkeypatch):
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        configure_logging()
        root = logging.getLogger()
        assert isinstance(root.handlers[0], logging.StreamHandler)

    def test_plain_text_formatter_is_default(self, monkeypatch):
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        configure_logging(json_output=False)
        root = logging.getLogger()
        formatter = root.handlers[0].formatter
        # Plain text formatter should not be a JSON formatter type
        assert "JsonFormatter" not in type(formatter).__name__

    def test_json_output_falls_back_gracefully_when_package_missing(self, monkeypatch):
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "pythonjsonlogger":
                raise ImportError("simulated missing dependency")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        configure_logging(json_output=True)
        root = logging.getLogger()
        assert len(root.handlers) == 1

    def test_json_output_fallback_uses_plain_text_formatter(self, monkeypatch, caplog):
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "pythonjsonlogger":
                raise ImportError("simulated missing dependency")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        with caplog.at_level(logging.WARNING):
            configure_logging(json_output=True)

        formatter = logging.getLogger().handlers[0].formatter
        assert "JsonFormatter" not in type(formatter).__name__
        assert any(
            "falling back to plain-text logging" in record.message for record in caplog.records
        )

    def test_warning_level_from_env(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "WARNING")
        configure_logging()
        assert logging.getLogger().level == logging.WARNING
