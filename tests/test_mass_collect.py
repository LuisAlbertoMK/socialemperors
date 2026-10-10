"""QoL mods: mass collect (one call credits every producing building).

Mirrors CMD_COLLECT math per building, no readiness invented: the stock
client never sends timestamps the server can trust, and CMD_COLLECT itself
applies without a cooldown check, so this has the same surface as clicking
every building by hand.
"""

import command as command_module
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
