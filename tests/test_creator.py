from tests.conftest import PREFIX


def create(client, **overrides):
    payload = {"name": "campaign1", "geo": "au", "offer_id": 3749, **overrides}
    return client.post("/api/campaigns", json=payload)


def test_creates_campaign_with_prefix_domain_group_and_source(client, fake):
    response = create(client)

    assert response.status_code == 201
    campaign = fake.campaigns[response.json()["id"]]
    assert campaign["name"] == PREFIX + "campaign1"
    assert campaign["domain_id"] == 7
    assert campaign["group_id"] == 5
    assert campaign["traffic_source_id"] == 9
    assert campaign["alias"]


def test_does_not_duplicate_prefix(client, fake):
    response = create(client, name=PREFIX + "campaign1")

    assert fake.campaigns[response.json()["id"]]["name"] == PREFIX + "campaign1"


def test_creates_geo_redirect_stream_and_offer_stream(client, fake):
    response = create(client, geo="mx, AU")

    geo_stream, offer_stream = sorted(fake.streams.values(), key=lambda s: s["position"])
    assert geo_stream["campaign_id"] == response.json()["id"]
    assert geo_stream["schema"] == "redirect"
    assert geo_stream["action_payload"] == "https://google.com"
    assert geo_stream["filters"] == [{"name": "country", "mode": "accept", "payload": ["MX", "AU"]}]
    assert offer_stream["schema"] == "landings"
    assert fake.shares(offer_stream["id"]) == {3749: 100}


def test_returns_campaign_with_both_streams_saved_locally(client):
    body = create(client).json()

    assert body["created_by_app"] is True
    assert body["geo"] == "AU"
    assert body["url"].startswith("https://tracker.example.com/")
    assert [stream["has_offers_schema"] for stream in body["streams"]] == [False, True]
    assert body["streams"][1]["offers"][0]["share"] == 100
    assert client.get("/api/campaigns").json()[0]["id"] == body["id"]


def test_archives_campaign_when_stream_creation_fails(client, fake):
    fake.fail_stream_creation = True

    response = create(client)

    assert response.status_code == 502
    assert fake.campaigns == {}
    assert len(fake.archived_campaigns) == 1
    assert client.get("/api/campaigns").json() == []


def test_rejects_unknown_offer_before_creating_anything(client, fake):
    response = create(client, offer_id=999)

    assert response.status_code == 404
    assert fake.campaigns == {}


def test_rejects_bad_geo(client, fake):
    for geo in ("", "australia", "A1", ","):
        response = create(client, geo=geo)

        assert response.status_code == 422, geo
        assert isinstance(response.json()["detail"], str)
    assert fake.campaigns == {}


def test_rejects_empty_name(client):
    assert create(client, name="   ").status_code == 422


def test_offer_search_finds_by_name_and_by_id(client):
    by_name = client.get("/api/offers", params={"q": "beauty ro"}).json()
    by_id = client.get("/api/offers", params={"q": "11112"}).json()

    assert [offer["id"] for offer in by_name] == [3749, 3717]
    assert by_id == [{"id": 11112, "name": "Beauty CL"}]
