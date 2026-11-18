"""Fetch streams: приводим нашу базу к тому, что сейчас лежит в Keitaro."""

from sqlalchemy.orm import Session

from app.keitaro import KeitaroClient
from app.models import (
    STATE_ACTIVE,
    STATE_REMOVED,
    Campaign,
    Offer,
    Stream,
    StreamOffer,
    utc_now,
)

KEITARO_DELETED = "deleted"


def sync_campaign(session: Session, keitaro: KeitaroClient, campaign_id: int) -> Campaign:
    """Забирает кампанию и её потоки из Keitaro и сохраняет у нас.

    Keitaro здесь главный: неопубликованные правки потоков затираются.
    Не затираются только архив удалённых офферов и закрепы.
    """
    remote_campaign = keitaro.get_campaign(campaign_id)
    remote_streams = [
        stream
        for stream in keitaro.get_campaign_streams(campaign_id)
        if "id" in stream and stream.get("state") != KEITARO_DELETED
    ]
    offer_names = {offer.get("id"): offer.get("name") for offer in keitaro.list_offers()}

    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        campaign = Campaign(id=campaign_id, name="", alias="")
        session.add(campaign)
    campaign.name = str(remote_campaign.get("name") or f"Кампания {campaign_id}")
    campaign.alias = str(remote_campaign.get("alias") or "")
    campaign.synced_at = utc_now()

    local_streams = {stream.id: stream for stream in campaign.streams}
    for remote in remote_streams:
        stream = local_streams.get(remote["id"])
        if stream is None:
            stream = Stream(id=remote["id"], name="")
            campaign.streams.append(stream)
        stream.name = remote.get("name") or f"Поток {remote['id']}"
        stream.position = remote.get("position") or 0
        stream.schema = remote.get("schema") or ""
        _sync_stream_offers(session, stream, remote_offer_shares(remote), offer_names)

    # Потоки, которых в Keitaro больше нет, у нас тоже не нужны
    remote_ids = {remote["id"] for remote in remote_streams}
    for stream in list(campaign.streams):
        if stream.id not in remote_ids:
            campaign.streams.remove(stream)

    session.commit()
    return campaign


def remote_offer_shares(remote_stream: dict) -> dict[int, int]:
    """Офферы потока из ответа Keitaro в виде {id оффера: доля}."""
    return {
        offer["offer_id"]: offer.get("share") or 0
        for offer in remote_stream.get("offers") or []
        if isinstance(offer, dict) and "offer_id" in offer
    }


def ensure_offer(session: Session, offer_id: int, name: str | None) -> Offer:
    """Создаёт или обновляет запись оффера в нашем справочнике.

    name = None значит, что Keitaro имя не сообщил: уже известное имя не трогаем.
    """
    offer = session.get(Offer, offer_id)
    if offer is None:
        offer = Offer(id=offer_id, name=name or f"Оффер #{offer_id}")
        session.add(offer)
    elif name:
        offer.name = name
    return offer


def _sync_stream_offers(
    session: Session,
    stream: Stream,
    remote_shares: dict[int, int],
    offer_names: dict[int, str | None],
) -> None:
    local = {binding.offer_id: binding for binding in stream.offers}

    for offer_id, share in remote_shares.items():
        offer = ensure_offer(session, offer_id, offer_names.get(offer_id))
        binding = local.get(offer_id)
        if binding is None:
            binding = StreamOffer(offer=offer)
            stream.offers.append(binding)
        binding.share = binding.synced_share = share
        binding.state = binding.synced_state = STATE_ACTIVE

    for offer_id, binding in local.items():
        if offer_id in remote_shares:
            continue
        if binding.is_new:
            # добавили у нас, но не опубликовали — в Keitaro его не было, убираем
            stream.offers.remove(binding)
        else:
            # был в Keitaro и пропал — уходит в архив, откуда его можно вернуть
            binding.share = binding.synced_share = 0
            binding.state = binding.synced_state = STATE_REMOVED
            binding.pinned = False
