"""Tests for the command envelope: the boundary between client bytes and game state.

``command.php`` receives ``<64-char digest>;<json payload>``. Everything about
that envelope is client-controlled, so malformed input must be rejected as JSON
and a malformed *command inside* a valid envelope must not take down the batch.
"""

import json

import sessions
from constants import Constant

BASE = "/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires"
COMMAND_URL = f"{BASE}/command.php"

FULL_PARAMS = {"user_key": "k", "client_id": "c", "language": "es"}


def envelope(commands, **overrides):
    """Build a well-formed client envelope carrying the given commands."""
    payload = {
        "ts": 0,
        "first_number": 0,
        "accessToken": "token",
        "tries": 0,
        "publishActions": 0,
        "commands": commands,
    }
    payload.update(overrides)
    return "0" * 64 + ";" + json.dumps(payload)


def post_envelope(client, userid, data, **extra):
    payload = {"USERID": userid, "data": data}
    payload.update(extra)
    return client.post(COMMAND_URL, data=payload)


def test_valid_envelope_is_accepted_without_the_optional_parameters(client, user):
    """Only USERID and data matter; the other protocol fields are optional."""
    response = post_envelope(
        client,
        user,
        envelope([{"cmd": Constant.CMD_GAME_STATUS, "args": ["ok"]}]),
    )

    assert response.status_code == 200
    assert response.get_json() == {"result": "success"}


def test_envelope_without_separator_is_rejected_as_json(client, user):
    response = post_envelope(client, user, "x" * 100, **FULL_PARAMS)

    assert response.status_code == 400
    assert response.get_json()["result"] == "error"


def test_envelope_with_broken_json_payload_is_rejected_as_json(client, user):
    response = post_envelope(client, user, "0" * 64 + ";{not json", **FULL_PARAMS)

    assert response.status_code == 400
    assert response.headers["Content-Type"].startswith("application/json")


def test_envelope_that_is_not_a_payload_mapping_is_rejected_as_json(client, user):
    response = post_envelope(client, user, "0" * 64 + ";[1, 2, 3]", **FULL_PARAMS)

    assert response.status_code == 400
    assert response.get_json()["result"] == "error"


def test_envelope_without_a_commands_list_is_rejected_as_json(client, user):
    response = post_envelope(
        client, user, "0" * 64 + ";" + json.dumps({"ts": 0}), **FULL_PARAMS
    )

    assert response.status_code == 400
    assert response.get_json()["result"] == "error"


def test_envelope_with_non_list_commands_is_rejected_as_json(client, user):
    response = post_envelope(
        client,
        user,
        envelope(commands="nope"),
        **FULL_PARAMS,
    )

    assert response.status_code == 400
    assert response.get_json()["result"] == "error"


def test_command_from_an_unknown_user_is_rejected_as_json(client):
    response = post_envelope(
        client,
        "00000000-0000-0000-0000-000000000000",
        envelope([{"cmd": Constant.CMD_GAME_STATUS, "args": ["ok"]}]),
        **FULL_PARAMS,
    )

    assert response.status_code == 400
    assert response.get_json()["result"] == "error"


def test_command_after_a_malformed_one_is_still_applied(client, user):
    """Containment must not skip the commands that follow the rejected one."""
    response = post_envelope(
        client,
        user,
        envelope(
            [
                {"cmd": Constant.CMD_BUY, "args": []},
                {"cmd": Constant.CMD_NAME_MAP, "args": ["0", "Renamed"]},
            ]
        ),
        **FULL_PARAMS,
    )

    assert response.status_code == 200
    assert sessions.session(user)["playerInfo"]["map_names"][0] == "Renamed"


def test_command_entry_that_is_not_a_mapping_is_contained(client, user):
    response = post_envelope(client, user, envelope([42]), **FULL_PARAMS)

    assert response.status_code == 200
    assert response.get_json() == {"result": "success"}


def test_malformed_command_does_not_abort_the_rest_of_the_batch(client, user):
    """A command with the wrong argument shape must not fail the whole frame."""
    response = post_envelope(
        client,
        user,
        envelope(
            [
                {"cmd": Constant.CMD_BUY, "args": []},
                {"cmd": Constant.CMD_GAME_STATUS, "args": ["after-failure"]},
            ]
        ),
        **FULL_PARAMS,
    )

    assert response.status_code == 200
    assert response.get_json() == {"result": "success"}
