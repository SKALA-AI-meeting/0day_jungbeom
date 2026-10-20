"""한 asyncio 루프에서 uvicorn Server 두 개(공개 8000, 내부 8001)를 띄운다.

hub·세션 Lock·스케줄러가 한 프로세스에 있어야 하므로 두 앱을 별도 프로세스로 띄우지 않는다.
--reload는 watchfiles로 이 프로세스 전체를 다시 띄운다(uvicorn 자체 reload는 서버 하나만 다룬다).
"""

import argparse
import asyncio
import logging
from pathlib import Path

import uvicorn

from app import scheduler
from app.main import create_internal_app, create_public_app
from app.services.context import build_context

APP_DIR = Path(__file__).resolve().parent
log = logging.getLogger("app.run")


async def serve(host: str = "0.0.0.0") -> None:
    ctx = build_context()
    public = create_public_app(ctx)
    internal = create_internal_app(ctx)
    servers = [
        uvicorn.Server(uvicorn.Config(public, host=host, port=ctx.settings.public_port)),
        uvicorn.Server(uvicorn.Config(internal, host=host, port=ctx.settings.internal_port)),
    ]
    # 실제 그래프 러너는 첫 실행 전에 체크포인터 풀을 연다(첫 카드가 초기화를 기다리지 않게)
    if hasattr(ctx.runner, "graph"):
        await ctx.runner.graph()
    tasks = [asyncio.create_task(scheduler.run(ctx))]
    try:
        await asyncio.gather(*(server.serve() for server in servers))
    finally:
        for task in tasks:
            task.cancel()
        if hasattr(ctx.runner, "aclose"):
            await ctx.runner.aclose()
        await ctx.publisher.close()
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
