"""완료 기준: /health 응답(compose healthcheck와 같은 경로)."""

import httpx
from debate_mcp.server import create_app


async def test_health():
    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
