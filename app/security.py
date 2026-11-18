"""Защита локального сервера без авторизации от чужих сайтов в том же браузере.

У приложения нет логина, поэтому любая страница, открытая в браузере пользователя,
могла бы дёрнуть http://localhost:8000/api/... и, например, опубликовать поток.
Здесь мы отсекаем такие запросы и ставим базовые заголовки безопасности.
"""

from collections.abc import Awaitable, Callable
from urllib.parse import urlparse

from fastapi import Request, Response
from fastapi.responses import JSONResponse

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# Swagger грузит скрипты с CDN, строгая политика его ломает
DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
}

NextHandler = Callable[[Request], Awaitable[Response]]


async def guard_requests(request: Request, call_next: NextHandler) -> Response:
    if request.method not in SAFE_METHODS and _is_foreign_origin(request):
        return JSONResponse(status_code=403, content={"detail": "Запрос с чужого сайта отклонён"})

    response = await call_next(request)
    if not request.url.path.startswith(DOCS_PATHS):
        response.headers.update(SECURITY_HEADERS)
    return response


def _is_foreign_origin(request: Request) -> bool:
    """Браузер сам ставит Origin на запросы, меняющие данные. Чужой Origin — чужой сайт."""
    origin = request.headers.get("origin")
    if origin is None:
        return False  # не браузер (curl, тесты) или старый браузер на том же сайте
    return urlparse(origin).netloc != request.headers.get("host")
