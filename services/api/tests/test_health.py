"""완료 기준: 한 프로세스의 공개(8000)·내부(8001) 앱이 둘 다 /health에 응답."""

import httpx
from app.main import create_internal_app, create_public_app
from app.services.context import build_context


async def test_public_and_internal_health():
    ctx = build_context()
    for app in (create_public_app(ctx), create_internal_app(ctx)):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
        assert response.json() == {"status": "ok"}
    await ctx.engine.dispose()
