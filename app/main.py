"""Сборка приложения: роуты API, обработка ошибок и раздача фронта."""

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api import campaigns, lookups, streams
from app.config import Settings, get_settings
from app.errors import AppError
from app.security import guard_requests

STATIC_DIR = Path(__file__).parent / "static"

logger = logging.getLogger("adrobot")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Adrobot: обёртка над Keitaro")

    # Авторизации у приложения нет, поэтому закрываемся от чужих сайтов: см. app/security.py
    app.middleware("http")(guard_requests)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_host_list)

    app.include_router(lookups.router)
    app.include_router(campaigns.router)
    app.include_router(streams.router)

    @app.exception_handler(AppError)
    def handle_app_error(request: Request, error: AppError) -> JSONResponse:
        logger.warning("%s %s -> %s", request.method, request.url.path, error.message)
        return JSONResponse(status_code=error.status_code, content={"detail": error.message})

    @app.exception_handler(RequestValidationError)
    def handle_validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        # Приводим ошибки pydantic к тому же виду, что и наши: одна понятная строка
        messages = [str(item["msg"]).removeprefix("Value error, ") for item in error.errors()]
        return JSONResponse(status_code=422, content={"detail": "; ".join(messages)})

    @app.exception_handler(IntegrityError)
    def handle_integrity_error(request: Request, error: IntegrityError) -> JSONResponse:
        # Два запроса одновременно создали одну и ту же запись
        logger.warning("%s %s -> конфликт записи", request.method, request.url.path)
        return JSONResponse(status_code=409, content={"detail": "Параллельное изменение, повторите"})

    @app.exception_handler(OperationalError)
    def handle_database_error(request: Request, error: OperationalError) -> JSONResponse:
        logger.error("%s %s -> ошибка базы: %s", request.method, request.url.path, error.orig)
        return JSONResponse(
            status_code=500,
            content={"detail": "База не готова. Выполните миграции: alembic upgrade head"},
        )

    @app.exception_handler(Exception)
    def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
        # Подробности — только в лог, пользователю хватит одной строки в общем формате
        logger.exception("%s %s -> необработанная ошибка", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Внутренняя ошибка сервера"})

    # Фронт монтируем последним, чтобы он не перехватывал /api
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


app = create_app()
