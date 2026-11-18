"""Клиент Admin API Keitaro. Вся работа с сетью — только здесь."""

import logging
import time
from collections.abc import Callable
from functools import lru_cache
from typing import Any

import httpx

from app.config import get_settings
from app.errors import KeitaroError

API_PATH = "/admin_api/v1"
NOT_FOUND = 404
UNAUTHORIZED = 401
ERROR_TEXT_LIMIT = 200

logger = logging.getLogger("adrobot.keitaro")


class KeitaroClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 20.0,
        cache_seconds: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._configured = bool(base_url and api_key)
        self._cache_seconds = cache_seconds
        self._cache: dict[str, tuple[float, Any]] = {}
        self._http = httpx.Client(
            base_url=base_url.rstrip("/") + API_PATH,
            headers={"Api-Key": api_key},
            timeout=timeout,
            transport=transport,
        )

    # --- справочники (кэшируются) ---

    def list_offers(self) -> list[dict]:
        return self._cached("offers", lambda: self._get_list("/offers"))

    def list_campaigns(self) -> list[dict]:
        return self._cached("campaigns", lambda: self._get_list("/campaigns"))

    def list_domains(self) -> list[dict]:
        return self._cached("domains", lambda: self._get_list("/domains"))

    def list_campaign_groups(self) -> list[dict]:
        return self._cached("groups", lambda: self._get_list("/groups", {"type": "campaigns"}))

    def list_traffic_sources(self) -> list[dict]:
        return self._cached("sources", lambda: self._get_list("/traffic_sources"))

    def find_offer_name(self, offer_id: int) -> str | None:
        """Имя оффера по id или None, если такого оффера нет.

        Если оффера нет в кэше, один раз перечитываем список: оффер могли
        создать в Keitaro минуту назад.
        """
        for attempt in range(2):
            for offer in self.list_offers():
                if offer.get("id") == offer_id:
                    return str(offer.get("name") or f"Оффер #{offer_id}")
            if attempt == 0:
                self._cache.pop("offers", None)
        return None

    # --- кампании и потоки ---

    def get_campaign(self, campaign_id: int) -> dict:
        return self._get_dict("GET", f"/campaigns/{campaign_id}")

    def create_campaign(self, payload: dict) -> dict:
        campaign = self._get_dict("POST", "/campaigns", json=payload)
        self._cache.pop("campaigns", None)  # список кампаний устарел
        return campaign

    def archive_campaign(self, campaign_id: int) -> None:
        self._request("DELETE", f"/campaigns/{campaign_id}")
        self._cache.pop("campaigns", None)

    def get_campaign_streams(self, campaign_id: int) -> list[dict]:
        return self._get_list(f"/campaigns/{campaign_id}/streams")

    def get_stream(self, stream_id: int) -> dict:
        return self._get_dict("GET", f"/streams/{stream_id}")

    def create_stream(self, payload: dict) -> dict:
        return self._get_dict("POST", "/streams", json=payload)

    def update_stream_offers(self, stream_id: int, offers: list[dict]) -> dict:
        return self._get_dict("PUT", f"/streams/{stream_id}", json={"offers": offers})

    # --- внутреннее ---

    def _cached(self, key: str, load: Callable[[], Any]) -> Any:
        cached = self._cache.get(key)
        if cached and time.monotonic() - cached[0] < self._cache_seconds:
            return cached[1]
        value = load()
        self._cache[key] = (time.monotonic(), value)
        return value

    def _get_list(self, path: str, params: dict | None = None) -> list[dict]:
        """Запрос, на который Keitaro должен ответить списком объектов."""
        data = self._request("GET", path, params=params)
        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise KeitaroError(f"Keitaro вернул неожиданный ответ на GET {path}")
        return data

    def _get_dict(self, method: str, path: str, **kwargs: Any) -> dict:
        """Запрос, на который Keitaro должен ответить объектом с полем id."""
        data = self._request(method, path, **kwargs)
        if not isinstance(data, dict) or "id" not in data:
            raise KeitaroError(f"Keitaro вернул неожиданный ответ на {method} {path}")
        return data

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self._configured:
            raise KeitaroError("Не заданы KEITARO_URL и KEITARO_API_KEY в .env")

        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            # Текст исключения наружу не отдаём: в нём бывают внутренние адреса,
            # а при кривом ключе — и сам ключ. Хватит названия ошибки.
            reason = type(error).__name__
            logger.error("Keitaro request failed: %s %s (%s)", method, path, reason)
            raise KeitaroError(f"Keitaro недоступен ({reason})") from error

        if response.status_code == UNAUTHORIZED:
            raise KeitaroError("Keitaro не принял API-ключ — проверьте KEITARO_API_KEY")
        if response.status_code == NOT_FOUND:
            raise KeitaroError(f"Keitaro: не найдено ({method} {path})")
        if response.is_error:
            raise KeitaroError(f"Keitaro ответил {response.status_code}: {_error_text(response)}")

        try:
            return response.json()
        except ValueError as error:
            raise KeitaroError("Keitaro вернул ответ не в формате JSON") from error


def _error_text(response: httpx.Response) -> str:
    """Достаёт короткий текст ошибки из ответа Keitaro, не роняя нас на неожиданном формате."""
    try:
        body = response.json()
    except ValueError:
        body = response.text
    if isinstance(body, dict) and body.get("error"):
        body = body["error"]
    # одна строка ограниченной длины: трейсы и простыни HTML пользователю не нужны
    return " ".join(str(body).split())[:ERROR_TEXT_LIMIT]


@lru_cache
def get_keitaro() -> KeitaroClient:
    settings = get_settings()
    return KeitaroClient(
        base_url=settings.keitaro_base_url,
        api_key=settings.keitaro_api_key,
        timeout=settings.keitaro_timeout_seconds,
        cache_seconds=settings.keitaro_cache_seconds,
    )
