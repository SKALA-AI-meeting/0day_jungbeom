"""FastAPI 앱 2개. 공개(8000): /admin, /s, /sessions, /ws, /assets. 내부(8001): /internal.

라우터는 api 트랙이 app/routers/<이름>.py에 `router`로 만들고 아래 목록에 이름을 넣는다.
G-F 시점에는 토론형 라우터가 아직 없어 목록이 비어 있다.
옛 라우터는 옛 모델을 import하므로 붙이지 않는다.
오류 응답은 contracts.md "공통" 형식 `{"error": {"code", "message"}}`,
입력 검증 실패는 422 invalid_input.
"""

import importlib
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

PUBLIC_ROUTERS: tuple[str, ...] = ()
INTERNAL_ROUTERS: tuple[str, ...] = ()
CORS_HEADERS = ["Authorization", "Content-Type"]


def _include(app: FastAPI, names: tuple[str, ...]) -> None:
    for name in names:
        app.include_router(importlib.import_module(f"app.routers.{name}").router)


async def _http_error(_: Request, exc: HTTPException) -> JSONResponse:
    # 의존성이 detail에 이미 {"error": {...}}를 담았으면 그대로, 아니면 같은 형식으로 감싼다
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        body = exc.detail
    else:
        body = {"error": {"code": "http_error", "message": str(exc.detail)}}
    return JSONResponse(body, status_code=exc.status_code, headers=exc.headers)


async def _invalid_input(_: Request, exc: RequestValidationError) -> JSONResponse:
    message = "; ".join(
        f"{'.'.join(str(part) for part in e['loc'])}: {e['msg']}" for e in exc.errors()
    )
    return JSONResponse({"error": {"code": "invalid_input", "message": message}}, status_code=422)


def _base(title: str, ctx: Any) -> FastAPI:
    app = FastAPI(title=title)
    app.state.ctx = ctx
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _invalid_input)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def create_public_app(ctx: Any, web_origins: tuple[str, ...] = ()) -> FastAPI:
    app = _base("Day Zero api", ctx)
    # 브라우저(web)가 8000을 직접 부른다. 인증은 Bearer 헤더라 쿠키 자격 증명은 허용하지 않는다.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(web_origins),
        allow_methods=["*"],
        allow_headers=CORS_HEADERS,
    )
    _include(app, PUBLIC_ROUTERS)
    return app


def create_internal_app(ctx: Any) -> FastAPI:
    app = _base("Day Zero internal api", ctx)
    _include(app, INTERNAL_ROUTERS)
    return app
