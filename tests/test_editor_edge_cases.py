"""Крайние случаи редактора, найденные на ревью."""

import pytest

from tests.test_editor import add, pin, push, remove, restore, shares


@pytest.fixture
def stream(client, campaign) -> dict:
    body = client.post(f"/api/campaigns/{campaign['id']}/fetch").json()
    return body["streams"][1]


def test_cancel_after_mixed_edits_restores_keitaro_state_and_drops_pins(client, stream):
    added = add(client, stream, 11112).json()
    pinned = pin(client, added, 3749, share=60).json()
    remove(client, pinned, 3717)

    cancelled = client.post(f"/api/streams/{stream['id']}/cancel").json()

    assert shares(cancelled) == {3749: 33, 3717: 33, 11111: 34}
    assert [offer["pinned"] for offer in cancelled["offers"]] == [False, False, False]
    assert cancelled["is_dirty"] is False


def test_removed_pinned_offer_comes_back_unpinned(client, stream):
    pinned = pin(client, stream, 3749, share=60).json()
    removed = remove(client, pinned, 3749).json()
    assert shares(removed) == {3717: 50, 11111: 50, 3749: 0}

    restored = restore(client, removed, 3749).json()

    assert shares(restored) == {3749: 34, 3717: 33, 11111: 33}
    assert not any(offer["pinned"] for offer in restored["offers"])


def test_fetch_keeps_pin_and_takes_shares_from_keitaro(client, campaign, stream):
    pin(client, stream, 3749)

    body = client.post(f"/api/campaigns/{campaign['id']}/fetch").json()
    refreshed = body["streams"][1]

    assert shares(refreshed) == {3749: 33, 3717: 33, 11111: 34}
    assert refreshed["offers"][0]["pinned"] is True


def test_all_offers_can_be_removed_and_pushed(client, fake, stream):
    current = stream
    for offer_id in (3749, 3717, 11111):
        current = remove(client, current, offer_id).json()

    pushed = push(client, stream).json()

    assert fake.shares(stream["id"]) == {}
    assert pushed["is_dirty"] is False
    assert [offer["state"] for offer in pushed["offers"]] == ["removed"] * 3


def test_push_is_refused_when_stream_changed_in_keitaro_after_fetch(client, fake, stream):
    add(client, stream, 11112)
    fake.streams[stream["id"]]["offers"][0]["share"] = 10  # кто-то поправил поток в Keitaro

    response = push(client, stream)

    assert response.status_code == 409
    assert "Fetch" in response.json()["detail"]
    assert 11112 not in fake.shares(stream["id"])


def test_same_offer_in_two_streams_is_edited_independently(client, fake, campaign):
    second = fake.add_stream(
        {
            "campaign_id": campaign["id"],
            "name": "Flow 3",
            "position": 3,
            "schema": "landings",
            "offers": [{"offer_id": 3749, "share": 100, "state": "active"}],
        }
    )
    body = client.post(f"/api/campaigns/{campaign['id']}/fetch").json()

    remove(client, body["streams"][1], 3749)

    refreshed = client.get(f"/api/campaigns/{campaign['id']}").json()
    assert shares(refreshed["streams"][1])[3749] == 0
    assert refreshed["streams"][2]["id"] == second["id"]
    assert shares(refreshed["streams"][2]) == {3749: 100}


def test_offer_without_share_in_keitaro_response_is_read_as_zero(client, fake, campaign, stream):
    del fake.streams[stream["id"]]["offers"][0]["share"]

    response = client.post(f"/api/campaigns/{campaign['id']}/fetch")

    assert response.status_code == 200
    assert shares(response.json()["streams"][1])[3749] == 0


def test_broken_stream_list_from_keitaro_is_a_gateway_error(client, fake, campaign):
    fake.fail_stream_listing = True

    response = client.post(f"/api/campaigns/{campaign['id']}/fetch")

    assert response.status_code == 502
    assert isinstance(response.json()["detail"], str)
