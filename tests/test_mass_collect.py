"""QoL mods: mass collect (one call credits every producing building).

Mirrors CMD_COLLECT math per building, no readiness invented: the stock
client never sends timestamps the server can trust, and CMD_COLLECT itself
applies without a cooldown check, so this has the same surface as clicking
every building by hand.
"""

import copy

import command as command_module
import server
import sessions
from constants import Constant
from engine import timestamp_now
from get_game_config import get_item_from_id


def _food(map_state):
    return map_state["food"]


def test_mass_collect_credits_every_producer(tmp_path, user):
    save = sessions.session(user)
    game_map = save["maps"][0]
    before = _food(game_map)

    mill = get_item_from_id(5)
    assert mill is not None and int(mill.get("collect", 0) or 0) > 0
    expected_each = int(mill["collect"])

    game_map["items"] += [
        [5, 10, 10, 0, 0, 0],
        [5, 11, 11, 0, 0, 0],
    ]

    command_module.do_command(user, Constant.CMD_MASS_COLLECT, [0, 1])

    assert _food(sessions.session(user)["maps"][0]) == before + 2 * expected_each


def test_mass_collect_stamps_timestamp(tmp_path, user):
    save = sessions.session(user)
    game_map = save["maps"][0]
    game_map["items"] += [[5, 12, 12, 0, 0, 0]]

    before_ts = timestamp_now()
    command_module.do_command(user, Constant.CMD_MASS_COLLECT, [0])

    stamped = next(
        item for item in sessions.session(user)["maps"][0]["items"]
        if item[0] == 5 and item[1] == 12 and item[2] == 12
    )[4]
    assert stamped >= before_ts


def test_mass_collect_ignores_non_producers(tmp_path, user):
    save = sessions.session(user)
    game_map = save["maps"][0]
    before_food = _food(game_map)
    before_coins = game_map["coins"]

    # House I produces nothing.
    house = get_item_from_id(1)
    assert int(house.get("collect", 0) or 0) == 0
    game_map["items"] += [[1, 13, 13, 0, 0, 0]]

    command_module.do_command(user, Constant.CMD_MASS_COLLECT, [0])

    assert _food(sessions.session(user)["maps"][0]) == before_food
    assert sessions.session(user)["maps"][0]["coins"] == before_coins


def test_collect_all_route_credits_and_saves(client, user):
    save = sessions.session(user)
    game_map = save["maps"][0]
    mill = get_item_from_id(5)
    expected_each = int(mill["collect"])
    before = _food(game_map)
    game_map["items"] += [[5, 14, 14, 0, 0, 0]]

    with client.session_transaction() as flask_session:
        flask_session["USERID"] = user

    response = client.post("/mods/collect_all", data={"town_id": 0})

    assert response.status_code == 200
    assert response.get_json()["result"] == "success"
    assert _food(sessions.session(user)["maps"][0]) == before + expected_each


def test_collect_all_route_requires_login(client):
    response = client.post("/mods/collect_all", data={"town_id": 0})
    assert response.status_code == 401


def test_collect_all_route_defaults_to_the_players_default_map(client, user):
    """The button posts no town_id: the endpoint must use the player's own map."""
    save = sessions.session(user)
    second_map = copy.deepcopy(save["maps"][0])
    second_map["items"] = [[5, 20, 20, 0, 0, 0]]
    second_map["food"] = 0
    save["maps"].append(second_map)
    save["playerInfo"]["default_map"] = 1
    expected_each = int(get_item_from_id(5)["collect"])

    with client.session_transaction() as flask_session:
        flask_session["USERID"] = user

    response = client.post("/mods/collect_all")

    assert response.status_code == 200
    assert response.get_json() == {"result": "success", "town_id": 1}
    assert sessions.session(user)["maps"][1]["food"] == expected_each
    # The default map was credited, not map 0.
    assert sessions.session(user)["maps"][0]["items"] != [[5, 20, 20, 0, 0, 0]]


def test_collect_all_route_rejects_out_of_range_town_id(client, user):
    """An index the save has no map for is a client error, not a 500."""
    with client.session_transaction() as flask_session:
        flask_session["USERID"] = user

    response = client.post("/mods/collect_all", data={"town_id": 99})

    assert response.status_code == 400
    assert response.get_json()["result"] == "error"


def test_play_pages_serve_the_collect_all_button(client, user):
    """The endpoint is useless without the button that calls it, on both pages."""
    with client.session_transaction() as flask_session:
        flask_session["USERID"] = user
        flask_session["GAMEVERSION"] = "SocialEmpires0926bsec.swf"

    for page in ("/play.html", "/ruffle.html"):
        response = client.get(page)
        assert response.status_code == 200, page
        body = response.get_data(as_text=True)
        assert "collectAll(" in body, page
        assert 'id="collectAllStatus"' in body, page


def test_play_pages_use_the_bound_port(client, user, monkeypatch):
    """The SWF URLs follow the configured port, not a hardcoded 5050."""
    with client.session_transaction() as flask_session:
        flask_session["USERID"] = user
        flask_session["GAMEVERSION"] = "SocialEmpires0926bsec.swf"

    default = client.get("/play.html").get_data(as_text=True)
    assert "http://localhost:5050/" in default

    monkeypatch.setattr(server, "port", 7777)
    for page in ("/play.html", "/ruffle.html"):
        body = client.get(page).get_data(as_text=True)
        assert "http://localhost:7777/" in body, page
        assert ":5050" not in body, page


def test_server_port_reads_the_host_header():
    """Behind a proxy the port comes from the Host the client reached."""
    with server.app.test_request_context(headers={"Host": "example.test:8080"}):
        assert server._server_port() == "8080"
    with server.app.test_request_context(headers={"Host": "example.test"}):
        assert server._server_port() == str(server.port)
