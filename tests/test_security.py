"""Приложение без логина не должно слушаться чужих сайтов и чужих хостов."""


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


def test_too_big_id_is_rejected_by_validation(client):
    assert client.post("/api/streams/99999999999999999999/push").status_code == 422
    assert client.get("/api/campaigns/0").status_code == 422
