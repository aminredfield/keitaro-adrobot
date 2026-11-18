"""Таблицы. У кампаний, потоков и офферов id совпадает с id в Keitaro."""

from datetime import datetime, timezone

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

STATE_ACTIVE = "active"
STATE_REMOVED = "removed"

# Схема потока Keitaro, в которой бывают офферы
SCHEMA_WITH_OFFERS = "landings"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str]
    alias: Mapped[str]
    # Гео заполняется только у кампаний, созданных через нашу форму
    geo: Mapped[str | None] = mapped_column(default=None)
    created_by_app: Mapped[bool] = mapped_column(default=False)
    synced_at: Mapped[datetime] = mapped_column(default=utc_now)

    streams: Mapped[list["Stream"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan", order_by="Stream.position"
    )


class Stream(Base):
    __tablename__ = "streams"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    name: Mapped[str]
    position: Mapped[int] = mapped_column(default=0)
    schema: Mapped[str] = mapped_column(default="")

    campaign: Mapped[Campaign] = relationship(back_populates="streams")
    offers: Mapped[list["StreamOffer"]] = relationship(
        back_populates="stream", cascade="all, delete-orphan", order_by="StreamOffer.id"
    )


class Offer(Base):
    """Справочник офферов, которые мы уже видели: нужен, чтобы показывать имена."""

    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str]


class StreamOffer(Base):
    """Привязка оффера к потоку.

    share/state — то, что видит пользователь у нас.
    synced_share/synced_state — то, что лежит в Keitaro. Если они расходятся,
    поток не опубликован. synced_state = None значит, что оффер добавили у нас
    и в Keitaro его ещё не было.
    """

    __tablename__ = "stream_offers"
    __table_args__ = (UniqueConstraint("stream_id", "offer_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stream_id: Mapped[int] = mapped_column(ForeignKey("streams.id"), index=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id"))

    share: Mapped[int] = mapped_column(default=0)
    state: Mapped[str] = mapped_column(default=STATE_ACTIVE)
    pinned: Mapped[bool] = mapped_column(default=False)

    synced_share: Mapped[int] = mapped_column(default=0)
    synced_state: Mapped[str | None] = mapped_column(default=None)

    stream: Mapped[Stream] = relationship(back_populates="offers")
    offer: Mapped[Offer] = relationship()

    @property
    def is_active(self) -> bool:
        return self.state == STATE_ACTIVE

    @property
    def is_new(self) -> bool:
        return self.synced_state is None

    @property
    def is_changed(self) -> bool:
        return self.state != self.synced_state or self.share != self.synced_share
