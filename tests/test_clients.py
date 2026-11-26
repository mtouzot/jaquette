from unittest.mock import AsyncMock, Mock

import pytest

from jaquette import clients


def test_sleep(monkeypatch):
    mock_sleep = Mock()
    monkeypatch.setattr(clients.time, "sleep", mock_sleep)

    clients._sleep(0.5)

    mock_sleep.assert_called_once_with(0.5)


@pytest.mark.asyncio
async def test_async_sleep(monkeypatch):
    mock_sleep = AsyncMock()
    monkeypatch.setattr(clients.asyncio, "sleep", mock_sleep)

    await clients._async_sleep(0.5)

    mock_sleep.assert_awaited_once_with(0.5)
