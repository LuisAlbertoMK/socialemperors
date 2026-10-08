import time

from get_game_config import get_item_from_id


def apply_cost(playerInfo: dict, map: dict, id: int, price_multiplier: int) -> None:
    item = get_item_from_id(id)
    if not item:
        return
    cost = int(price_multiplier * int(item.get("cost", 0) or 0))
    cost_type = item.get("cost_type")
    if cost_type == "w":
        map["wood"] = max(map["wood"] - cost, 0)
    elif cost_type == "g":
        map["coins"] = max(map["coins"] - cost, 0)
    elif cost_type == "c":
        playerInfo["cash"] = max(playerInfo["cash"] - cost, 0)
    elif cost_type == "s":
        map["stone"] = max(map["stone"] - cost, 0)
    elif cost_type == "f":
        map["food"] = max(map["food"] - cost, 0)

def apply_collect(playerInfo: dict, map: dict, id: int, resource_multiplier: int) -> None:
    item = get_item_from_id(id)
    if not item:
        return
    collect = int(resource_multiplier * int(item.get("collect", 0) or 0))
    collect_type = item.get("collect_type")
    collect_xp = int(item.get("collect_xp", 0) or 0)
    map["xp"] = map["xp"] + collect_xp
    if collect_type == "w":
        map["wood"] = map["wood"] + collect
    elif collect_type == "g":
        map["coins"] = map["coins"] + collect
    elif collect_type == "c":
        playerInfo["cash"] = playerInfo["cash"] + collect
    elif collect_type == "s":
        map["stone"] = map["stone"] + collect
    elif collect_type == "f":
        map["food"] = map["food"] + collect

def apply_collect_xp(map: dict, id: int) -> None:
    item = get_item_from_id(id)
    if not item:
        return
    collect_xp = int(item.get("collect_xp", 0) or 0)
    map["xp"] = map["xp"] + collect_xp

def timestamp_now() -> int:
    return int(time.time())