"""Automatic retries: what is retried, how long we wait, when we give up."""

import httpx
import pytest

from jaquette import NetworkError, NotFoundError, RateLimitError, ServerError

from .helpers import PRODUCT, Script, reply


def test_a_503_is_retried_then_succeeds(make_client, sleeps):
    script = Script(reply(503, {"error": "DVDFr inaccessible"}), reply(200, PRODUCT))
    product = make_client(script).get_product("3333290016961")

    assert product.title
    assert len(script.requests) == 2
    assert sleeps == [0.5]


@pytest.mark.parametrize("status", [429, 502, 503, 504])
def test_every_transient_status_is_retried(make_client, sleeps, status):
    script = Script(reply(status, {"error": "later"}), reply(200, PRODUCT))
    make_client(script).get_product("3333290016961")
    assert len(script.requests) == 2


def test_the_wait_grows_between_attempts(make_client, sleeps):
    script = Script(
        reply(503, {"error": "x"}), reply(503, {"error": "x"}), reply(200, PRODUCT)
    )
    make_client(script, max_retries=2).get_product("3333290016961")
    assert sleeps == [0.5, 1.0]


def test_retry_after_is_honored(make_client, sleeps):
    script = Script(
        *[reply(429, {"error": "slow"}, headers={"Retry-After": "3"}) for _ in range(3)]
    )
    with pytest.raises(RateLimitError) as exc:
        make_client(script, max_retries=2).get_product("3333290016961")

    assert sleeps == [3.0, 3.0]
    assert exc.value.retry_after == 3.0
    assert exc.value.status_code == 429
    assert len(script.requests) == 3  # the call + 2 retries


def test_a_huge_retry_after_is_capped(make_client, sleeps):
    script = Script(
        reply(429, {"error": "slow"}, headers={"Retry-After": "3600"}),
        reply(200, PRODUCT),
    )
    make_client(script).get_product("3333290016961")
    assert sleeps == [30.0]


def test_a_429_without_retry_after_uses_backoff(make_client, sleeps):
    script = Script(reply(429, {"error": "slow"}), reply(200, PRODUCT))
    make_client(script).get_product("3333290016961")
    assert sleeps == [0.5]


def test_gives_up_after_max_retries(make_client, sleeps):
    script = Script(*[reply(503, {"error": "down"}) for _ in range(3)])
    with pytest.raises(ServerError) as exc:
        make_client(script).get_product("3333290016961")

    assert exc.value.status_code == 503
    assert len(script.requests) == 3  # default: 1 call + 2 retries
    assert len(sleeps) == 2  # no wait after the last attempt


def test_max_retries_zero_disables_retries(make_client, sleeps):
    script = Script(reply(503, {"error": "down"}))
    with pytest.raises(ServerError):
        make_client(script, max_retries=0).get_product("3333290016961")
    assert len(script.requests) == 1
    assert sleeps == []


@pytest.mark.parametrize("status", [400, 404, 422, 500])
def test_definitive_errors_are_never_retried(make_client, sleeps, status):
    script = Script(reply(status, {"error": "no"}))
    with pytest.raises(Exception):  # noqa: B017 - the type does not matter here
        make_client(script).get_product("3333290016961")
    assert len(script.requests) == 1
    assert sleeps == []


def test_a_network_error_is_retried_then_succeeds(make_client, sleeps):
    script = Script(httpx.ConnectError("boom"), reply(200, PRODUCT))
    assert make_client(script).get_product("3333290016961").title
    assert sleeps == [0.5]


def test_persistent_network_errors_become_network_error(make_client, sleeps):
    script = Script(*[httpx.ConnectError("boom") for _ in range(3)])
    with pytest.raises(NetworkError, match="boom") as exc:
        make_client(script).get_product("3333290016961")

    assert isinstance(exc.value.__cause__, httpx.ConnectError)
    assert len(script.requests) == 3
    assert sleeps == [0.5, 1.0]


def test_a_timeout_is_a_network_error(make_client, sleeps):
    script = Script(httpx.ReadTimeout("slow"))
    with pytest.raises(NetworkError):
        make_client(script, max_retries=0).get_product("3333290016961")


def test_retries_resend_the_same_request(make_client, sleeps):
    script = Script(
        reply(503, {"error": "x"}),
        reply(503, {"error": "x"}),
        reply(200, {"title": "x"}),
    )
    from jaquette import InvalidResponseError

    with pytest.raises(InvalidResponseError):  # the payload is incomplete, that is fine
        make_client(script).search("Alien", media="Blu-ray")
    urls = {str(r.url) for r in script.requests}
    assert len(urls) == 1  # same path and same query string on every attempt


def test_retries_also_apply_to_search(make_client, sleeps):
    script = Script(
        reply(503, {"error": "x"}),
        reply(200, {"query": "Alien", "total": 0, "dvdfr_total": 0}),
    )
    results = make_client(script).search("Alien")
    assert len(results) == 0
    assert len(script.requests) == 2


def test_not_found_is_not_retried_even_with_retries_left(make_client, sleeps):
    script = Script(reply(404, {"error": "unknown"}))
    with pytest.raises(NotFoundError):
        make_client(script, max_retries=5).get_product("3333290016961")
    assert len(script.requests) == 1
