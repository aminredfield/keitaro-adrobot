"""Редактор потока: добавить, удалить, вернуть, закрепить, опубликовать, отменить.

Все правки сначала живут только в нашей базе (поток «жёлтый»),
в Keitaro они уходят по кнопке Push.
"""

from sqlalchemy.orm import Session

from app.errors import ConflictError, KeitaroError, NotFoundError, ValidationError
from app.keitaro import KeitaroClient
from app.models import (
    SCHEMA_WITH_OFFERS,
    STATE_ACTIVE,
    STATE_REMOVED,
    Stream,
    StreamOffer,
)
from app.services.sync import ensure_offer, remote_offer_shares
from app.shares import TOTAL_SHARE, distribute


def get_stream(session: Session, stream_id: int) -> Stream:
    stream = session.get(Stream, stream_id)
    if stream is None:
        raise NotFoundError("Поток не найден — сначала нажмите Fetch streams")
    return stream


def add_offer(session: Session, keitaro: KeitaroClient, stream: Stream, offer_id: int) -> Stream:
    if stream.schema != SCHEMA_WITH_OFFERS:
        raise ValidationError("В этот поток нельзя добавлять офферы: он не про офферы")

    existing = _find_by_offer(stream, offer_id)
    if existing is not None and existing.is_active:
        raise ConflictError("Этот оффер уже есть в потоке")
    if existing is not None:
        # оффер лежит в архиве — возвращаем его, а не плодим вторую привязку
        return restore_offer(session, stream, existing.id)

    offer_name = keitaro.find_offer_name(offer_id)
    if offer_name is None:
        raise NotFoundError(f"В Keitaro нет оффера с id {offer_id}")

    offer = ensure_offer(session, offer_id, offer_name)
    stream.offers.append(StreamOffer(offer=offer, state=STATE_ACTIVE))
    return _rebalance_and_save(session, stream)


def remove_offer(session: Session, stream: Stream, binding_id: int) -> Stream:
    binding = _get_binding(stream, binding_id)
    if not binding.is_active:
        raise ConflictError("Оффер уже удалён из потока")

    if binding.is_new:
        # в Keitaro его не было — архивировать нечего, просто убираем
        stream.offers.remove(binding)
    else:
        binding.state = STATE_REMOVED
        binding.share = 0
        binding.pinned = False
    return _rebalance_and_save(session, stream)


def restore_offer(session: Session, stream: Stream, binding_id: int) -> Stream:
    binding = _get_binding(stream, binding_id)
    if binding.is_active:
        raise ConflictError("Оффер и так в потоке")

    binding.state = STATE_ACTIVE
    return _rebalance_and_save(session, stream)


def set_pin(
    session: Session, stream: Stream, binding_id: int, pinned: bool, share: int | None
) -> Stream:
    binding = _get_binding(stream, binding_id)
    if not binding.is_active:
        raise ConflictError("Удалённому офферу нельзя закрепить долю")

    binding.pinned = pinned
    if pinned and share is not None:
        binding.share = share
    return _rebalance_and_save(session, stream)


def cancel(session: Session, stream: Stream) -> Stream:
    """Откатывает поток к тому, что лежит в Keitaro.

    Закрепы тоже снимаются: в Keitaro их нет, а оставшийся закреп
    от отменённой правки незаметно влиял бы на следующие пересчёты.
    """
    for binding in list(stream.offers):
        if binding.is_new:
            stream.offers.remove(binding)
            continue
        binding.state = binding.synced_state
        binding.share = binding.synced_share
        binding.pinned = False
    session.commit()
    return stream


def push(session: Session, keitaro: KeitaroClient, stream: Stream) -> Stream:
    """Публикует поток: отправляет активные офферы в Keitaro и сверяет результат."""
    active = [binding for binding in stream.offers if binding.is_active]
    total = sum(binding.share for binding in active)
    if active and total != TOTAL_SHARE:
        raise ValidationError(
            f"Сумма долей {total}%, а должна быть {TOTAL_SHARE}% — поправьте закрепы"
        )

    # Пока мы правили поток у себя, его могли поменять в Keitaro. Перезаписывать
    # чужие правки молча нельзя — просим сначала сделать Fetch.
    known = {
        binding.offer_id: binding.synced_share
        for binding in stream.offers
        if binding.synced_state == STATE_ACTIVE
    }
    if remote_offer_shares(keitaro.get_stream(stream.id)) != known:
        raise ConflictError("Поток изменили в Keitaro после Fetch — нажмите Fetch streams")

    expected = {binding.offer_id: binding.share for binding in active}
    keitaro.update_stream_offers(
        stream.id,
        [
            {"offer_id": offer_id, "share": share, "state": STATE_ACTIVE}
            for offer_id, share in expected.items()
        ],
    )

    # Не верим на слово: перечитываем поток и сверяем, что в Keitaro те же цифры
    saved = remote_offer_shares(keitaro.get_stream(stream.id))
    if saved != expected:
        raise KeitaroError(
            f"Keitaro сохранил не то, что мы отправили. Отправили {expected}, в Keitaro {saved}"
        )

    for binding in stream.offers:
        binding.synced_state = binding.state
        binding.synced_share = binding.share
    session.commit()
    return stream


def _rebalance_and_save(session: Session, stream: Stream) -> Stream:
    try:
        _rebalance(stream)
    except ValidationError:
        session.rollback()  # правка не прошла — возвращаем поток как был
        raise
    session.commit()
    return stream


def _rebalance(stream: Stream) -> None:
    """Пересчитывает доли: закреплённые не трогаем, остальное делим поровну."""
    active = [binding for binding in stream.offers if binding.is_active]
    pinned = [binding for binding in active if binding.pinned]
    unpinned = [binding for binding in active if not binding.pinned]

    shares = distribute([binding.share for binding in pinned], len(unpinned))
    for binding, share in zip(unpinned, shares):
        binding.share = share


def _get_binding(stream: Stream, binding_id: int) -> StreamOffer:
    for binding in stream.offers:
        if binding.id == binding_id:
            return binding
    raise NotFoundError("В этом потоке нет такой привязки оффера")


def _find_by_offer(stream: Stream, offer_id: int) -> StreamOffer | None:
    for binding in stream.offers:
        if binding.offer_id == offer_id:
            return binding
    return None
