# jaquette

[![PyPI](https://img.shields.io/pypi/v/jaquette)](https://pypi.org/project/jaquette/)
[![Python](https://img.shields.io/pypi/pyversions/jaquette)](https://pypi.org/project/jaquette/)
[![CI](https://github.com/mtouzot/jaquette/actions/workflows/ci.yml/badge.svg)](https://github.com/mtouzot/jaquette/actions)
[![License](https://img.shields.io/badge/license-PolyForm%20Noncommercial-blue)](https://github.com/mtouzot/jaquette/blob/HEAD/LICENSE)

Python client for the public [MyBluray](https://mybluray.fr/api) API (cover art and title search).

> **Non-commercial use only**, as required by MyBluray and by this project's license.
> This project is not affiliated with MyBluray or DVDFr.

- Synchronous (`Client`) and asynchronous (`AsyncClient`) clients with the same interface
- Typed responses ([pydantic](https://docs.pydantic.dev/)) and a typed package (`py.typed`)
- Search filters: media type, publisher, genre, release dates
- Automatic retries with `Retry-After` support and exponential backoff
- A clear exception hierarchy: one `except JaquetteException` catches everything
- A `jaquette` command-line tool

## Installation

```bash
pip install jaquette
# or
uv add jaquette
```

Python 3.11 or newer is required.

## Quick start

```python
from jaquette import Client

with Client() as client:
    # Cover art record by barcode (ISBN/EAN, as a string)
    product = client.get_product("3333290016961")
    print(product.title, product.media, product.editeur)

    # All editions of a title
    results = client.search("Breaking Bad")
    print(f"{len(results)} editions (truncated: {results.truncated})")
    for item in results:
        print(item.isbn, item.media, item.title)
```

The ISBN is a **string**: barcodes can start with zeros, which an integer would lose.
Use the client as a context manager so the connection is closed for you.

### Searching with filters

All filters are optional and keyword-only. `media`, `editeur` and `genre` accept a
string or a list of strings.

| Parameter | Type | Description |
|---|---|---|
| `media` | `str \| list[str]` | Media type, e.g. `"Blu-ray"`, `["DVD", "4K Ultra HD"]` |
| `editeur` | `str \| list[str]` | Publisher |
| `genre` | `str \| list[str]` | DVDFr genre |
| `parution_min` | `date \| "YYYY-MM-DD"` | Earliest release date |
| `parution_max` | `date \| "YYYY-MM-DD"` | Latest release date |

```python
results = client.search(
    "Alien",
    media=["Blu-ray", "4K Ultra HD"],
    parution_min="2015-01-01",
)
```

> Always check `results.truncated`: when it is `True`, not all DVDFr pages could be
> crawled and the list is incomplete.

### Saving the barcode image

`product.barcode` holds the PNG bytes of the EAN-13 barcode:

```python
from pathlib import Path

Path("barcode.png").write_bytes(product.barcode)
```

## Asynchronous client

`AsyncClient` has the same methods, as coroutines:

```python
import asyncio

from jaquette import AsyncClient


async def main() -> None:
    isbns = ["3333290016961", "3333290016962"]
    limit = asyncio.Semaphore(5)  # be polite: at most 5 requests at a time

    async with AsyncClient() as client:

        async def fetch(isbn: str):
            async with limit:
                return await client.get_product(isbn)

        # return_exceptions=True: one unknown barcode must not discard the others
        results = await asyncio.gather(*(fetch(i) for i in isbns), return_exceptions=True)

    for isbn, result in zip(isbns, results):
        print(isbn, result if isinstance(result, Exception) else result.title)


asyncio.run(main())
```

## Command line

```bash
jaquette product 3333290016961
jaquette search Breaking Bad
jaquette search Alien --media Blu-ray --media "4K Ultra HD" --from 2015-01-01
jaquette search Alien --json
```

| Option | Applies to | Description |
|---|---|---|
| `--json` | `product`, `search` | Print JSON instead of text (the barcode image is left out) |
| `--media`, `--editeur`, `--genre` | `search` | Filter; repeat the option to give several values |
| `--from`, `--to` | `search` | Release date bounds, `YYYY-MM-DD` |

The exit code is `0` on success and `1` on error (the message goes to stderr).

## Error handling

Every error raised by the library inherits from `JaquetteException`.

```
JaquetteException
├── InvalidISBNError         malformed ISBN (no request sent)
├── InvalidQueryError        query too short, or malformed date (no request sent)
├── NetworkError             connection failure or timeout, after retries
├── InvalidResponseError     the API response does not match the expected schema
└── APIError                 HTTP error (has .status_code, .message, .payload)
    ├── BadRequestError      400 / 422
    ├── NotFoundError        404
    ├── RateLimitError       429 (has .retry_after, in seconds)
    └── ServerError          5xx
```

```python
from jaquette import Client, JaquetteException, NotFoundError

with Client() as client:
    try:
        product = client.get_product("9999999999999")
    except NotFoundError as e:
        print(f"Unknown barcode: {e.message}")
    except JaquetteException as e:
        print(f"Request failed: {e}")
```

Put the most specific `except` first.

## Retries

Network errors, HTTP `429` and `502`/`503`/`504` are retried automatically, 2 times by
default. The client waits for the `Retry-After` header when the server sends one
(capped at 30 s), and otherwise waits 0.5 s, 1 s, 2 s... Other errors (404, 400...) are
never retried.

Use `Client(max_retries=0)` to disable retries.

## Design notes

- **One logic, two clients**: validation, error mapping, parsing and retry delays are plain
  functions shared by `Client` and `AsyncClient`; only the network call differs.
- **Offline tests**: the suite runs against `httpx.MockTransport`, never the real API.
- **Bring your own `httpx` client**: `Client(client=my_httpx_client)` for proxies or
  custom transports.

## Documentation

Full API reference: [**https://mtouzot.github.io/jaquette/**](https://mtouzot.github.io/jaquette/)

## Development

```bash
uv sync
uv run pytest
uv run prek run --all-files
uv run mkdocs serve        # documentation preview
```

## License

Released under the [PolyForm Noncommercial License 1.0.0](https://github.com/mtouzot/jaquette/blob/HEAD/LICENSE).
