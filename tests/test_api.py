import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_health_check():
    with patch("ai.providers.ollama.OllamaProvider.health_check", new_callable=AsyncMock, return_value=True), \
         patch("redis.asyncio.from_url") as mock_redis:
        mock_r = AsyncMock()
        mock_r.ping = AsyncMock(return_value=True)
        mock_redis.return_value = mock_r

        # Import app after patches
        from api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Health endpoint doesn't need auth
            r = await client.get("/health")
            assert r.status_code == 200
            data = r.json()
            assert "status" in data
