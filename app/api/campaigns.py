"""Кампании: создать, посмотреть, подтянуть потоки из Keitaro."""

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import KeitaroDep, KeitaroId, SessionDep, SettingsDep, WriteLock
from app.config import Settings
from app.errors import NotFoundError
from app.models import Campaign
from app.schemas import CampaignCreate, CampaignListItem, CampaignOut, campaign_out
from app.services.creator import create_campaign
from app.services.sync import sync_campaign

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])

LIST_LIMIT = 50


@router.get("", response_model=list[CampaignListItem])
def list_campaigns(session: SessionDep) -> list[CampaignListItem]:
    """Кампании, которые уже есть в нашей базе: созданные у нас или открытые в редакторе."""
    campaigns = session.scalars(
        select(Campaign).order_by(Campaign.synced_at.desc()).limit(LIST_LIMIT)
    )
    return [
        CampaignListItem(
            id=campaign.id,
            name=campaign.name,
            geo=campaign.geo,
            created_by_app=campaign.created_by_app,
        )
        for campaign in campaigns
    ]


@router.post(
    "", response_model=CampaignOut, status_code=status.HTTP_201_CREATED, dependencies=[WriteLock]
)
def create(
    data: CampaignCreate, session: SessionDep, keitaro: KeitaroDep, settings: SettingsDep
) -> CampaignOut:
    campaign = create_campaign(session, keitaro, settings, data)
    return _out(campaign, settings)


@router.get("/{campaign_id}", response_model=CampaignOut)
def get_campaign(
    campaign_id: KeitaroId, session: SessionDep, settings: SettingsDep
) -> CampaignOut:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise NotFoundError("Кампании нет в нашей базе — нажмите Fetch streams")
    return _out(campaign, settings)


@router.post("/{campaign_id}/fetch", response_model=CampaignOut, dependencies=[WriteLock])
def fetch_streams(
    campaign_id: KeitaroId, session: SessionDep, keitaro: KeitaroDep, settings: SettingsDep
) -> CampaignOut:
    campaign = sync_campaign(session, keitaro, campaign_id)
    return _out(campaign, settings)


def _out(campaign: Campaign, settings: Settings) -> CampaignOut:
    return campaign_out(campaign, settings.keitaro_base_url, settings.domain_host)
