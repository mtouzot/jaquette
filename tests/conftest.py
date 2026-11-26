import httpx
import pytest

from jaquette import AsyncClient, Client


@pytest.fixture
def make_client():
    """Build a Client wired to a fake server."""

    def _make(script, **kwargs) -> Client:
        http = httpx.Client(
            base_url="https://test", transport=httpx.MockTransport(script)
        )
        return Client(client=http, **kwargs)

    return _make


@pytest.fixture
def make_async_client():
    """Build an AsyncClient wired to a fake server."""

    def _make(script, **kwargs) -> AsyncClient:
        http = httpx.AsyncClient(
            base_url="https://test", transport=httpx.MockTransport(script)
        )
        return AsyncClient(client=http, **kwargs)

    return _make


@pytest.fixture
def sleeps(monkeypatch) -> list[float]:
    """Skip real waiting. Returns the list of delays the client asked for."""
    delays: list[float] = []

    async def fake_async_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("jaquette.clients._sleep", delays.append)
    monkeypatch.setattr("jaquette.clients._async_sleep", fake_async_sleep)
    return delays
