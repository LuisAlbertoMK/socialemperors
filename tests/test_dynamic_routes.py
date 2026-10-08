"""Contract tests for the game's dynamic (PHP-emulating) endpoints.

The Flash client is not defensive: an HTML error page aborts its sync loop
mid-frame. Whatever the client sends, these endpoints must answer within the
game's own protocol: JSON or an empty body, but never an HTML error page.
"""

import gzip
import json

import pytest

BASE = "/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires"

DYNAMIC_ROUTES = [
    ("GET", f"{BASE}/get_game_config.php"),
    ("POST", f"{BASE}/get_player_info.php"),
    ("POST", f"{BASE}/track_game_status.php"),
    ("POST", f"{BASE}/sync_error_track.php"),
    ("POST", f"{BASE}/command.php"),
    ("GET", f"{BASE}/get_continent_ranking.php"),
]

TELEMETRY_ROUTES = [
    f"{BASE}/track_game_status.php",
    f"{BASE}/sync_error_track.php",
]


@pytest.mark.parametrize("method,path", DYNAMIC_ROUTES)
def test_dynamic_route_never_answers_with_an_html_error_page(client, method, path):
    """A client error must come back as JSON, never as Flask's HTML error page."""
    response = client.open(path, method=method, data={})

    assert response.status_code < 400 or response.headers["Content-Type"].startswith(
        "application/json"
    )


@pytest.mark.parametrize("path", TELEMETRY_ROUTES)
def test_telemetry_without_parameters_still_returns_an_empty_200(client, path):
    response = client.post(path, data={})

    assert response.status_code == 200
    assert response.get_data() == b""


def test_game_config_serves_json_without_parameters(client):
    response = client.get(f"{BASE}/get_game_config.php")

    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/json")


def test_game_config_is_gzipped_when_the_client_accepts_it(client):
    """2.01 MB of JSON becomes 0.14 MB, which is what the client has to pull."""
    plain = client.get(f"{BASE}/get_game_config.php")
    compressed = client.get(
        f"{BASE}/get_game_config.php", headers={"Accept-Encoding": "gzip"}
    )

    assert compressed.status_code == 200
    assert compressed.headers.get("Content-Encoding") == "gzip"
    assert len(compressed.get_data()) * 5 < len(plain.get_data())
    # Same game data, only encoded differently.
    assert gzip.decompress(compressed.get_data()) == plain.get_data()


def test_game_config_is_identical_for_a_client_that_cannot_gzip(client):
    plain = client.get(f"{BASE}/get_game_config.php")

    assert plain.headers.get("Content-Encoding") is None
    assert json.loads(plain.get_data())["items"]


def test_game_config_response_varies_on_accept_encoding(client):
    """Without Vary, a shared cache could hand gzip bytes to a plain client."""
    for headers in ({}, {"Accept-Encoding": "gzip"}):
        response = client.get(f"{BASE}/get_game_config.php", headers=headers)

        assert "accept-encoding" in response.headers.get("Vary", "").lower()


def test_continent_ranking_without_parameters_returns_json(client):
    response = client.get(f"{BASE}/get_continent_ranking.php")

    assert response.status_code == 200
    assert response.get_json()["world_id"] == 0


def test_command_without_parameters_is_rejected_as_json(client):
    response = client.post(f"{BASE}/command.php", data={})

    assert response.status_code == 400
    assert response.headers["Content-Type"].startswith("application/json")
    assert response.get_json()["result"] == "error"


def test_player_info_returns_protocol_json_for_known_user(client, user):
    response = client.post(
        f"{BASE}/get_player_info.php",
        data={"USERID": user, "user_key": "k", "client_id": "c", "language": "es"},
    )

    assert response.status_code == 200
    assert response.get_json()["result"] == "ok"


def test_player_info_with_unknown_user_is_a_client_error_not_a_crash(client):
    response = client.post(
        f"{BASE}/get_player_info.php",
        data={
            "USERID": "00000000-0000-0000-0000-000000000000",
            "user_key": "k",
            "client_id": "c",
            "language": "es",
        },
    )

    assert response.status_code == 400
    assert response.headers["Content-Type"].startswith("application/json")
    assert response.get_json()["result"] == "error"


def test_player_info_with_unknown_neighbor_is_not_a_crash(client, user):
    response = client.post(
        f"{BASE}/get_player_info.php",
        data={
            "USERID": user,
            "user_key": "k",
            "client_id": "c",
            "language": "es",
            "user": "no-such-neighbour",
            "map": "0",
        },
    )

    assert response.status_code == 400
    assert response.headers["Content-Type"].startswith("application/json")


def test_player_info_tolerates_a_non_numeric_map_parameter(client, user):
    response = client.post(
        f"{BASE}/get_player_info.php",
        data={
            "USERID": user,
            "user_key": "k",
            "client_id": "c",
            "language": "es",
            "user": "1111",
            "map": "not-a-number",
        },
    )

    assert response.status_code < 500
