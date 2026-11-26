"""Shared test data and a scripted fake server (no real network)."""

from __future__ import annotations

from typing import Any

import httpx

# PNG signature, base64-encoded: what the API sends in `barcode`.
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_BASE64 = "iVBORw0KGgo="

PRODUCT: dict[str, Any] = {
    "title": "Breaking Bad - Intégrale de la série + El Camino",
    "title_vo": "Breaking Bad + El Camino: A Breaking Bad Movie",
    "annee": "2008",
    "description": "Walter White, 50 ans, est professeur de chimie...",
    "image": "https://images.example/cover.jpg",
    "categorie": "Série",
    "duree": "3070 mn",
    "sortie": "5 Octobre 2022",
    "isbn": 3333290016961,
    "barcode": PNG_BASE64,
    "editeur": "Sony Pictures",
    "distributeur": "ESCD",
    "collection": "Metropolitan Edition Haute Définition",
    "media": "Blu-ray",
    "edition": "Metropolitan Edition Haute Définition",
    "acteurs": ["Bryan Cranston", "Aaron Paul"],
    "producteurs": ["Vince Gilligan"],
    "prix": "49.91 €",
    "date_sortie": "20/01/2008",
    "date_parution": "05/10/2022",
    "genres": ["Drame"],
    "source": "https://www.dvdfr.com/dvd/3333290016961-breaking-bad/",
}

SEARCH_ITEM: dict[str, Any] = {
    "isbn": "3333290016961",
    "title": "Breaking Bad - Intégrale de la série",
    "annee": "2008",
    "image": "https://images.example/cover.jpg",
    "editeur": "Sony Pictures",
    "media": "Blu-ray",
    "prix": "49.91 €",
    "date_parution": "5 Octobre 2022",
    "description": "Walter White...",
    "genres": ["Drame"],
    "url": "https://www.dvdfr.com/dvd/3333290016961-breaking-bad/",
    "source": "https://www.dvdfr.com/dvd/3333290016961-breaking-bad/",
}


def search_payload(*items: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "query": "Breaking Bad",
        "total": len(items),
        "dvdfr_total": len(items),
        "truncated": False,
        "results": list(items),
    }
    return {**payload, **overrides}


def reply(status: int, body: Any = None, **kwargs: Any) -> httpx.Response:
    """Build a fresh response (never reuse one object across requests)."""
    if body is None:
        return httpx.Response(status, **kwargs)
    return httpx.Response(status, json=body, **kwargs)


class Script:
    """Fake server: plays the given replies in order and records every request.

    An item can be a ``httpx.Response`` or an exception to raise (to simulate
    a network failure). Asking for more requests than scripted fails loudly.
    """

    def __init__(self, *replies: httpx.Response | Exception) -> None:
        self.replies = list(replies)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self.replies:
            raise AssertionError(
                f"Unexpected request #{len(self.requests)}: {request.url}"
            )
        item = self.replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
