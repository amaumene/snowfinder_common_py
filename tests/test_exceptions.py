"""Tests for snowfinder_common.exceptions."""

import pytest

from snowfinder_common.exceptions import (
    AnalysisError,
    ConfigError,
    DatabaseError,
    FetchError,
    ParseError,
    SnowfinderError,
    ValidationError,
)


class TestSnowfinderErrorBase:
    def test_message_stored_as_str(self):
        exc = SnowfinderError("something went wrong")
        assert str(exc) == "something went wrong"

    def test_context_defaults_to_empty_dict(self):
        exc = SnowfinderError("oops")
        assert exc.context == {}

    def test_context_stored_when_provided(self):
        ctx = {"key": "value", "code": 42}
        exc = SnowfinderError("oops", context=ctx)
        assert exc.context == ctx

    def test_context_is_defensively_copied(self):
        ctx = {"key": "value"}
        exc = SnowfinderError("oops", context=ctx)

        ctx["key"] = "changed"
        ctx["extra"] = True

        assert exc.context == {"key": "value"}

    def test_repr_without_context(self):
        exc = SnowfinderError("bad thing")
        assert repr(exc) == "SnowfinderError('bad thing')"

    def test_repr_with_context(self):
        exc = SnowfinderError("bad thing", context={"x": 1})
        assert repr(exc) == "SnowfinderError('bad thing', context={'x': 1})"

    def test_is_exception_subclass(self):
        assert issubclass(SnowfinderError, Exception)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(SnowfinderError, match="test error"):
            raise SnowfinderError("test error")


class TestExceptionHierarchy:
    @pytest.mark.parametrize(
        "exc_class",
        [ConfigError, DatabaseError, FetchError, ParseError, AnalysisError, ValidationError],
    )
    def test_all_subclass_snowfinder_error(self, exc_class):
        assert issubclass(exc_class, SnowfinderError)

    @pytest.mark.parametrize(
        "exc_class",
        [ConfigError, DatabaseError, FetchError, ParseError, AnalysisError, ValidationError],
    )
    def test_all_subclass_exception(self, exc_class):
        assert issubclass(exc_class, Exception)

    @pytest.mark.parametrize(
        "exc_class",
        [ConfigError, DatabaseError, FetchError, ParseError, AnalysisError, ValidationError],
    )
    def test_can_be_caught_as_snowfinder_error(self, exc_class):
        with pytest.raises(SnowfinderError):
            raise exc_class("leaf error")

    @pytest.mark.parametrize(
        "exc_class",
        [ConfigError, DatabaseError, FetchError, ParseError, AnalysisError, ValidationError],
    )
    def test_context_propagates_through_subclass(self, exc_class):
        ctx = {"detail": "extra info"}
        exc = exc_class("msg", context=ctx)
        assert exc.context == ctx

    @pytest.mark.parametrize(
        "exc_class",
        [ConfigError, DatabaseError, FetchError, ParseError, AnalysisError, ValidationError],
    )
    def test_repr_shows_subclass_name(self, exc_class):
        exc = exc_class("boom")
        assert repr(exc).startswith(exc_class.__name__)


class TestSubclassDistinctness:
    def test_config_error_not_database_error(self):
        with pytest.raises(ConfigError):
            raise ConfigError("cfg")
        with pytest.raises(SnowfinderError):
            raise ConfigError("cfg")

    def test_database_error_not_fetch_error(self):
        exc = DatabaseError("db down")
        assert not isinstance(exc, FetchError)

    def test_fetch_error_not_parse_error(self):
        exc = FetchError("404")
        assert not isinstance(exc, ParseError)

    def test_analysis_error_not_validation_error(self):
        exc = AnalysisError("singular matrix")
        assert not isinstance(exc, ValidationError)
