class JaquetteException(Exception):
    """Base class for all Jaquette exceptions."""


class InvalidISBNError(JaquetteException, ValueError):
    """The provided ISBN does not have a valid format."""


class InvalidQueryError(JaquetteException, ValueError):
    """The provided search query is empty or not a string."""


class NetworkError(JaquetteException):
    """The request could not be completed (connection failure, timeout, DNS...)."""


class InvalidResponseError(JaquetteException):
    """The API returned a payload that does not match the expected schema."""


class APIError(JaquetteException):
    """Error from the API."""

    def __init__(self, status_code: int, message: str = "", payload=None):
        super().__init__(
            f"HTTP {status_code}: {message}" if message else f"HTTP {status_code}"
        )
        self.status_code = status_code
        self.message = message
        self.payload = payload


class NotFoundError(APIError):
    """404: product not found."""


class BadRequestError(APIError):
    """400/422: parameters rejected by the API."""


class RateLimitError(APIError):
    """429: too many requests."""

    def __init__(
        self,
        status_code: int,
        message: str = "",
        payload=None,
        retry_after: float | None = None,
    ):
        super().__init__(status_code, message, payload)
        self.retry_after = retry_after


class ServerError(APIError):
    """5xx: server-side error."""
