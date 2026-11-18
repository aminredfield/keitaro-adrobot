"""Клиент Keitaro сам по себе, без приложения."""

import httpx
import pytest

from app.errors import KeitaroError
from app.keitaro import KeitaroClient
from tests.conftest import API_KEY, FakeKeitaro


def make_client(handler, cache_seconds: float = 60) -> KeitaroClient:
    return KeitaroClient(
        "https://keitaro.test",
        API_KEY,
        cache_seconds=cache_seconds,
        transport=httpx.MockTransport(handler),
    )


def test_offer_created_after_first_request_is_found_despite_cache():
    fake = FakeKeitaro()
    client = make_client(fake.handler)
    assert client.find_offer_name(555) is None  # список офферов попал в кэш

    fake.offers[555] = "Fresh offer"

    assert client.find_offer_name(555) == "Fresh offer"


def test_reference_lists_are_cached():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json=[{"id": 1, "name": "Offer"}])

    client = make_client(handler)

    client.list_offers()
    client.list_offers()

    assert len(calls) == 1


def test_network_error_text_does_not_leak():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("could not reach 10.0.0.7:8443 with key secret-value")

    client = make_client(handler)

    with pytest.raises(KeitaroError) as raised:
        client.list_offers()

    assert "ConnectError" in raised.value.message
    assert "10.0.0.7" not in raised.value.message
    assert "secret-value" not in raised.value.message


def test_long_keitaro_error_is_cut_to_one_short_line():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "Stack trace:\n" + "x" * 5000})

    client = make_client(handler)

    with pytest.raises(KeitaroError) as raised:
        client.list_offers()

    assert len(raised.value.message) < 300
    assert "\n" not in raised.value.message


def test_object_instead_of_list_is_reported_as_keitaro_error():
    client = make_client(lambda request: httpx.Response(200, json={"oops": True}))

    with pytest.raises(KeitaroError) as raised:
        client.list_offers()

    assert "неожиданный ответ" in raised.value.message


def test_missing_settings_are_reported_before_any_request():
    client = KeitaroClient("", "")

    with pytest.raises(KeitaroError) as raised:
        client.list_offers()

    assert ".env" in raised.value.message
