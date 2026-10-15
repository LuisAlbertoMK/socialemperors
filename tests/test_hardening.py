"""Hardening contract: the server must reject what it used to silently allow.

- Buying/expanding without funds places nothing (no more clamp-and-keep).
- Out-of-range map indexes answer JSON 400, never an HTML 500.
- Login without fields redirects instead of raising KeyError.
- command.php throttles abusive loops instead of rewriting the save forever.
"""

import json

import command as command_module
import server
import sessions
from constants import Constant
from get_game_config import get_game_config

BASE = "/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires"


def _gold_item_id():
    for item in get_game_config()["items"]:
        try:
            cost = int(item.get("cost", 0) or 0)
        except (TypeError, ValueError):
            continue
        if item.get("cost_type") == "g" and cost > 0:
            return int(item["id"])
    raise AssertionError("no priced gold item in config")


def _envelope(commands):
    payload = {
        "ts": 0,
        "first_number": 0,
        "accessToken": "token",
        "tries": 0,
        "publishActions": 0,
        "commands": commands,
    }
    return "0" * 64 + ";" + json.dumps(payload)


def test_buy_without_funds_places_nothing(user):
    save = sessions.session(user)
    save["maps"][0]["coins"] = 0
    save["playerInfo"]["cash"] = 0
    before = len(save["maps"][0]["items"])
    command_module.do_command(
        user, Constant.CMD_BUY, [_gold_item_id(), 10, 10, 0, 0, 0, 1, "b"]
    )
    assert len(save["maps"][0]["items"]) == before


def test_buy_with_funds_places_item(user):
    save = sessions.session(user)
    save["maps"][0]["coins"] = 10**9
    before = len(save["maps"][0]["items"])
    command_module.do_command(
        user, Constant.CMD_BUY, [_gold_item_id(), 10, 10, 0, 0, 0, 1, "b"]
    )
    assert len(save["maps"][0]["items"]) == before + 1


def test_expand_without_funds_adds_nothing(user):
    save = sessions.session(user)
    save["maps"][0]["coins"] = 0
    save["playerInfo"]["cash"] = 0
    before = list(save["maps"][0]["expansions"])
    command_module.do_command(user, Constant.CMD_EXPAND, ["42", "gold", 0])
    assert save["maps"][0]["expansions"] == before


def test_player_info_bad_map_is_json_400(client, user):
    response = client.post(
        f"{BASE}/get_player_info.php",
        data={"USERID": user, "user": user, "map": 999},
    )
    assert response.status_code == 400
    assert response.is_json


def test_login_without_fields_redirects(client):
    response = client.post("/", data={})
    assert response.status_code == 302


def test_command_throttle_rejects_loops(client, user, monkeypatch):
    monkeypatch.setattr(server, "_CMD_HITS_MAX", 3)
    monkeypatch.setattr(server, "_cmd_hits", {})
    data = {
        "USERID": user,
        "data": _envelope([{"cmd": Constant.CMD_GAME_STATUS, "args": ["ok"]}]),
    }
    for _ in range(3):
        assert client.post(f"{BASE}/command.php", data=data).status_code == 200
    flooded = client.post(f"{BASE}/command.php", data=data)
    assert flooded.status_code == 429
    assert flooded.is_json
