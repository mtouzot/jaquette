"""Real MyBluray API. Excluded by default: run with `pytest -m network`.

These tests are the only ones that notice when the API changes shape (a renamed
field, a new required one). Keep them few: the service is free and shared.
"""

import pytest

from jaquette import Client, NotFoundError


@pytest.fixture(scope="module")
def client():
    with Client() as c:
        yield c


def test_a_known_product_matches_the_strict_model(client):
    product = client.get_product("3333290016961")
    assert product.isbn == 3333290016961
    assert product.title
    assert product.barcode.startswith(b"\x89PNG")


def test_search_matches_the_strict_model(client):
    results = client.search("Breaking Bad")
    assert len(results) > 0
    assert all(item.isbn.isdigit() for item in results)


def test_media_filter_only_returns_that_media(client):
    results = client.search("Breaking Bad", media="Blu-ray")
    assert {item.media for item in results} <= {"Blu-ray"}


def test_an_unknown_barcode_is_not_found(client):
    with pytest.raises(NotFoundError):
        client.get_product("9999999999999")
