"""The exception hierarchy is part of the public API."""

import pytest

import jaquette
from jaquette import (
    APIError,
    BadRequestError,
    InvalidISBNError,
    InvalidQueryError,
    InvalidResponseError,
    JaquetteException,
    NetworkError,
    NotFoundError,
    RateLimitError,
    ServerError,
)


@pytest.mark.parametrize(
    "error",
    [
        InvalidISBNError,
        InvalidQueryError,
        NetworkError,
        InvalidResponseError,
        APIError,
        BadRequestError,
        NotFoundError,
        RateLimitError,
        ServerError,
    ],
)
def test_everything_inherits_from_the_base_exception(error):
    assert issubclass(error, JaquetteException)


@pytest.mark.parametrize(
    "error", [BadRequestError, NotFoundError, RateLimitError, ServerError]
)
def test_http_errors_share_api_error(error):
    assert issubclass(error, APIError)


@pytest.mark.parametrize("error", [InvalidISBNError, InvalidQueryError])
def test_input_errors_are_also_value_errors(error):
    assert issubclass(error, ValueError)


def test_api_error_exposes_its_details():
    error = APIError(418, "teapot", payload={"error": "teapot"})
    assert (error.status_code, error.message, error.payload) == (
        418,
        "teapot",
        {"error": "teapot"},
    )
    assert str(error) == "HTTP 418: teapot"


def test_api_error_without_a_message():
    assert str(APIError(500)) == "HTTP 500"


def test_rate_limit_error_carries_retry_after():
    assert RateLimitError(429, "slow", retry_after=4.0).retry_after == 4.0
    assert RateLimitError(429).retry_after is None


def test_input_errors_are_not_api_errors():
    assert not issubclass(InvalidISBNError, APIError)


def test_the_public_api_is_importable():
    for name in jaquette.__all__:
        assert hasattr(jaquette, name), name
