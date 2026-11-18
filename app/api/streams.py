"""Редактор потока. Каждый обработчик возвращает поток целиком после правки."""

from fastapi import APIRouter

from app.api.deps import KeitaroDep, KeitaroId, SessionDep, WriteLock
from app.schemas import OfferAdd, OfferPin, StreamOut, stream_out
from app.services import editor

# Все обработчики здесь меняют поток, поэтому замок на запись стоит на весь роутер
router = APIRouter(
    prefix="/api/streams/{stream_id}", tags=["streams"], dependencies=[WriteLock]
)


@router.post("/offers", response_model=StreamOut)
def add_offer(
    stream_id: KeitaroId, data: OfferAdd, session: SessionDep, keitaro: KeitaroDep
) -> StreamOut:
    stream = editor.get_stream(session, stream_id)
    return stream_out(editor.add_offer(session, keitaro, stream, data.offer_id))


@router.delete("/offers/{binding_id}", response_model=StreamOut)
def remove_offer(stream_id: KeitaroId, binding_id: KeitaroId, session: SessionDep) -> StreamOut:
    stream = editor.get_stream(session, stream_id)
    return stream_out(editor.remove_offer(session, stream, binding_id))


@router.post("/offers/{binding_id}/restore", response_model=StreamOut)
def restore_offer(stream_id: KeitaroId, binding_id: KeitaroId, session: SessionDep) -> StreamOut:
    stream = editor.get_stream(session, stream_id)
    return stream_out(editor.restore_offer(session, stream, binding_id))


@router.patch("/offers/{binding_id}", response_model=StreamOut)
def pin_offer(
    stream_id: KeitaroId, binding_id: KeitaroId, data: OfferPin, session: SessionDep
) -> StreamOut:
    stream = editor.get_stream(session, stream_id)
    return stream_out(editor.set_pin(session, stream, binding_id, data.pinned, data.share))


@router.post("/push", response_model=StreamOut)
def push(stream_id: KeitaroId, session: SessionDep, keitaro: KeitaroDep) -> StreamOut:
    stream = editor.get_stream(session, stream_id)
    return stream_out(editor.push(session, keitaro, stream))


@router.post("/cancel", response_model=StreamOut)
def cancel(stream_id: KeitaroId, session: SessionDep) -> StreamOut:
    stream = editor.get_stream(session, stream_id)
    return stream_out(editor.cancel(session, stream))
