import asyncio
import re
import time
from collections.abc import Mapping, Sequence
from datetime import date
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Self, TypeVar

import httpx
from pydantic import BaseModel

from .exceptions import (
    APIError,
    BadRequestError,
    InvalidISBNError,
    InvalidQueryError,
    InvalidResponseError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    ServerError,
)
from .models import ApiErrorBody, ProductResponse, SearchResponse

try:
    _VERSION = version("jaquette")
except PackageNotFoundError:  # package not installed (e.g. run from a checkout)
    _VERSION = "unknown"

DEFAULT_BASE_URL: str = "https://mybluray.fr"
"""Base URL of the public MyBluray API."""

DEFAULT_TIMEOUT: float = 15.0
"""Default request timeout, in seconds."""

DEFAULT_MAX_RETRIES: int = 2
"""Default number of retries on transient errors (429, 502, 503, 504)."""

_USER_AGENT: str = f"jaquette/{_VERSION} (non-commercial use)"
_HEADERS: dict[str, str] = {"Accept": "application/json", "User-Agent": _USER_AGENT}
_PRODUCT_PATH: str = "/api/product/{isbn}"
_SEARCH_PATH: str = "/api/search/"  # the title is sent as the ?q= query parameter, no longer in the path
_MIN_QUERY_LENGTH: int = 2
_ISBN_REGEX: re.Pattern = re.compile(
    r"^\d{8,14}$", re.ASCII
)  # 8 to 14 digits, no hyphens or spaces
_RETRY_STATUSES: frozenset[int] = frozenset({429, 502, 503, 504})
_MAX_DELAY: float = 30.0  # upper bound for any wait between two attempts, in seconds

T = TypeVar("T", bound=BaseModel)


def _validate_isbn(value: str) -> str:
    """Validate an ISBN/EAN: 8 to 14 digits, as required by the API."""
    if not isinstance(value, str):
        raise InvalidISBNError(
            f"ISBN must be a string (leading zeros matter), got {type(value).__name__}"
        )
    if not _ISBN_REGEX.fullmatch(value):
        raise InvalidISBNError(f"Invalid ISBN: {value!r}")
    return value


def _validate_query(value: str) -> str:
    """Strip a search query and check it is long enough for the API."""
    if not isinstance(value, str):
        raise InvalidQueryError(f"Query must be a string, got {type(value).__name__}")
    value = value.strip()
    if len(value) < _MIN_QUERY_LENGTH:
        raise InvalidQueryError(
            f"The search query must be at least {_MIN_QUERY_LENGTH} characters."
        )
    return value


def _parse_retry_after(value: str | None) -> float | None:
    """Read a Retry-After header given in seconds (HTTP dates are ignored)."""
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def _backoff(attempt: int) -> float:
    """Exponential wait: 0.5 s, 1 s, 2 s, 4 s... capped."""
    return min(_MAX_DELAY, 0.5 * 2**attempt)


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    """Wait before retrying: honor Retry-After when present, else back off."""
    retry_after = _parse_retry_after(response.headers.get("Retry-After"))
    if retry_after is None:
        return _backoff(attempt)
    return min(_MAX_DELAY, retry_after)


def _error_details(response: httpx.Response) -> tuple[str, object]:
    """Extract (message, payload) from an error response."""
    try:
        payload = response.json()
    except ValueError:  # body is not JSON
        return response.text, response.text
    try:
        return ApiErrorBody.model_validate(payload).error, payload
    except ValueError:  # JSON without an "error" field
        return response.text, payload


def _raise_for_status(response: httpx.Response) -> None:
    """Convert an HTTP error response into the matching exception."""
    if response.is_success:
        return
    message, payload = _error_details(response)
    code = response.status_code
    if code in (400, 422):
        raise BadRequestError(code, message, payload)
    if code == 404:
        raise NotFoundError(code, message, payload)
    if code == 429:
        retry_after = _parse_retry_after(response.headers.get("Retry-After"))
        raise RateLimitError(code, message, payload, retry_after=retry_after)
    if code >= 500:
        raise ServerError(code, message, payload)
    raise APIError(code, message, payload)


def _parse(model: type[T], response: httpx.Response) -> T:
    """Validate a successful response body against a model."""
    try:
        return model.model_validate(response.json())
    except ValueError as e:  # body is not JSON, or does not match the schema
        raise InvalidResponseError(str(e)) from e


def _format_date(name: str, value: date | str) -> str:
    """Return a date as YYYY-MM-DD, the format the API expects."""
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise InvalidQueryError(
            f"{name} must be a date or a YYYY-MM-DD string, got {value!r}"
        ) from None


def _search_params(
    query: str,
    *,
    media: str | Sequence[str] | None = None,
    editeur: str | Sequence[str] | None = None,
    genre: str | Sequence[str] | None = None,
    parution_min: date | str | None = None,
    parution_max: date | str | None = None,
) -> dict[str, Any]:
    """Build the query string of /api/search, skipping unset filters."""
    params: dict[str, Any] = {"q": _validate_query(query)}
    for name, value in (("media", media), ("editeur", editeur), ("genre", genre)):
        if value is not None:
            # A bare string is one value, not a sequence of characters.
            params[name] = [value] if isinstance(value, str) else list(value)
    if parution_min is not None:
        params["parution_min"] = _format_date("parution_min", parution_min)
    if parution_max is not None:
        params["parution_max"] = _format_date("parution_max", parution_max)
    return params


def _sleep(delay: float) -> None:
    """Sleep synchronously for the given delay."""
    time.sleep(delay)


async def _async_sleep(delay: float) -> None:
    """Sleep asynchronously for the given delay."""
    await asyncio.sleep(delay)


class Client:
    """Synchronous client for the public MyBluray API.

    Use it as a context manager so the connection is always closed.

    Network errors, HTTP 429 and HTTP 502/503/504 are retried automatically
    (see `max_retries`). Any other failure raises a subclass of
    [`JaquetteException`][jaquette.exceptions.JaquetteException].

    Args:
        base_url: Root URL of the API. Defaults to
            [`DEFAULT_BASE_URL`][jaquette.clients.DEFAULT_BASE_URL].
        timeout: Timeout in seconds, applied separately to connecting, writing,
            reading and acquiring a connection (not to the whole request).
            Defaults to [`DEFAULT_TIMEOUT`][jaquette.clients.DEFAULT_TIMEOUT].
        max_retries: Extra attempts after a network error, a 429 or a
            502/503/504. Use `0` to disable retries; otherwise one call sends
            at most `max_retries + 1` requests. Waits honor the `Retry-After`
            header when present (capped at 30 s), otherwise they grow
            exponentially. Defaults to
            [`DEFAULT_MAX_RETRIES`][jaquette.clients.DEFAULT_MAX_RETRIES].
        client: An existing `httpx.Client` to use instead of creating one.
            In that case `base_url`, `timeout` and the default headers are
            ignored (your client defines them), and closing it is up to you.

    Raises:
        ValueError: If `max_retries` is negative.

    Examples:
        ```pycon
        >>> with Client() as client:
        ...     product = client.get_product("3333290016961")
        ...     results = client.search("Breaking Bad")
        ```
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        client: httpx.Client | None = None,
    ):
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        self._max_retries = max_retries
        self._owns_client = client is None
        self._http = client or httpx.Client(
            base_url=base_url,
            timeout=timeout,
            headers=_HEADERS,
            follow_redirects=True,
        )

    def get_product(self, isbn: str) -> ProductResponse:
        """Fetch a cover art record by its ISBN/EAN.

        Args:
            isbn: The barcode, as a string of 8 to 14 digits without hyphens or
                spaces. Pass a string, not an integer: leading zeros are significant.

        Returns:
            The full record: title, release year, publisher, media type, price,
            cast, genres, cover image URL, the DVDFr page and the barcode image
            (``barcode``, as PNG bytes).

        Raises:
            InvalidISBNError: The ISBN is malformed (no request is sent).
            NotFoundError: No product matches this barcode (HTTP 404).
            BadRequestError: The API rejected the request (HTTP 400 or 422).
            RateLimitError: Too many requests, after retries (see ``retry_after``).
            ServerError: The API failed (HTTP 5xx), after retries.
            APIError: Any other HTTP error (parent of the four errors above).
            NetworkError: The request could not be completed, after retries.
            InvalidResponseError: The response does not match the expected schema.

        Example:
            ```pycon
            >>> product = client.get_product("3333290016961")
            >>> product.title
            'Breaking Bad - Intégrale de la série + El Camino : un film "Breaking Bad"'
            ```
        """
        response = self._request(_PRODUCT_PATH.format(isbn=_validate_isbn(isbn)))
        _raise_for_status(response)
        return _parse(ProductResponse, response)

    def search(
        self,
        query: str,
        *,
        media: str | Sequence[str] | None = None,
        editeur: str | Sequence[str] | None = None,
        genre: str | Sequence[str] | None = None,
        parution_min: date | str | None = None,
        parution_max: date | str | None = None,
    ) -> SearchResponse:
        """Fetch the editions available for a movie or TV series title.

        The result can be iterated directly (``for item in results``). Always check
        ``truncated`` before treating the list as complete.

        Args:
            query: The title to search for, at least 2 characters.
            media: Keep only these media types, for example ``["Blu-ray", "4K Ultra HD"]``.
                A single string is accepted too. Values are matched by DVDFr.
            editeur: Keep only these publishers.
            genre: Keep only these DVDFr genres.
            parution_min: Earliest release date of the edition (a ``date`` or a
                ``"YYYY-MM-DD"`` string).
            parution_max: Latest release date of the edition (same format).

        Returns:
            A ``SearchResponse`` with ``results`` (one ``SearchItem`` per edition:
            DVD, Blu-ray, 4K...), ``total`` (editions returned, other editions
            included), ``dvdfr_total`` (products announced by DVDFr) and
            ``truncated`` (``True`` if not all DVDFr pages could be crawled, so the
            list is incomplete).

        Raises:
            InvalidQueryError: The query is too short or not a string, or a date is
                malformed (no request is sent).
            BadRequestError: The API rejected the query, for example when it is
                too short (HTTP 400).
            RateLimitError: Too many requests, after retries (see ``retry_after``).
            ServerError: The API or DVDFr failed (HTTP 5xx), after retries.
            NetworkError: The request could not be completed, after retries.
            InvalidResponseError: The response does not match the expected schema.

        Example:
            ```pycon
            >>> results = client.search("Alien", media="Blu-ray", parution_min="2015-01-01")
            >>> for item in results:
            ...     print(item.isbn, item.media, item.title)
            ```
        """
        params = _search_params(
            query,
            media=media,
            editeur=editeur,
            genre=genre,
            parution_min=parution_min,
            parution_max=parution_max,
        )
        response = self._request(_SEARCH_PATH, params=params)
        _raise_for_status(response)
        return _parse(SearchResponse, response)

    def _request(
        self, path: str, params: Mapping[str, Any] | None = None
    ) -> httpx.Response:
        """GET a path, retrying network errors and transient statuses."""
        attempt = 0
        while True:
            try:
                response = self._http.get(path, params=params)
            except httpx.TransportError as e:
                # Connection failure, timeout, DNS error...
                if attempt >= self._max_retries:
                    raise NetworkError(str(e) or type(e).__name__) from e
                delay = _backoff(attempt)
            else:
                # Success, definitive error or no retries left: return it as is.
                if (
                    response.status_code not in _RETRY_STATUSES
                    or attempt >= self._max_retries
                ):
                    return response
                delay = _retry_delay(response, attempt)
            _sleep(delay)
            attempt += 1

    def close(self) -> None:
        """Close the underlying connection.

        Does nothing if you passed your own ``httpx.Client`` with ``client=``:
        closing it is then up to you. Prefer the context manager, which calls
        this method for you::

        ```pycon
        >>> with Client() as client:
                ...
        ```
        """
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(base_url={str(self._http.base_url)!r})"


class AsyncClient:
    """Asynchronous client for the public MyBluray API.

    Same interface as [`Client`][jaquette.clients.Client], but every method that
    talks to the API is a coroutine. Use it as an async context manager so the
    connection is always closed.

    Network errors, HTTP 429 and HTTP 502/503/504 are retried automatically
    (see `max_retries`). Any other failure raises a subclass of
    [`JaquetteException`][jaquette.exceptions.JaquetteException].

    Args:
        base_url: Root URL of the API. Defaults to
            [`DEFAULT_BASE_URL`][jaquette.clients.DEFAULT_BASE_URL].
        timeout: Timeout in seconds, applied separately to connecting, writing,
            reading and acquiring a connection (not to the whole request).
            Defaults to [`DEFAULT_TIMEOUT`][jaquette.clients.DEFAULT_TIMEOUT].
        max_retries: Extra attempts after a network error, a 429 or a
            502/503/504. Use `0` to disable retries; otherwise one call sends
            at most `max_retries + 1` requests. Waits honor the `Retry-After`
            header when present (capped at 30 s), otherwise they grow
            exponentially. Defaults to
            [`DEFAULT_MAX_RETRIES`][jaquette.clients.DEFAULT_MAX_RETRIES].
        client: An existing `httpx.AsyncClient` to use instead of creating one.
            In that case `base_url`, `timeout` and the default headers are
            ignored (your client defines them), and closing it is up to you.

    Raises:
        ValueError: If `max_retries` is negative.

    Examples:
        ```pycon
        >>> async with AsyncClient() as client:
        ...     product = await client.get_product("3333290016961")
        ...     results = await client.search("Breaking Bad")
        ```
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        client: httpx.AsyncClient | None = None,
    ):
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        self._max_retries = max_retries
        self._owns_client = client is None
        self._http = client or httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers=_HEADERS,
            follow_redirects=True,
        )

    async def get_product(self, isbn: str) -> ProductResponse:
        """Fetch a cover art record by its ISBN/EAN.

        Args:
            isbn: The barcode, as a string of 8 to 14 digits without hyphens or
                spaces. Pass a string, not an integer: leading zeros are significant.

        Returns:
            The full record: title, release year, publisher, media type, price,
            cast, genres, cover image URL, the DVDFr page and the barcode image
            (``barcode``, as PNG bytes).

        Raises:
            InvalidISBNError: The ISBN is malformed (no request is sent).
            NotFoundError: No product matches this barcode (HTTP 404).
            BadRequestError: The API rejected the request (HTTP 400 or 422).
            RateLimitError: Too many requests, after retries (see ``retry_after``).
            ServerError: The API failed (HTTP 5xx), after retries.
            APIError: Any other HTTP error (parent of the four errors above).
            NetworkError: The request could not be completed, after retries.
            InvalidResponseError: The response does not match the expected schema.

        Example:
            ```pycon
            >>> product = await client.get_product("3333290016961")
            >>> print(product.title)
            ```
        """
        response = await self._request(_PRODUCT_PATH.format(isbn=_validate_isbn(isbn)))
        _raise_for_status(response)
        return _parse(ProductResponse, response)

    async def search(
        self,
        query: str,
        *,
        media: str | Sequence[str] | None = None,
        editeur: str | Sequence[str] | None = None,
        genre: str | Sequence[str] | None = None,
        parution_min: date | str | None = None,
        parution_max: date | str | None = None,
    ) -> SearchResponse:
        """Fetch the editions available for a movie or TV series title.

        The result can be iterated directly (``for item in results``). Always check
        ``truncated`` before treating the list as complete.

        Args:
            query: The title to search for, at least 2 characters.
            media: Keep only these media types, for example
                ``["Blu-ray", "4K Ultra HD"]``. A single string is accepted too.
            editeur: Keep only these publishers.
            genre: Keep only these DVDFr genres.
            parution_min: Earliest release date of the edition (a ``date`` or a
                ``"YYYY-MM-DD"`` string).
            parution_max: Latest release date of the edition (same format).

        Returns:
            A ``SearchResponse`` with ``results`` (one ``SearchItem`` per edition:
            DVD, Blu-ray, 4K...), ``total`` (editions returned, other editions
            included), ``dvdfr_total`` (products announced by DVDFr) and
            ``truncated`` (``True`` if not all DVDFr pages could be crawled, so
            the list is incomplete).

        Raises:
            InvalidQueryError: The query is too short or not a string, or a date is
                malformed (no request is sent).
            BadRequestError: The API rejected the request (HTTP 400).
            RateLimitError: Too many requests, after retries (see ``retry_after``).
            ServerError: The API or DVDFr failed (HTTP 5xx), after retries.
            NetworkError: The request could not be completed, after retries.
            InvalidResponseError: The response does not match the expected schema.

        Example:
            ```pycon
            >>> results = await client.search("Alien", media="Blu-ray", parution_min="2015-01-01")
            >>> for item in results:
            ...     print(item.isbn, item.media, item.title)
            ```
        """
        params = _search_params(
            query,
            media=media,
            editeur=editeur,
            genre=genre,
            parution_min=parution_min,
            parution_max=parution_max,
        )
        response = await self._request(_SEARCH_PATH, params=params)
        _raise_for_status(response)
        return _parse(SearchResponse, response)

    async def _request(
        self, path: str, params: Mapping[str, Any] | None = None
    ) -> httpx.Response:
        """GET a path, retrying network errors and transient statuses."""
        attempt = 0
        while True:
            try:
                response = await self._http.get(path, params=params)
            except httpx.TransportError as e:
                # Connection failure, timeout, DNS error...
                if attempt >= self._max_retries:
                    raise NetworkError(str(e) or type(e).__name__) from e
                delay = _backoff(attempt)
            else:
                # Success, definitive error or no retries left: return it as is.
                if (
                    response.status_code not in _RETRY_STATUSES
                    or attempt >= self._max_retries
                ):
                    return response
                delay = _retry_delay(response, attempt)
            await _async_sleep(delay)
            attempt += 1

    async def aclose(self) -> None:
        """Close the underlying connection.

        Does nothing if you passed your own ``httpx.AsyncClient`` with
        ``client=``: closing it is then up to you. Prefer the async context
        manager, which calls this method for you::
            ```pycon
            >>> async with AsyncClient() as client:
                 ...
            ```
        """
        if self._owns_client:
            await self._http.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(base_url={str(self._http.base_url)!r})"
