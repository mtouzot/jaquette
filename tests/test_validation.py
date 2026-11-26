"""Pure functions: no client, no network."""

from datetime import date
from typing import Any

import httpx
import pytest

from jaquette.clients import (
    _backoff,
    _parse_retry_after,
    _retry_delay,
    _search_params,
    _validate_isbn,
    _validate_query,
)
from jaquette.exceptions import InvalidISBNError, InvalidQueryError


class TestValidateIsbn:
    @pytest.mark.parametrize("value", ["3333290016961", "00000000", "12345678901234"])
    def test_accepts_8_to_14_digits(self, value):
        assert _validate_isbn(value) == value

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "abc",
            "1234567",  # too short
            "123456789012345",  # too long
            "1234-5678-90",  # hyphens
            " 12345678",  # space
            "12345678\n",  # trailing newline
            "١٢٣٤٥٦٧٨",  # Arabic-Indic digits: \d would match without re.ASCII
            "9780306406157X",  # ISBN-10 style check digit is not accepted
        ],
    )
    def test_rejects_invalid_strings(self, value):
        with pytest.raises(InvalidISBNError):
            _validate_isbn(value)

    @pytest.mark.parametrize("value", [3333290016961, None, 1.5, b"12345678"])
    def test_rejects_non_strings(self, value):
        with pytest.raises(InvalidISBNError, match="string"):
            _validate_isbn(value)  # type: ignore[arg-type]

    def test_error_is_also_a_value_error(self):
        with pytest.raises(ValueError):
            _validate_isbn("abc")


class TestValidateQuery:
    def test_strips_whitespace(self):
        assert _validate_query("  Alien  ") == "Alien"

    def test_two_characters_is_the_minimum(self):
        assert _validate_query("AB") == "AB"

    @pytest.mark.parametrize("value", ["", "   ", "a", " a "])
    def test_rejects_too_short(self, value):
        with pytest.raises(InvalidQueryError, match="at least 2"):
            _validate_query(value)

    def test_validate_query_invalid_type(self) -> None:
        value: Any = 42

        with pytest.raises(InvalidQueryError, match="string"):
            _validate_query(value)


class TestSearchParams:
    def test_only_query_by_default(self):
        assert _search_params("Alien") == {"q": "Alien"}

    def test_a_single_string_is_one_value_not_characters(self):
        assert _search_params("Alien", media="Blu-ray")["media"] == ["Blu-ray"]

    def test_sequences_become_lists(self):
        params = _search_params("Alien", genre=("Horreur", "SF"))
        assert params["genre"] == ["Horreur", "SF"]

    def test_dates_are_formatted_as_iso(self):
        params = _search_params(
            "Alien", parution_min=date(2015, 1, 5), parution_max="2020-12-31"
        )
        assert params["parution_min"] == "2015-01-05"
        assert params["parution_max"] == "2020-12-31"

    @pytest.mark.parametrize("bad", ["05/01/2015", "yesterday", ""])
    def test_malformed_dates_are_rejected(self, bad):
        with pytest.raises(InvalidQueryError, match="parution_min"):
            _search_params("Alien", parution_min=bad)

    def test_unset_filters_are_left_out(self):
        params = _search_params("Alien", media=None, editeur=None)
        assert set(params) == {"q"}

    def test_the_title_is_validated_too(self):
        with pytest.raises(InvalidQueryError):
            _search_params("a")


class TestRetryTiming:
    @pytest.mark.parametrize(
        ("attempt", "expected"), [(0, 0.5), (1, 1.0), (2, 2.0), (3, 4.0), (10, 30.0)]
    )
    def test_backoff_grows_then_is_capped(self, attempt, expected):
        assert _backoff(attempt) == expected

    @pytest.mark.parametrize(
        ("header", "expected"),
        [
            ("3", 3.0),
            ("0", 0.0),
            ("1.5", 1.5),
            ("-5", 0.0),  # never a negative wait
            (None, None),
            ("abc", None),
            ("Wed, 21 Oct 2015 07:28:00 GMT", None),  # HTTP dates are ignored
        ],
    )
    def test_parse_retry_after(self, header, expected):
        assert _parse_retry_after(header) == expected

    def test_retry_after_header_wins_over_backoff(self):
        response = httpx.Response(429, headers={"Retry-After": "7"})
        assert _retry_delay(response, attempt=0) == 7.0

    def test_retry_after_is_capped(self):
        response = httpx.Response(429, headers={"Retry-After": "120"})
        assert _retry_delay(response, attempt=0) == 30.0

    def test_without_header_it_falls_back_to_backoff(self):
        assert _retry_delay(httpx.Response(503), attempt=2) == 2.0
