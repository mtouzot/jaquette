"""Same behaviour as Client, through AsyncClient (pytest-asyncio, auto mode)."""

import asyncio

import httpx
import pytest

from jaquette import (
    AsyncClient,
    InvalidISBNError,
    InvalidQueryError,
    NetworkError,
    NotFoundError,
    RateLimitError,
)

from .helpers import PNG_SIGNATURE, PRODUCT, SEARCH_ITEM, Script, reply, search_payload


async def test_get_product(make_async_client):
    script = Script(reply(200, PRODUCT))
    product = await make_async_client(script).get_product("3333290016961")

    assert script.requests[0].url.path == "/api/product/3333290016961"
    assert product.isbn == 3333290016961
    assert product.barcode.startswith(PNG_SIGNATURE)


async def test_search_sends_filters(make_async_client):
    script = Script(reply(200, search_payload(SEARCH_ITEM)))
    results = await make_async_client(script).search(
        "Alien", media=["DVD", "Blu-ray"], parution_min="2015-01-01"
    )
    params = script.requests[0].url.params
    assert params["q"] == "Alien"
    assert params.get_list("media") == ["DVD", "Blu-ray"]
    assert params["parution_min"] == "2015-01-01"
    assert len(results) == 1


async def test_validation_sends_nothing(make_async_client):
    script = Script()
    client = make_async_client(script)
    with pytest.raises(InvalidISBNError):
        await client.get_product("abc")
    with pytest.raises(InvalidQueryError):
        await client.search("a")
    assert script.requests == []


async def test_404_becomes_not_found(make_async_client):
    script = Script(reply(404, {"error": "Aucun résultat"}))
    with pytest.raises(NotFoundError) as exc:
        await make_async_client(script).get_product("9999999999999")
    assert exc.value.message == "Aucun résultat"
    assert len(script.requests) == 1


async def test_retry_then_success_uses_the_async_sleep(make_async_client, sleeps):
    script = Script(reply(503, {"error": "down"}), reply(200, PRODUCT))
    product = await make_async_client(script).get_product("3333290016961")
    assert product.title
    assert sleeps == [0.5]


async def test_retry_after_is_honored(make_async_client, sleeps):
    script = Script(
        *[reply(429, {"error": "slow"}, headers={"Retry-After": "2"}) for _ in range(3)]
    )
    with pytest.raises(RateLimitError) as exc:
        await make_async_client(script).get_product("3333290016961")
    assert sleeps == [2.0, 2.0]
    assert exc.value.retry_after == 2.0


async def test_network_errors_become_network_error(make_async_client, sleeps):
    script = Script(*[httpx.ConnectError("boom") for _ in range(3)])
    with pytest.raises(NetworkError):
        await make_async_client(script).get_product("3333290016961")
    assert len(script.requests) == 3


async def test_concurrent_requests(make_async_client):
    script = Script(*[reply(200, PRODUCT) for _ in range(5)])
    client = make_async_client(script)
    products = await asyncio.gather(
        *(client.get_product("3333290016961") for _ in range(5))
    )
    assert len(products) == 5
    assert len(script.requests) == 5


async def test_gather_with_return_exceptions_keeps_the_other_results(make_async_client):
    script = Script(
        reply(200, PRODUCT), reply(404, {"error": "unknown"}), reply(200, PRODUCT)
    )
    client = make_async_client(script)
    results = await asyncio.gather(
        *(client.get_product("3333290016961") for _ in range(3)), return_exceptions=True
    )
    assert sum(isinstance(r, NotFoundError) for r in results) == 1
    assert sum(not isinstance(r, Exception) for r in results) == 2


class TestLifecycle:
    async def test_default_http_client_is_configured(self):
        client = AsyncClient()
        try:
            assert str(client._http.base_url).startswith("https://mybluray.fr")
            assert client._http.headers["user-agent"].startswith("jaquette/")
        finally:
            await client.aclose()

    async def test_aclose_closes_a_client_it_created(self):
        client = AsyncClient()
        await client.aclose()
        assert client._http.is_closed

    async def test_aclose_leaves_a_client_you_passed_open(self):
        http = httpx.AsyncClient(transport=httpx.MockTransport(Script()))
        await AsyncClient(client=http).aclose()
        assert not http.is_closed
        await http.aclose()

    async def test_async_context_manager(self):
        async with AsyncClient() as client:
            assert not client._http.is_closed
        assert client._http.is_closed

    async def test_errors_propagate_out_of_the_block(self):
        with pytest.raises(RuntimeError, match="boom"):
            async with AsyncClient():
                raise RuntimeError("boom")

    def test_negative_max_retries_is_rejected(self):
        with pytest.raises(ValueError, match="max_retries"):
            AsyncClient(max_retries=-1)

    async def test_repr(self):
        async with AsyncClient() as client:
            assert repr(client) == "AsyncClient(base_url='https://mybluray.fr')"
