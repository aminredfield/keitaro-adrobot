"""Поиск для автокомплитов и сведения о настройках."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import KeitaroDep, SettingsDep
from app.schemas import AppInfo, LookupItem

router = APIRouter(prefix="/api", tags=["lookups"])

SEARCH_LIMIT = 20
SearchQuery = Annotated[str, Query(max_length=100)]


@router.get("/info", response_model=AppInfo)
def get_info(settings: SettingsDep) -> AppInfo:
    return AppInfo(
        campaign_prefix=settings.campaign_prefix,
        domain=settings.domain_host,
        group=settings.keitaro_group,
        source=settings.keitaro_source,
        geo_redirect_url=settings.geo_redirect_url,
        keitaro_configured=bool(settings.keitaro_url and settings.keitaro_api_key),
    )


@router.get("/offers", response_model=list[LookupItem])
def search_offers(keitaro: KeitaroDep, q: SearchQuery = "") -> list[LookupItem]:
    return _search(keitaro.list_offers(), q)


@router.get("/keitaro/campaigns", response_model=list[LookupItem])
def search_campaigns(keitaro: KeitaroDep, q: SearchQuery = "") -> list[LookupItem]:
    return _search(keitaro.list_campaigns(), q)


def _search(items: list[dict], query: str) -> list[LookupItem]:
    """Ищет по вхождению в имя или по id. Свежие записи (с большим id) — первыми."""
    query = query.strip().lower()
    found = []
    for item in items:
        if "id" not in item:
            continue  # Keitaro прислал что-то странное — пропускаем
        name = str(item.get("name") or "")
        if query in name.lower() or query == str(item["id"]):
            found.append(LookupItem(id=item["id"], name=name))
    found.sort(key=lambda item: item.id, reverse=True)
    return found[:SEARCH_LIMIT]
