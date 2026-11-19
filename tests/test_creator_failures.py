"""Что происходит, когда Keitaro ломается посреди создания кампании."""

from tests.test_creator import create


def test_campaign_stays_in_keitaro_when_only_local_save_fails(client, fake):
    fake.fail_stream_listing = True

    response = create(client)

    assert response.status_code == 502
    campaign_id = next(iter(fake.campaigns))
    assert f"id {campaign_id}" in response.json()["detail"]
    assert fake.archived_campaigns == []
    assert len(fake.streams) == 2


def test_failed_archive_does_not_hide_the_original_error(client, fake):
    fake.fail_stream_creation = True
    fake.fail_archive = True

    response = create(client)

    assert response.status_code == 502
    assert "stream is broken" in response.json()["detail"]


def test_unknown_domain_error_lists_available_domains(client, fake):
    fake.domains = [{"id": 7, "name": "other.example.com"}]

    response = create(client)

    assert response.status_code == 404
    assert "other.example.com" in response.json()["detail"]
    assert fake.campaigns == {}


def test_rejects_name_with_control_characters(client, fake):
    assert create(client, name="camp\naign").status_code == 422
    assert fake.campaigns == {}
