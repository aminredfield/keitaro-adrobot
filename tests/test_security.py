"""Приложение без логина не должно слушаться чужих сайтов и чужих хостов."""

import pytest
from starlette.websockets import WebSocketDisconnect


def test_request_from_foreign_site_is_rejected(client, campaign):
    response = client.post(
        f"/api/campaigns/{campaign['id']}/fetch", headers={"Origin": "https://evil.example"}
    )

    assert response.status_code == 403


def test_request_from_our_own_page_is_allowed(client, campaign):
    response = client.post(
        f"/api/campaigns/{campaign['id']}/fetch", headers={"Origin": "http://testserver"}
    )

    assert response.status_code == 200


def test_request_under_foreign_host_name_is_rejected(client):
    # DNS rebinding: браузер приходит на наш сервер, но под чужим именем
    response = client.get("/api/info", headers={"Host": "evil.example"})

    assert response.status_code == 400


def test_responses_carry_security_headers(client):
    response = client.get("/api/info")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]


def test_api_key_is_never_returned(client):
    assert "test-key" not in client.get("/api/info").text


def test_page_and_its_assets_are_served(client):
    page = client.get("/")

    assert page.status_code == 200
    assert "/static/app.js" in page.text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/styles.css").status_code == 200


def test_stray_websocket_connection_is_refused_without_crashing(client):
    # На том же порту может слушать чужой клиент (например, live reload другого проекта)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/"):
            pass


def test_too_big_id_is_rejected_by_validation(client):
    assert client.post("/api/streams/99999999999999999999/push").status_code == 422
    assert client.get("/api/campaigns/0").status_code == 422
