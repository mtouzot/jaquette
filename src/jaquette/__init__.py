from importlib.metadata import PackageNotFoundError, version

from .cli import main
from .clients import AsyncClient, Client
from .exceptions import (
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
from .models import ProductResponse, SearchItem, SearchResponse

try:
    __version__ = version("jaquette")
except PackageNotFoundError:
    __version__ = "unknown"

__all__ = [
    "APIError",
    "AsyncClient",
    "BadRequestError",
    "Client",
    "InvalidISBNError",
    "InvalidQueryError",
    "InvalidResponseError",
    "JaquetteException",
    "NetworkError",
    "NotFoundError",
    "ProductResponse",
    "RateLimitError",
    "SearchItem",
    "SearchResponse",
    "ServerError",
    "__version__",
    "main",
]
