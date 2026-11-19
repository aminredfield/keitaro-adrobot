"""Создаватор: кампания в Keitaro с двумя потоками."""

import logging
import secrets
import string

from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import KeitaroError, NotFoundError, ValidationError
from app.keitaro import KeitaroClient
from app.models import SCHEMA_WITH_OFFERS, STATE_ACTIVE, Campaign
from app.schemas import CampaignCreate
from app.services.sync import sync_campaign
from app.shares import TOTAL_SHARE

ALIAS_LENGTH = 8
ALIAS_ALPHABET = string.ascii_letters + string.digits
AVAILABLE_NAMES_LIMIT = 5

logger = logging.getLogger("adrobot.creator")


def create_campaign(
    session: Session, keitaro: KeitaroClient, settings: Settings, data: CampaignCreate
) -> Campaign:
    name = with_prefix(data.name, settings.campaign_prefix)

    # Всё проверяем до того, как что-то создавать в Keitaro
    if keitaro.find_offer_name(data.offer_id) is None:
        raise NotFoundError(f"В Keitaro нет оффера с id {data.offer_id}")
    domain_id = _find_id(keitaro.list_domains(), settings.domain_host, "домен")
    group_id = _find_id(keitaro.list_campaign_groups(), settings.keitaro_group, "группа")
    source_id = _find_id(keitaro.list_traffic_sources(), settings.keitaro_source, "источник")

    remote = keitaro.create_campaign(
        {
            "name": name,
            "alias": _random_alias(),
            "type": "position",  # потоки проверяются по порядку: сначала гео, потом офферы
            "state": STATE_ACTIVE,
            "domain_id": domain_id,
            "group_id": group_id,
            "traffic_source_id": source_id,
        }
    )
    campaign_id = remote["id"]

    try:
        keitaro.create_stream(_geo_stream(campaign_id, data.geo, settings.geo_redirect_url))
        keitaro.create_stream(_offer_stream(campaign_id, data.offer_id))
    except KeitaroError:
        # Не оставляем в Keitaro кампанию без потоков
        _archive_quietly(keitaro, campaign_id)
        raise

    try:
        campaign = sync_campaign(session, keitaro, campaign_id)
    except KeitaroError as error:
        # Кампания уже полностью создана — удалять её нельзя, но и молчать тоже
        raise KeitaroError(
            f"Кампания создана в Keitaro (id {campaign_id}), но не загрузилась к нам: "
            f"откройте её в редакторе. Причина: {error.message}"
        ) from error
    campaign.geo = ",".join(data.geo)
    campaign.created_by_app = True
    session.commit()
    return campaign


def _archive_quietly(keitaro: KeitaroClient, campaign_id: int) -> None:
    """Архивирует недособранную кампанию. Если не вышло — пишем в лог и не прячем исходную ошибку."""
    try:
        keitaro.archive_campaign(campaign_id)
    except KeitaroError:
        logger.exception("Не удалось отправить в архив кампанию %s", campaign_id)


def with_prefix(name: str, prefix: str) -> str:
    """Добавляет обязательный префикс, если пользователь не написал его сам."""
    if prefix and not name.startswith(prefix):
        return prefix + name
    return name


def _geo_stream(campaign_id: int, geo: list[str], redirect_url: str) -> dict:
    """Первый поток: всех из указанных стран отправляет редиректом на Google."""
    return {
        "campaign_id": campaign_id,
        "name": f"{', '.join(geo)} -> Google",
        "type": "regular",
        "position": 1,
        "schema": "redirect",
        "action_type": "http",
        "action_payload": redirect_url,
        "filters": [{"name": "country", "mode": "accept", "payload": geo}],
        "collect_clicks": True,
        "state": STATE_ACTIVE,
    }


def _offer_stream(campaign_id: int, offer_id: int) -> dict:
    """Второй поток: все остальные идут на выбранный оффер."""
    return {
        "campaign_id": campaign_id,
        "name": "Offers",
        "type": "regular",
        "position": 2,
        "schema": SCHEMA_WITH_OFFERS,
        "action_type": "http",
        "offers": [{"offer_id": offer_id, "share": TOTAL_SHARE, "state": STATE_ACTIVE}],
        "collect_clicks": True,
        "state": STATE_ACTIVE,
    }


def _find_id(items: list[dict], name: str, what: str) -> int:
    """Ищет в справочнике Keitaro запись по имени (без учёта регистра)."""
    if not name:
        raise ValidationError(f"В .env не задан {what} для новых кампаний")
    wanted = name.strip().lower()
    for item in items:
        if str(item.get("name", "")).strip().lower() == wanted:
            return item["id"]
    # Подсказываем, что есть: ключу Keitaro может быть видна только часть справочника
    available = ", ".join(str(item.get("name")) for item in items[:AVAILABLE_NAMES_LIMIT])
    raise NotFoundError(f"В Keitaro не найден {what} «{name}». Доступны: {available or 'ничего'}")


def _random_alias() -> str:
    return "".join(secrets.choice(ALIAS_ALPHABET) for _ in range(ALIAS_LENGTH))
