"""Тестовое окружение: база в памяти и поддельный Keitaro вместо настоящего."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.db import Base, get_session
from app.keitaro import API_PATH, KeitaroClient, get_keitaro
from app.main import create_app

API_KEY = "test-key"
PREFIX = "test_ivanov_"


class FakeKeitaro:
    """Повторяет нужную нам часть Admin API Keitaro и хранит всё в словарях."""

    def __init__(self) -> None:
        self.offers = {3749: "Beauty RO spin", 3717: "Beauty RO prize", 11111: "Weight loss CO", 11112: "Beauty CL"}
        self.domains = [{"id": 7, "name": "tracker.example.com"}]
        self.groups = [{"id": 5, "name": "FORTESTS"}]
        self.sources = [{"id": 9, "name": "FORTESTS"}]
        self.campaigns: dict[int, dict] = {}
        self.streams: dict[int, dict] = {}
        self.archived_campaigns: list[int] = []
        self.fail_stream_creation = False
        self.fail_stream_listing = False
        self.fail_archive = False
        self._last_id = 100

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("Api-Key") != API_KEY:
            return httpx.Response(401, json={"error": "Unauthorized"})

        method = request.method
        parts = request.url.path.removeprefix(API_PATH).strip("/").split("/")
        body = json.loads(request.content) if request.content else {}

        if method == "GET" and parts == ["offers"]:
            return httpx.Response(200, json=[{"id": i, "name": n} for i, n in self.offers.items()])
        if method == "GET" and parts == ["domains"]:
            return httpx.Response(200, json=self.domains)
        if method == "GET" and parts == ["groups"]:
            return httpx.Response(200, json=self.groups)
        if method == "GET" and parts == ["traffic_sources"]:
            return httpx.Response(200, json=self.sources)
        if method == "GET" and parts == ["campaigns"]:
            return httpx.Response(200, json=list(self.campaigns.values()))
        if method == "POST" and parts == ["campaigns"]:
            campaign = {**body, "id": self._next_id()}
            self.campaigns[campaign["id"]] = campaign
            return httpx.Response(200, json=campaign)
        if method == "POST" and parts == ["streams"]:
            if self.fail_stream_creation:
                return httpx.Response(400, json={"error": "stream is broken"})
            return httpx.Response(200, json=self.add_stream(body))

        if len(parts) >= 2 and parts[0] == "campaigns":
            campaign_id = int(parts[1])
            if campaign_id not in self.campaigns:
                return httpx.Response(404, json={"error": "not found"})
            if method == "GET" and len(parts) == 2:
                return httpx.Response(200, json=self.campaigns[campaign_id])
            if method == "DELETE" and len(parts) == 2:
                if self.fail_archive:
                    return httpx.Response(500, json={"error": "archive is broken"})
                self.archived_campaigns.append(campaign_id)
                del self.campaigns[campaign_id]
                return httpx.Response(200, json={})
            if method == "GET" and parts[2:] == ["streams"]:
                if self.fail_stream_listing:
                    return httpx.Response(500, json={"error": "listing is broken"})
                streams = [s for s in self.streams.values() if s["campaign_id"] == campaign_id]
                return httpx.Response(200, json=streams)

        if len(parts) == 2 and parts[0] == "streams":
            stream = self.streams.get(int(parts[1]))
            if stream is None:
                return httpx.Response(404, json={"error": "not found"})
            if method == "PUT":
                stream["offers"] = self._offers(stream["id"], body["offers"])
            return httpx.Response(200, json=stream)

        return httpx.Response(404, json={"error": f"no route {method} {request.url.path}"})

    def add_campaign(self, name: str = "campaign 2") -> dict:
        campaign = {"id": self._next_id(), "name": name, "alias": "abc123"}
        self.campaigns[campaign["id"]] = campaign
        return campaign

    def add_stream(self, payload: dict) -> dict:
        stream_id = self._next_id()
        stream = {**payload, "id": stream_id, "state": "active"}
        stream["offers"] = self._offers(stream_id, payload.get("offers", []))
        self.streams[stream_id] = stream
        return stream

    def shares(self, stream_id: int) -> dict[int, int]:
        return {offer["offer_id"]: offer["share"] for offer in self.streams[stream_id]["offers"]}

    def _offers(self, stream_id: int, offers: list[dict]) -> list[dict]:
        return [{**offer, "id": self._next_id(), "stream_id": stream_id} for offer in offers]

    def _next_id(self) -> int:
        self._last_id += 1
        return self._last_id


@pytest.fixture
def fake() -> FakeKeitaro:
    return FakeKeitaro()


@pytest.fixture(scope="session")
def app_client():
    """Одно приложение и один клиент на весь прогон: быстрее и не плодит event loop'ы."""
    app = create_app(Settings(_env_file=None, allowed_hosts="testserver"))
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client(app_client: TestClient, fake: FakeKeitaro):
    """Клиент с чистой базой и свежим поддельным Keitaro для каждого теста."""
    # StaticPool держит одно соединение, иначе у каждой сессии была бы своя пустая база в памяти
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    make_session = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session():
        with make_session() as session:
            yield session

    keitaro = KeitaroClient(
        base_url="https://keitaro.test",
        api_key=API_KEY,
        cache_seconds=0,
        transport=httpx.MockTransport(fake.handler),
    )
    settings = Settings(
        _env_file=None,
        keitaro_url="https://keitaro.test",
        keitaro_api_key=API_KEY,
        keitaro_domain="https://tracker.example.com/",
        keitaro_group="FORTESTS",
        keitaro_source="FORTESTS",
        campaign_prefix=PREFIX,
    )

    app = app_client.app
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_keitaro] = lambda: keitaro
    app.dependency_overrides[get_settings] = lambda: settings

    yield app_client

    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def campaign(fake: FakeKeitaro) -> dict:
    """Кампания как в видео: поток-редирект по гео и поток с тремя офферами."""
    campaign = fake.add_campaign()
    fake.add_stream(
        {"campaign_id": campaign["id"], "name": "Flow 1", "position": 1, "schema": "redirect"}
    )
    offers_stream = fake.add_stream(
        {
            "campaign_id": campaign["id"],
            "name": "Flow 2",
            "position": 2,
            "schema": "landings",
            "offers": [
                {"offer_id": 3749, "share": 33, "state": "active"},
                {"offer_id": 3717, "share": 33, "state": "active"},
                {"offer_id": 11111, "share": 34, "state": "active"},
            ],
        }
    )
    return {"id": campaign["id"], "stream_id": offers_stream["id"]}
