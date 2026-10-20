"""FastAPI 앱 2개. 공개(8000): /admin, /s, /sessions, /ws. 내부(8001): /internal.

라우터는 각 트랙이 app/routers/<이름>.py에 `router`로 만든다. 모듈이 있으면 자동으로 붙이므로
라우터 트랙은 이 파일을 고치지 않는다.
"""

import importlib
import importlib.util

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.services.context import AppContext
from app.services.session import SessionError

PUBLIC_ROUTERS = ("admin", "candidate", "ws")
INTERNAL_ROUTERS = ("internal",)

ERROR_STATUS = {
    "not_found": 404,
    "forbidden": 403,
    "conflict": 409,
    "session_ending": 409,
    "expired": 410,
    "cancelled": 410,
}


def _include(app: FastAPI, names: tuple[str, ...]) -> None:
    for name in names:
        module_name = f"app.routers.{name}"
        if importlib.util.find_spec(module_name) is not None:
            app.include_router(importlib.import_module(module_name).router)


async def _session_error(_: Request, exc: SessionError) -> JSONResponse:
    body = {"error": {"code": exc.code, "message": exc.message}}
    return JSONResponse(body, status_code=ERROR_STATUS.get(exc.code, 400))


async def _http_error(_: Request, exc: HTTPException) -> JSONResponse:
    # auth 의존성은 detail에 이미 {"error": {...}}를 담는다. 그 외에는 같은 형식으로 감싼다.
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        body = exc.detail
    else:
        body = {"error": {"code": "http_error", "message": str(exc.detail)}}
    return JSONResponse(body, status_code=exc.status_code, headers=exc.headers)


async def _invalid_input(_: Request, exc: RequestValidationError) -> JSONResponse:
    message = "; ".join(
        f"{'.'.join(str(part) for part in e['loc'])}: {e['msg']}" for e in exc.errors()
    )
    body = {"error": {"code": "invalid_input", "message": message}}
    return JSONResponse(body, status_code=422)


def _base(title: str, ctx: AppContext) -> FastAPI:
    app = FastAPI(title=title)
    app.state.ctx = ctx
    app.add_exception_handler(SessionError, _session_error)
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _invalid_input)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


CORS_HEADERS = ["Authorization", "Content-Type", "Idempotency-Key"]


def create_public_app(ctx: AppContext) -> FastAPI:
    app = _base("Day Zero api", ctx)
    # 브라우저(web)가 8000을 직접 부른다. 인증은 Bearer 헤더라 쿠키 자격 증명은 허용하지 않는다.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(ctx.settings.web_origins),
        allow_methods=["*"],
        allow_headers=CORS_HEADERS,
    )
    _include(app, PUBLIC_ROUTERS)
    return app


def create_internal_app(ctx: AppContext) -> FastAPI:
    app = _base("Day Zero internal api", ctx)
    _include(app, INTERNAL_ROUTERS)
    return app
