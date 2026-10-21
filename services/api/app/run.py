"""한 asyncio 루프에서 uvicorn Server 두 개(공개 8000, 내부 8001)를 띄운다.

hub·세션 메일박스·스케줄러가 한 프로세스에 있어야 하므로 두 앱을 별도 프로세스로 띄우지 않는다.
G-F 시점의 컨텍스트는 설정·DB 엔진뿐이다. hub·메일박스·스케줄러·AgentRunner 연결은 api 트랙이
`RuntimeContext`를 넓혀 넣는다. --reload는 watchfiles로 이 프로세스 전체를 다시 띄운다.
"""

import argparse
import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

import uvicorn
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.db import make_engine, make_session_factory
from app.main import create_internal_app, create_public_app

APP_DIR = Path(__file__).resolve().parent
log = logging.getLogger("app.run")


@dataclass
class RuntimeContext:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]


def build_runtime(settings: Settings | None = None) -> RuntimeContext:
    settings = settings or get_settings()
    engine = make_engine(settings.database_url)
    return RuntimeContext(settings, engine, make_session_factory(engine))


async def serve(host: str = "0.0.0.0") -> None:
    ctx = build_runtime()
    public = create_public_app(ctx, ctx.settings.web_origins)
    internal = create_internal_app(ctx)
    servers = [
        uvicorn.Server(uvicorn.Config(public, host=host, port=ctx.settings.public_port)),
        uvicorn.Server(uvicorn.Config(internal, host=host, port=ctx.settings.internal_port)),
    ]
    try:
        await asyncio.gather(*(server.serve() for server in servers))
    finally:
        await ctx.engine.dispose()


def _serve_sync(host: str) -> None:
    asyncio.run(serve(host))


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.run")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--reload", action="store_true", help="app/ 변경 시 재시작(개발용)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.reload:
        import watchfiles

        watchfiles.run_process(APP_DIR, target=_serve_sync, args=(args.host,))
    else:
        _serve_sync(args.host)


if __name__ == "__main__":
    main()
