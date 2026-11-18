"""Сценарии из видео с редактором: fetch, add, push, cancel, remove, bring back, pin."""

import pytest


@pytest.fixture
def stream(client, campaign) -> dict:
    """Поток с офферами сразу после Fetch streams."""
    body = client.post(f"/api/campaigns/{campaign['id']}/fetch").json()
    return body["streams"][1]


def shares(stream: dict) -> dict[int, int]:
    return {offer["offer_id"]: offer["share"] for offer in stream["offers"]}


def binding_id(stream: dict, offer_id: int) -> int:
    return next(offer["id"] for offer in stream["offers"] if offer["offer_id"] == offer_id)


def add(client, stream: dict, offer_id: int):
    return client.post(f"/api/streams/{stream['id']}/offers", json={"offer_id": offer_id})


def remove(client, stream: dict, offer_id: int):
    return client.delete(f"/api/streams/{stream['id']}/offers/{binding_id(stream, offer_id)}")


def restore(client, stream: dict, offer_id: int):
    url = f"/api/streams/{stream['id']}/offers/{binding_id(stream, offer_id)}/restore"
    return client.post(url)


def pin(client, stream: dict, offer_id: int, **body):
    url = f"/api/streams/{stream['id']}/offers/{binding_id(stream, offer_id)}"
    return client.patch(url, json={"pinned": True, **body})


def push(client, stream: dict):
    return client.post(f"/api/streams/{stream['id']}/push")


def test_fetch_shows_offers_only_for_stream_that_has_them(client, campaign):
    body = client.post(f"/api/campaigns/{campaign['id']}/fetch").json()

    redirect_stream, offers_stream = body["streams"]
    assert redirect_stream["offers"] == []
    assert redirect_stream["has_offers_schema"] is False
    assert shares(offers_stream) == {3749: 33, 3717: 33, 11111: 34}
    assert offers_stream["is_dirty"] is False
    assert offers_stream["offers"][0]["offer_name"] == "Beauty RO spin"


def test_fetch_of_unknown_campaign_is_an_error(client):
    assert client.post("/api/campaigns/424242/fetch").status_code == 502


def test_add_rebalances_locally_and_does_not_touch_keitaro(client, fake, stream):
    updated = add(client, stream, 11112).json()

    assert shares(updated) == {3749: 25, 3717: 25, 11111: 25, 11112: 25}
    assert updated["is_dirty"] is True
    assert fake.shares(stream["id"]) == {3749: 33, 3717: 33, 11111: 34}


def test_push_publishes_offers_and_clears_dirty_flag(client, fake, stream):
    add(client, stream, 11112)

    pushed = push(client, stream).json()

    assert pushed["is_dirty"] is False
    assert fake.shares(stream["id"]) == {3749: 25, 3717: 25, 11111: 25, 11112: 25}


def test_cancel_drops_unpublished_offer_and_restores_shares(client, stream):
    add(client, stream, 11112)

    cancelled = client.post(f"/api/streams/{stream['id']}/cancel").json()

    assert shares(cancelled) == {3749: 33, 3717: 33, 11111: 34}
    assert cancelled["is_dirty"] is False


def test_add_rejects_duplicate_and_unknown_offer(client, stream):
    assert add(client, stream, 3749).status_code == 409
    assert add(client, stream, 999).status_code == 404


def test_add_is_not_allowed_for_stream_without_offers(client, campaign):
    body = client.post(f"/api/campaigns/{campaign['id']}/fetch").json()

    assert add(client, body["streams"][0], 3749).status_code == 422


def test_remove_zeroes_share_and_keeps_offer_in_archive_after_push(client, fake, stream):
    removed = remove(client, stream, 3717).json()

    assert shares(removed) == {3749: 50, 11111: 50, 3717: 0}
    assert removed["offers"][-1]["state"] == "removed"
    assert removed["is_dirty"] is True

    pushed = push(client, stream).json()

    assert fake.shares(stream["id"]) == {3749: 50, 11111: 50}
    assert shares(pushed) == {3749: 50, 11111: 50, 3717: 0}
    assert pushed["is_dirty"] is False


def test_bring_back_returns_archived_offer(client, fake, stream):
    remove(client, stream, 3717)
    push(client, stream)

    restored = restore(client, stream, 3717).json()

    assert shares(restored) == {3749: 34, 3717: 33, 11111: 33}
    assert restored["is_dirty"] is True
    push(client, stream)
    assert fake.shares(stream["id"]) == {3749: 34, 3717: 33, 11111: 33}


def test_removing_unpublished_offer_deletes_it_completely(client, stream):
    added = add(client, stream, 11112).json()

    removed = remove(client, added, 11112).json()

    assert 11112 not in shares(removed)
    assert removed["is_dirty"] is True  # доли 34/33/33 отличаются от 33/33/34 в Keitaro


def test_offer_deleted_in_keitaro_becomes_removed_after_fetch(client, fake, campaign, stream):
    fake.streams[stream["id"]]["offers"] = [
        offer for offer in fake.streams[stream["id"]]["offers"] if offer["offer_id"] == 3749
    ]
    fake.streams[stream["id"]]["offers"][0]["share"] = 100

    body = client.post(f"/api/campaigns/{campaign['id']}/fetch").json()
    refreshed = body["streams"][1]

    assert shares(refreshed) == {3749: 100, 3717: 0, 11111: 0}
    assert [offer["state"] for offer in refreshed["offers"]] == ["active", "removed", "removed"]
    assert refreshed["is_dirty"] is False
    assert restore(client, refreshed, 3717).json()["is_dirty"] is True


def test_fetch_discards_unpublished_changes(client, campaign, stream):
    add(client, stream, 11112)

    body = client.post(f"/api/campaigns/{campaign['id']}/fetch").json()

    assert shares(body["streams"][1]) == {3749: 33, 3717: 33, 11111: 34}


def test_pinned_share_survives_rebalancing(client, fake, stream):
    add(client, stream, 11112)  # четыре оффера по 25%
    pinned = pin(client, stream, 3717).json()
    assert shares(pinned)[3717] == 25

    after_remove = remove(client, pinned, 11111).json()

    assert shares(after_remove) == {3749: 38, 3717: 25, 11112: 37, 11111: 0}
    push(client, stream)
    assert fake.shares(stream["id"]) == {3749: 38, 3717: 25, 11112: 37}


def test_pin_with_explicit_share_recalculates_the_rest(client, stream):
    pinned = pin(client, stream, 3749, share=60).json()

    assert shares(pinned) == {3749: 60, 3717: 20, 11111: 20}
    assert next(o for o in pinned["offers"] if o["offer_id"] == 3749)["pinned"] is True


def test_unpin_returns_offer_to_even_split(client, stream):
    pinned = pin(client, stream, 3749, share=60).json()
    url = f"/api/streams/{stream['id']}/offers/{binding_id(pinned, 3749)}"

    unpinned = client.patch(url, json={"pinned": False}).json()

    assert shares(unpinned) == {3749: 34, 3717: 33, 11111: 33}


def test_pin_that_leaves_nothing_for_others_is_rejected_and_rolled_back(client, campaign, stream):
    response = pin(client, stream, 3749, share=100)

    assert response.status_code == 422
    body = client.get(f"/api/campaigns/{campaign['id']}").json()
    assert shares(body["streams"][1]) == {3749: 33, 3717: 33, 11111: 34}
    assert body["streams"][1]["offers"][0]["pinned"] is False


def test_push_is_blocked_when_pinned_shares_do_not_sum_to_hundred(client, fake, stream):
    pinned = pin(client, stream, 3749, share=60).json()
    pinned = pin(client, pinned, 3717).json()  # 60 + 20 закреплены
    remove(client, pinned, 11111)  # свободных офферов не осталось, сумма 80

    response = push(client, stream)

    assert response.status_code == 422
    assert "80%" in response.json()["detail"]
    assert fake.shares(stream["id"]) == {3749: 33, 3717: 33, 11111: 34}


def test_push_fails_loudly_when_keitaro_saved_other_shares(client, fake, stream, monkeypatch):
    add(client, stream, 11112)
    original = fake._offers
    # Keitaro «потерял» один оффер при сохранении
    monkeypatch.setattr(fake, "_offers", lambda stream_id, offers: original(stream_id, offers[:-1]))

    response = push(client, stream)

    assert response.status_code == 502
    assert client.post(f"/api/streams/{stream['id']}/cancel").json()["is_dirty"] is False


def test_wrong_api_key_gives_clear_error(client, fake, campaign, monkeypatch):
    monkeypatch.setattr("tests.conftest.API_KEY", "another-key")

    response = client.post(f"/api/campaigns/{campaign['id']}/fetch")

    assert response.status_code == 502
    assert "API-ключ" in response.json()["detail"]
