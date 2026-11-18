"""Схемы запросов и ответов нашего API."""

import re
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator

from app.models import SCHEMA_WITH_OFFERS, Campaign, Stream, StreamOffer
from app.shares import TOTAL_SHARE

COUNTRY_CODE = re.compile(r"^[A-Z]{2}$")
MAX_ID = 2**31 - 1  # id должен помещаться в INTEGER базы


# --- запросы ---


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    # Принимаем и строку "MX, AU", и список — приводим к списку кодов
    geo: list[str]
    offer_id: int = Field(gt=0, le=MAX_ID)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Название не может быть пустым")
        if not value.isprintable():
            raise ValueError("В названии есть непечатаемые символы")
        return value

    @field_validator("geo", mode="before")
    @classmethod
    def parse_geo(cls, value: object) -> list[str]:
        if isinstance(value, str):
            value = value.split(",")
        if not isinstance(value, list):
            raise ValueError("Гео — это коды стран через запятую, например MX,AU")

        codes = [str(item).strip().upper() for item in value if str(item).strip()]
        if not codes:
            raise ValueError("Укажите хотя бы один код страны")
        for code in codes:
            if not COUNTRY_CODE.match(code):
                raise ValueError(f"'{code}' не похоже на двухбуквенный код страны")
        # dict.fromkeys убирает повторы и сохраняет порядок
        return list(dict.fromkeys(codes))


class OfferAdd(BaseModel):
    offer_id: int = Field(gt=0, le=MAX_ID)


class OfferPin(BaseModel):
    pinned: bool
    # Если доля передана, закрепляем именно её, иначе — текущую
    share: int | None = Field(default=None, ge=1, le=TOTAL_SHARE)


# --- ответы ---


class LookupItem(BaseModel):
    id: int
    name: str


class AppInfo(BaseModel):
    campaign_prefix: str
    domain: str
    group: str
    source: str
    geo_redirect_url: str
    keitaro_configured: bool


class StreamOfferOut(BaseModel):
    id: int
    offer_id: int
    offer_name: str
    share: int
    pinned: bool
    state: str
    is_new: bool


class StreamOut(BaseModel):
    id: int
    name: str
    position: int
    has_offers_schema: bool
    is_dirty: bool
    share_total: int
    offers: list[StreamOfferOut]


class CampaignOut(BaseModel):
    id: int
    name: str
    alias: str
    geo: str | None
    created_by_app: bool
    synced_at: datetime
    url: str | None
    keitaro_url: str | None
    streams: list[StreamOut]


class CampaignListItem(BaseModel):
    id: int
    name: str
    geo: str | None
    created_by_app: bool


# --- сборка ответов из моделей ---


def offer_out(binding: StreamOffer) -> StreamOfferOut:
    return StreamOfferOut(
        id=binding.id,
        offer_id=binding.offer_id,
        offer_name=binding.offer.name,
        share=binding.share,
        pinned=binding.pinned,
        state=binding.state,
        is_new=binding.is_new,
    )


def stream_out(stream: Stream) -> StreamOut:
    # Сначала активные, удалённые (архив) — в конце
    bindings = sorted(stream.offers, key=lambda binding: (not binding.is_active, binding.id))
    return StreamOut(
        id=stream.id,
        name=stream.name,
        position=stream.position,
        has_offers_schema=stream.schema == SCHEMA_WITH_OFFERS,
        is_dirty=any(binding.is_changed for binding in stream.offers),
        share_total=sum(binding.share for binding in stream.offers if binding.is_active),
        offers=[offer_out(binding) for binding in bindings],
    )


def campaign_out(campaign: Campaign, keitaro_url: str, domain: str) -> CampaignOut:
    return CampaignOut(
        id=campaign.id,
        name=campaign.name,
        alias=campaign.alias,
        geo=campaign.geo,
        created_by_app=campaign.created_by_app,
        # SQLite отдаёт время без зоны; мы всегда пишем UTC, поэтому зону дописываем сами
        synced_at=campaign.synced_at.replace(tzinfo=timezone.utc),
        url=f"https://{domain}/{campaign.alias}" if domain else None,
        keitaro_url=f"{keitaro_url}/admin/#!/campaigns/{campaign.id}" if keitaro_url else None,
        streams=[stream_out(stream) for stream in campaign.streams],
    )
