import json
import traceback

from constants import Constant
from engine import (
    apply_collect,
    apply_collect_xp,
    apply_cost,
    mass_collect_buildings,
    timestamp_now,
)
from get_game_config import (
    get_attribute_from_item_id,
    get_attribute_from_mission_id,
    get_game_config,
    get_item_from_subcat_functional,
    get_level_from_xp,
    get_name_from_item_id,
    get_xp_from_level,
)
from logger import VERBOSE, log
from sessions import save_session, session, synchronized


def _label_item(item_id) -> str:
    """Human-readable item label for logs only; free when VERBOSE is off."""
    if not VERBOSE:
        return ""
    name = get_name_from_item_id(item_id)
    return str(name) if name is not None else str(item_id)


def _label_mission(mission_id) -> str:
    if not VERBOSE:
        return ""
    title = get_attribute_from_mission_id(mission_id, "title")
    return str(title) if title is not None else str(mission_id)


# Ephemeral per-batch item index: O(1) lookups within one command() batch.
# The save format stays a plain list (the client reads it); the index is only
# an accelerator that is verified before use and falls back to a full scan,
# so a stale index can never break the game, only cost one rebuild.
_batch_indexes = None


def _index_key(USERID, town_id):
    return (str(USERID), town_id)


def _ensure_batch_index(USERID, town_id, map_state):
    global _batch_indexes
    if _batch_indexes is None:
        return None
    key = _index_key(USERID, town_id)
    items = map_state.get("items")
    if not isinstance(items, list):
        return None
    entry = _batch_indexes.get(key)
    if entry is not None and entry.get("items") is items:
        return entry
    by_id_xyz = {}
    by_xy = {}
    for idx, item in enumerate(items):
        try:
            iid, ix, iy = item[0], item[1], item[2]
        except (IndexError, TypeError):
            continue
        if (iid, ix, iy) not in by_id_xyz:
            by_id_xyz[(iid, ix, iy)] = idx
        if (ix, iy) not in by_xy:
            by_xy[(ix, iy)] = idx
    entry = {"by_id_xyz": by_id_xyz, "by_xy": by_xy, "items": items}
    _batch_indexes[key] = entry
    return entry


def _index_invalidate(USERID, town_id):
    global _batch_indexes
    if _batch_indexes is None:
        return
    _batch_indexes.pop(_index_key(USERID, town_id), None)


def _scan_idx(items, iid, x, y):
    for idx, item in enumerate(items):
        try:
            if item[0] == iid and item[1] == x and item[2] == y:
                return idx
        except (IndexError, TypeError):
            continue
    return None


def _scan_xy(items, x, y):
    for idx, item in enumerate(items):
        try:
            if item[1] == x and item[2] == y:
                return idx
        except (IndexError, TypeError):
            continue
    return None


def _find_idx(USERID, town_id, map_state, iid, x, y):
    items = map_state.get("items")
    if not isinstance(items, list):
        return None
    entry = _ensure_batch_index(USERID, town_id, map_state)
    if entry is not None:
        idx = entry["by_id_xyz"].get((iid, x, y))
        if idx is not None and 0 <= idx < len(items):
            item = items[idx]
            try:
                if item[0] == iid and item[1] == x and item[2] == y:
                    return idx
            except (IndexError, TypeError):
                pass
    return _scan_idx(items, iid, x, y)


def _find_xy(USERID, town_id, map_state, x, y):
    items = map_state.get("items")
    if not isinstance(items, list):
        return None
    entry = _ensure_batch_index(USERID, town_id, map_state)
    if entry is not None:
        idx = entry["by_xy"].get((x, y))
        if idx is not None and 0 <= idx < len(items):
            item = items[idx]
            try:
                if item[1] == x and item[2] == y:
                    return idx
            except (IndexError, TypeError):
                pass
    return _scan_xy(items, x, y)


def _index_note_move(USERID, town_id, map_state, old_xyz, old_xy, new_xyz, new_xy, idx):
    global _batch_indexes
    if _batch_indexes is None:
        return
    entry = _batch_indexes.get(_index_key(USERID, town_id))
    if entry is None or entry.get("items") is not map_state.get("items"):
        return
    by_id_xyz = entry["by_id_xyz"]
    by_xy = entry["by_xy"]
    if by_id_xyz.get(old_xyz) == idx:
        del by_id_xyz[old_xyz]
        by_id_xyz.setdefault(new_xyz, idx)
    if by_xy.get(old_xy) == idx:
        del by_xy[old_xy]
        by_xy.setdefault(new_xy, idx)


def _warehouse(map_state: dict) -> dict:
    """The stored-items map, created on demand.

    It lives in the map, not in privateState: the original server's saves carry it
    as ``map.store``, keyed by item id as a string, ``{"141": 1, "57": 1, ...}``
    (see villages/quests/100000023.json), and that is where the client reads it.
    Some of those saves hold an empty list there instead of a dict, so anything
    that is not a dict is replaced.
    """
    store = map_state.get("store")
    if not isinstance(store, dict):
        store = map_state["store"] = {}
    return store


def _take_from_warehouse(store: dict, item_id: int) -> None:
    key = str(item_id)
    remaining = int(store.get(key, 0)) - 1
    if remaining > 0:
        store[key] = remaining
    else:
        store.pop(key, None)


def get_strategy_type(id):
    if id == 8:
        return "Defensive"
    if id == 9:
        return "Mid Defensive"
    if id == 7:
        return "Mid Aggressive"
    if id == 10:
        return "Aggressive"
    return "Unknown Strategy"

@synchronized
def command(USERID, data):
    timestamp = data["ts"]
    first_number = data["first_number"]
    accessToken = data["accessToken"]
    tries = data["tries"]
    publishActions = data["publishActions"]
    commands = data["commands"]

    global _batch_indexes
    _batch_indexes = {}
    try:
        for position, comm in enumerate(commands):
            try:
                cmd = comm["cmd"]
                args = comm["args"]
                do_command(USERID, cmd, args)
            except (IndexError, KeyError, TypeError, ValueError) as error:
                # A command with the wrong argument shape must not abort the whole
                # frame: the client already applied the rest of it locally, so a
                # failed request desyncs it further. Contain it, log it, continue.
                # Rare enough to print even with request logging off.
                print(f"[WARN] command #{position} {comm!r} rejected: {error!r}")
                log(traceback.format_exc())
    finally:
        _batch_indexes = None
    save_session(USERID) # Save session

def _handle_buy(USERID, save, args):
    id = args[0]
    x = args[1]
    y = args[2]
    frame = args[3] # TODO ??
    town_id = args[4]
    bool_dont_modify_resources = bool(args[5]) # 1 if the game "buys" for you, so does not substract whatever the item cost is.
    price_multiplier = args[6]
    type = args[7]
    log("Add", _label_item(id), "at", f"({x},{y})")
    collected_at_timestamp = timestamp_now()
    level = 0 # TODO 
    orientation = 0
    map = save["maps"][town_id]
    if not bool_dont_modify_resources:
        apply_cost(save["playerInfo"], map, id, price_multiplier)
        xp = int(get_attribute_from_item_id(id, "xp"))
        map["xp"] = map["xp"] + xp
    map["items"] += [[id, x, y, orientation, collected_at_timestamp, level]]
    _index_invalidate(USERID, town_id)
    return False

def _handle_complete_tutorial(USERID, save, args):
    tutorial_step = args[0]
    log("Tutorial step", tutorial_step, "reached.")
    if tutorial_step >= 31: # 31 is Dragon choosing. After that, you have some freedom. There's at least until step 45.
        log("Tutorial COMPLETED!")
        save["playerInfo"]["completed_tutorial"] = 1
        save["privateState"]["dragonNestActive"] = 1 
    return False

def _handle_move(USERID, save, args):
    ix = args[0]
    iy = args[1]
    id = args[2]
    newx = args[3]
    newy = args[4]
    frame = args[5]
    town_id = args[6]
    reason = args[7] # "Unitat", "moveTo", "colisio", "MouseUsed"
    log("Move", _label_item(id), "from", f"({ix},{iy})", "to", f"({newx},{newy})")
    map = save["maps"][town_id]
    idx = _find_idx(USERID, town_id, map, id, ix, iy)
    if idx is not None:
        item = map["items"][idx]
        _index_note_move(
            USERID, town_id, map,
            (id, ix, iy), (ix, iy), (id, newx, newy), (newx, newy), idx,
        )
        item[1] = newx
        item[2] = newy
    return False

def _handle_collect(USERID, save, args):
    x = args[0]
    y = args[1]
    town_id = args[2]
    id = args[3]
    num_units_contained_when_harvested = args[4]#TODO does this affect multiplier?
    resource_multiplier = args[5]
    cash_to_substract = args[6]
    log("Collect", _label_item(id))
    map = save["maps"][town_id]
    apply_collect(save["playerInfo"], map, id, resource_multiplier)
    save["playerInfo"]["cash"] = max(save["playerInfo"]["cash"] - cash_to_substract, 0)
    return False

def _handle_mass_collect(USERID, save, args):
    # QoL mod: one call credits every producing building on the map.
    # args: [town_id] or [town_id, resource_multiplier]. Same math as
    # CMD_COLLECT per building, no readiness invented (see engine).
    town_id = args[0] if len(args) > 0 else 0
    try:
        town_id = int(town_id)
    except (TypeError, ValueError):
        town_id = 0
    multiplier = args[1] if len(args) > 1 else 1
    map = save["maps"][town_id]
    count = mass_collect_buildings(save["playerInfo"], map, multiplier)
    log(f"Mass-collected {count} buildings")
    return False

def _handle_sell(USERID, save, args):
    x = args[0]
    y = args[1]
    id = args[2]
    town_id = args[3]
    bool_dont_modify_resources = args[4]
    reason = args[5]
    log("Remove", _label_item(id), "from", f"({x},{y}). Reason: {reason}")
    map = save["maps"][town_id]
    idx = _find_idx(USERID, town_id, map, id, x, y)
    if idx is not None:
        del map["items"][idx]
        _index_invalidate(USERID, town_id)
    if not bool_dont_modify_resources:
        price_multiplier = -0.05
        if get_attribute_from_item_id(id, "cost_type") != "c":
            apply_cost(save["playerInfo"], save["maps"][town_id], id, price_multiplier)
    if reason == 'KILL':
        pass # TODO : add to graveyard
    return False

def _handle_kill(USERID, save, args):
    x = args[0]
    y = args[1]
    id = args[2]
    town_id = args[3]
    type = args[4]
    log("Kill", _label_item(id), "from", f"({x},{y}).")
    map = save["maps"][town_id]
    idx = _find_idx(USERID, town_id, map, id, x, y)
    if idx is not None:
        apply_collect_xp(map, id)
        del map["items"][idx]
        _index_invalidate(USERID, town_id)
    return False

def _handle_complete_mission(USERID, save, args):
    mission_id = args[0]
    skipped_with_cash = bool(args[1])
    log("Complete mission", mission_id, ":", _label_mission(mission_id))
    if skipped_with_cash:
        cash_to_substract = 0 # TODO 
        save["playerInfo"]["cash"] = max(save["playerInfo"]["cash"] - cash_to_substract, 0)
    save["privateState"]["completedMissions"] += [mission_id]
    return False

def _handle_reward_mission(USERID, save, args):
    town_id = args[0]
    mission_id = args[1]
    log("Reward mission", mission_id, ":", _label_mission(mission_id))
    reward = int(get_attribute_from_mission_id(mission_id, "reward")) # gold
    save["maps"][town_id]["coins"] += reward   
    save["privateState"]["rewardedMissions"] += [mission_id]
    return False

def _handle_push_unit(USERID, save, args):
    unit_x = args[0]
    unit_y = args[1]
    unit_id = args[2]
    b_x = args[3]
    b_y = args[4]
    town_id = args[5]
    log("Push", _label_item(unit_id), "to", f"({b_x},{b_y}).")
    map = save["maps"][town_id]
    # Unit into building
    b_idx = _find_xy(USERID, town_id, map, b_x, b_y)
    if b_idx is not None:
        item = map["items"][b_idx]
        if len(item) < 7:
            item += [[]]
        item[6] += [unit_id]
    # Remove unit
    u_idx = _find_idx(USERID, town_id, map, unit_id, unit_x, unit_y)
    if u_idx is not None:
        del map["items"][u_idx]
        _index_invalidate(USERID, town_id)
    return False

def _handle_pop_unit(USERID, save, args):
    b_x = args[0]
    b_y = args[1]
    town_id = args[2]
    unit_id = args[3]
    place_popped_unit = len(args) > 4
    if place_popped_unit:
        unit_x = args[4]
        unit_y = args[5]
        unit_frame = args[6] # unknown use
    log("Pop", _label_item(unit_id), "from", f"({b_x},{b_y}).")
    map = save["maps"][town_id]
    # Remove unit from building
    b_idx = _find_xy(USERID, town_id, map, b_x, b_y)
    if b_idx is not None:
        item = map["items"][b_idx]
        if len(item) >= 7:
            item[6].remove(unit_id)
    if place_popped_unit:
        # Spawn unit outside
        collected_at_timestamp = timestamp_now()
        level = 0 # TODO 
        orientation = 0
        map["items"] += [[unit_id, unit_x, unit_y, orientation, collected_at_timestamp, level]]
        _index_invalidate(USERID, town_id)
    return False

def _handle_rt_level_up(USERID, save, args):
    new_level = args[0]
    log("Level Up!:", new_level)
    map = save["maps"][0] # TODO : xp must be general, since theres no given town_id
    map["level"] = args[0]
    current_xp = map["xp"]
    min_expected_xp = get_xp_from_level(max(0, new_level - 1))
    map["xp"] = max(min_expected_xp, current_xp) # try to fix problems with not counting XP... by keeping up with client-side level counting
    return False

def _handle_rt_publish_score(USERID, save, args):
    new_xp = args[0]
    log("xp set to", new_xp)
    map = save["maps"][0] # TODO : xp must be general, since theres no given town_id
    map["xp"] = new_xp
    map["level"] = get_level_from_xp(new_xp)
    return False

def _handle_expand(USERID, save, args):
    land_id = args[0]
    resource = args[1]
    town_id = int(args[2])
    log("Expansion", land_id, "purchased")
    map = save["maps"][town_id]
    if land_id in map["expansions"]:
        return
    # Substract resources
    expansion_prices = get_game_config()["expansion_prices"]
    exp = expansion_prices[len(map["expansions"]) - 1]
    if resource == "gold":
        to_substract = exp["coins"]
        save["maps"][town_id]["coins"] = max(save["maps"][town_id]["coins"] - to_substract, 0)
    elif resource == "cash":
        to_substract = exp["cash"]
        save["playerInfo"]["cash"] = max(save["playerInfo"]["cash"] - to_substract, 0)
    # Add expansion
    map["expansions"].append(land_id)
    return True

def _handle_name_map(USERID, save, args):
    town_id =int(args[0])
    new_name = args[1]
    log(f"Map name changed to '{new_name}'.")
    save["playerInfo"]["map_names"][town_id] = new_name
    return False

def _handle_exchange_cash(USERID, save, args):
    town_id = args[0]
    log("Exchange cash -> coins.")
    save["playerInfo"]["cash"] = max(save["playerInfo"]["cash"] - 5, 0)#maybe make function for editing resources
    save["maps"][town_id]["coins"] += 2500
    return False

def _handle_store_item(USERID, save, args):
    x = args[0]
    y = args[1]
    town_id = int(args[2])
    item_id = args[3]
    log("Store", _label_item(item_id), "from", f"({x},{y})")
    map = save["maps"][town_id]
    idx = _find_idx(USERID, town_id, map, item_id, x, y)
    if idx is not None:
        del map["items"][idx]
        _index_invalidate(USERID, town_id)
    length = len(save["privateState"]["gifts"])
    if length <= item_id:
        save["privateState"]["gifts"].extend([0] * (item_id - length + 1))
    save["privateState"]["gifts"][item_id] += 1
    return False

def _handle_store_item_frombug(USERID, save, args):
    # The client's other way of storing an item. CMD_STORE_ITEM feeds the gifts
    # list; this one feeds the warehouse, which the original server kept in
    # privateState.store as {item_id: count}.
    x = args[0]
    y = args[1]
    town_id = int(args[2])
    item_id = int(args[3])
    map = save["maps"][town_id]
    idx = _find_idx(USERID, town_id, map, item_id, x, y)
    if idx is not None:
        item = map["items"][idx]
        if isinstance(item, list):
            del map["items"][idx]
            _index_invalidate(USERID, town_id)
            warehouse = _warehouse(map)
            warehouse[str(item_id)] = int(warehouse.get(str(item_id), 0)) + 1
            log("Stored", _label_item(item_id), "in the warehouse")
    return False

def _handle_place_stored_item(USERID, save, args):
    item_id = int(args[0])
    x = args[1]
    y = args[2]
    town_id = int(args[3])
    map = save["maps"][town_id]
    warehouse = _warehouse(map)
    if int(warehouse.get(str(item_id), 0)) > 0:
        _take_from_warehouse(warehouse, item_id)
        map["items"] += [[item_id, x, y, 0, timestamp_now(), 0]]
        _index_invalidate(USERID, town_id)
        log("Placed", _label_item(item_id), "from the warehouse")
    return False

def _handle_sell_stored(USERID, save, args):
    item_id = int(args[0])
    town_id = int(args[1]) if len(args) > 1 else 0
    warehouse = _warehouse(save["maps"][town_id])
    if int(warehouse.get(str(item_id), 0)) > 0:
        # Only the stored count changes. The client did not say what the sale
        # paid, and inventing a refund would hand out resources for free.
        _take_from_warehouse(warehouse, item_id)
        log("Sold", _label_item(item_id), "from the warehouse")
    return False

def _handle_place_gift(USERID, save, args):
    item_id = args[0]
    x = args[1]
    y = args[2]
    town_id = args[3]#unsure, both 3 and 4 seem to stay 0
    args[4]#unknown yet
    log("Add", _label_item(item_id), "at", f"({x},{y})")
    items = save["maps"][town_id]["items"]
    orientation = 0#TODO
    collected_at_timestamp = timestamp_now()
    level = 0
    items += [[item_id, x, y, orientation, collected_at_timestamp, level]]#maybe make function for adding items
    _index_invalidate(USERID, town_id)
    save["privateState"]["gifts"][item_id] -= 1
    if save["privateState"]["gifts"][item_id] == 0: #removes excess zeros at end if necessary
        while(save["privateState"]["gifts"][-1] == 0):
            save["privateState"]["gifts"].pop()  
    return False

def _handle_sell_gift(USERID, save, args):
    item_id = args[0]
    town_id = args[1]
    log("Gift", _label_item(item_id), "sold on town:",town_id)
    gifts = save["privateState"]["gifts"]
    gifts[item_id] -= 1
    if gifts[item_id] == 0: #removes excess zeros at end if necessary
        while(len(gifts) != 0 and gifts[-1] == 0):
            gifts.pop()
    price_multiplier = -0.05
    if get_attribute_from_item_id(item_id, "cost_type") != "c":
        apply_cost(save["playerInfo"], save["maps"][town_id], item_id, price_multiplier)
    return False

def _handle_activate_dragon(USERID, save, args):
    currency = args[0]
    log("Dragon nest activated.")
    if currency == 'c':
        save["playerInfo"]["cash"] = max(int(save["playerInfo"]["cash"] - 50), 0)
    elif currency == 'g':
        map = save["maps"]
        map[0]["coins"] = max(int(map[0]["coins"] - 100000), 0)
    save["privateState"]["dragonNestActive"] = 1
    save["privateState"]["timeStampTakeCare"] = -1 # remove timer if any
    return False

def _handle_desactivate_dragon(USERID, save, args):
    log("Dragon nest deactivated.")
    pState = save["privateState"]
    pState["dragonNestActive"] = 0
    # reset step and dragon numbers
    pState["stepNumber"] = 0
    pState["dragonNumber"] = 0
    pState["timeStampTakeCare"] = -1 # remove timer if any
    return False

def _handle_next_dragon_step(USERID, save, args):
    unknown = args[0]
    log("Dragon step increased.")
    pState = save["privateState"]
    pState["stepNumber"] += 1
    pState["timeStampTakeCare"] = timestamp_now()
    return False

def _handle_next_dragon(USERID, save, args):
    log("Dragon step reset and dragonNumber increased.")
    pState = save["privateState"]
    pState["stepNumber"] = 0
    pState["dragonNumber"] += 1
    pState["timeStampTakeCare"] = -1 # remove timer
    return False

def _handle_dragon_buy_step_cash(USERID, save, args):
    price = args[0]
    log("Buy dragon step with cash.")
    save["playerInfo"]["cash"] = max(int(save["playerInfo"]["cash"] - price), 0)
    save["privateState"]["timeStampTakeCare"] = -1 # remove timer
    return False

def _handle_rider_buy_step_cash(USERID, save, args):
    price = args[0]
    log("Buy rider step with cash.")
    save["playerInfo"]["cash"] = max(int(save["playerInfo"]["cash"] - price), 0)
    save["privateState"]["riderTimeStamp"] = -1 # remove timer
    return False

def _handle_next_rider_step(USERID, save, args):
    log("Rider step increased.")
    pState = save["privateState"]
    pState["riderStepNumber"] += 1
    pState["riderTimeStamp"] = timestamp_now()
    return False

def _handle_select_rider(USERID, save, args):
    number = int(args[0])
    pState = save["privateState"]
    if number == 1 or number == 2 or number == 3:
        pState["riderNumber"] = number
        log("Rider", number, "Selected.")
    else:
        pState["riderNumber"] = 0
        pState["riderStepNumber"] = 0
        pState["riderTimeStamp"] = -1 # remove timer
        log("Rider reset.")
    return False

def _handle_orient(USERID, save, args):
    x = args[0]
    y = args[1]
    new_orientation = args[2]
    town_id = args[3]
    log("Item at", f"({x},{y})", "changed to orientation", new_orientation)
    map = save["maps"][town_id]
    idx = _find_xy(USERID, town_id, map, x, y)
    if idx is not None:
        # Keys (id,x,y) unchanged: index stays valid, no invalidate needed.
        map["items"][idx][3] = new_orientation
    return False

def _handle_monster_buy_step_cash(USERID, save, args):
    price = args[0]
    log("Buy monster step with cash.")
    save["playerInfo"]["cash"] = max(int(save["playerInfo"]["cash"] - price), 0)
    save["privateState"]["timeStampTakeCareMonster"] = -1 # remove timer
    return False

def _handle_activate_monster(USERID, save, args):
    currency = args[0]
    log("Monster nest activated.")
    if currency == 'c':
        save["playerInfo"]["cash"] = max(int(save["playerInfo"]["cash"] - 50), 0)
    elif currency == 'g':
        map = save["maps"]
        map[0]["coins"] = max(int(map[0]["coins"] - 100000), 0)
    save["privateState"]["monsterNestActive"] = 1
    save["privateState"]["timeStampTakeCareMonster"] = -1 # remove timer if any
    return False

def _handle_desactivate_monster(USERID, save, args):
    log("Monster nest deactivated.")
    pState = save["privateState"]
    pState["monsterNestActive"] = 0
    pState["stepMonsterNumber"] = 0
    pState["MonsterNumber"] = 0
    pState["timeStampTakeCareMonster"] = -1 # remove timer if any
    return False

def _handle_next_monster_step(USERID, save, args):
    log("Monster Step increased.")
    pState = save["privateState"]
    pState["stepMonsterNumber"] += 1
    pState["timeStampTakeCareMonster"] = timestamp_now()
    return False

def _handle_next_monster(USERID, save, args):
    log("Monster Step reset and Monster Number increased.")
    pState = save["privateState"]
    pState["stepMonsterNumber"] = 0
    pState["monsterNumber"] += 1
    pState["timeStampTakeCareMonster"] = -1 # remove timer
    return False

def _handle_win_bonus(USERID, save, args):
    coins = args[0]
    town_id = args[1]
    hero = args[2]
    claimId = args[3]
    cash = args[4]

    log("Claiming Win Bonus")
    map = save["maps"][town_id]

    if cash != 0:
        save["playerInfo"]["cash"] = save["playerInfo"]["cash"] + cash
        log("Added " + str(cash) + " Cash to players balance")

    if coins != 0:
        map["coins"] = map["coins"] + coins
        log("Added " + str(coins) + " Gold to players balance")

    if hero != 0:
        length = len(save["privateState"]["gifts"])
        if length <= hero:
            save["privateState"]["gifts"].extend([0] * (hero - length + 1))
        save["privateState"]["gifts"][hero] += 1
        log("Added Hero ID=" + str(hero))

    pState = save["privateState"]
    pState["bonusNextId"] = claimId + 1
    pState["timestampLastBonus"] = timestamp_now()
    return False

def _handle_admin_add_animal(USERID, save, args):
    subcatFunc = str(args[0])
    toBeAdded = int(args[1])
    log("Added", toBeAdded, get_item_from_subcat_functional(subcatFunc)["name"])

    # TODO
    oAnimals: dict = save["privateState"]["arrayAnimals"]
    oAnimals[subcatFunc] = toBeAdded + oAnimals.get(subcatFunc, 0)
    return False

def _handle_graveyard_buy_potions(USERID, save, args):
    # no args
    log("Graveyard buy potion")
    # info from config
    graveyard_potions = get_game_config()["globals"]["GRAVEYARD_POTIONS"]
    amount = graveyard_potions["amount"]
    price_cash = graveyard_potions["price"]["c"]
    # pay
    save["playerInfo"]["cash"] = max(int(save["playerInfo"]["cash"] - price_cash), 0)
    # add potion
    save["privateState"]["potion"] += amount
    return False

def _handle_resurrect_hero(USERID, save, args):
    unit_id = args[0]
    x = args[1]
    y = args[2]
    town_id = args[3]
    bool_used_potion = len(args) > 4 and args[4] == '1'
    log("Resurrect", _label_item(unit_id), "from graveyard")
    # pay
    if bool_used_potion:
        quantity = 1
        save["privateState"]["potion"] = max(int(save["privateState"]["potion"] - quantity), 0)
    else:
        pass # TODO 
    # Place unit
    collected_at_timestamp = timestamp_now()
    level = 0 # TODO 
    orientation = 0
    map = save["maps"][town_id]
    map["items"] += [[unit_id, x, y, orientation, collected_at_timestamp, level]]
    _index_invalidate(USERID, town_id)
    return False

def _handle_buy_super_offer_pack(USERID, save, args):
    town_id = args[0]
    unknown2 = args[1] # this is probably the super offer pack ID?
    items = args[2]
    cash_used = args[3]
    
    map = save["maps"][town_id]

    item_array = items.split(',')
    for item in item_array:
        item_id = int(item)
        length = len(save["privateState"]["gifts"])
        if length <= item_id:
            save["privateState"]["gifts"].extend([0] * (item_id - length + 1))
        save["privateState"]["gifts"][item_id] += 1

    save["playerInfo"]["cash"] = max(save["playerInfo"]["cash"] - cash_used, 0)#maybe make function for editing resources
    log(f"Used {cash_used} cash to buy super offer pack!")
    return False

def _handle_set_strategy(USERID, save, args):
    strategy_type = args[0]
    type_name = get_strategy_type(strategy_type)
    save["privateState"]["strategy"] = strategy_type
    log(f"Set defense strategy type to {type_name}")
    return False

def _handle_start_quest(USERID, save, args):
    quest_id = args[0]
    town_id = args[1]
    log(f"Start quest {quest_id}")
    return False

def _handle_end_quest(USERID, save, args):
    data = json.loads(args[0])
    town_id = data["map"]
    gold_gained = data["resources"]["g"]
    xp_gained = data["resources"]["x"]
    units = data["units"]
    win = data["win"] == 1
    duration_sec = data["duration"]
    voluntary_end = data["voluntary_end"] == 1
    quest_id = int(data["quest_id"])
    item_rewards = data.get("item_rewards")
    activators_left = data.get("activators_left")
    difficulty = data["difficulty"]

    # Resources
    save["maps"][town_id]["coins"] += int(gold_gained)
    save["maps"][town_id]["xp"] += int(xp_gained)

    # Update quests data
    save["privateState"]["unlockedQuestIndex"] = max(quest_id + 1, save["privateState"]["unlockedQuestIndex"], 0)
    # save["privateState"]["questsRank"] = TODO 
    # save["maps"]["questTimes"] [quest_id] = TODO min (... , duration_sec)
    # save["maps"]["lastQuestTimes"] [quest_id] = TODO min (... , duration_sec)

    log(f"Ended quest {quest_id}.")
    return False

def _handle_add_collectable(USERID, save, args):
    collection_id = int(args[0])
    collectible_id = int(args[1])
    # The client reports a unit-collection pickup here and expects the state
    # back on the next full load; without this the collectible is lost.
    # privateState.collections is a list indexed by collection id, each slot
    # holding the collected ids: see villages/quests/100000047.json, a
    # snapshot written by the original server.
    categories = get_game_config().get("units_collections_categories") or {}
    category = categories.get(str(collection_id))
    if category is None or not 0 <= collectible_id < len(category.get("units") or []):
        # Checked against the config so an unknown id cannot grow the save.
        log(f"Ignored unknown collection pickup: {collection_id}/{collectible_id}")
        return
    collections = save["privateState"].get("collections")
    if not isinstance(collections, list):
        collections = save["privateState"]["collections"] = []
    while len(collections) <= collection_id:
        collections.append([])
    slot = collections[collection_id]
    if not isinstance(slot, list):
        slot = collections[collection_id] = []
    if collectible_id not in slot:
        slot.append(collectible_id)
    log(f"Collected {collectible_id} of collection {collection_id}.")
    return True
_COMMAND_HANDLERS = {
    Constant.CMD_BUY: _handle_buy,
    Constant.CMD_COMPLETE_TUTORIAL: _handle_complete_tutorial,
    Constant.CMD_MOVE: _handle_move,
    Constant.CMD_COLLECT: _handle_collect,
    Constant.CMD_MASS_COLLECT: _handle_mass_collect,
    Constant.CMD_SELL: _handle_sell,
    Constant.CMD_KILL: _handle_kill,
    Constant.CMD_COMPLETE_MISSION: _handle_complete_mission,
    Constant.CMD_REWARD_MISSION: _handle_reward_mission,
    Constant.CMD_PUSH_UNIT: _handle_push_unit,
    Constant.CMD_POP_UNIT: _handle_pop_unit,
    Constant.CMD_RT_LEVEL_UP: _handle_rt_level_up,
    Constant.CMD_RT_PUBLISH_SCORE: _handle_rt_publish_score,
    Constant.CMD_EXPAND: _handle_expand,
    Constant.CMD_NAME_MAP: _handle_name_map,
    Constant.CMD_EXCHANGE_CASH: _handle_exchange_cash,
    Constant.CMD_STORE_ITEM: _handle_store_item,
    Constant.CMD_STORE_ITEM_FROMBUG: _handle_store_item_frombug,
    Constant.CMD_PLACE_STORED_ITEM: _handle_place_stored_item,
    Constant.CMD_SELL_STORED: _handle_sell_stored,
    Constant.CMD_PLACE_GIFT: _handle_place_gift,
    Constant.CMD_SELL_GIFT: _handle_sell_gift,
    Constant.CMD_ACTIVATE_DRAGON: _handle_activate_dragon,
    Constant.CMD_DESACTIVATE_DRAGON: _handle_desactivate_dragon,
    Constant.CMD_NEXT_DRAGON_STEP: _handle_next_dragon_step,
    Constant.CMD_NEXT_DRAGON: _handle_next_dragon,
    Constant.CMD_DRAGON_BUY_STEP_CASH: _handle_dragon_buy_step_cash,
    Constant.CMD_RIDER_BUY_STEP_CASH: _handle_rider_buy_step_cash,
    Constant.CMD_NEXT_RIDER_STEP: _handle_next_rider_step,
    Constant.CMD_SELECT_RIDER: _handle_select_rider,
    Constant.CMD_ORIENT: _handle_orient,
    Constant.CMD_MONSTER_BUY_STEP_CASH: _handle_monster_buy_step_cash,
    Constant.CMD_ACTIVATE_MONSTER: _handle_activate_monster,
    Constant.CMD_DESACTIVATE_MONSTER: _handle_desactivate_monster,
    Constant.CMD_NEXT_MONSTER_STEP: _handle_next_monster_step,
    Constant.CMD_NEXT_MONSTER: _handle_next_monster,
    Constant.CMD_WIN_BONUS: _handle_win_bonus,
    Constant.CMD_ADMIN_ADD_ANIMAL: _handle_admin_add_animal,
    Constant.CMD_GRAVEYARD_BUY_POTIONS: _handle_graveyard_buy_potions,
    Constant.CMD_RESURRECT_HERO: _handle_resurrect_hero,
    Constant.CMD_BUY_SUPER_OFFER_PACK: _handle_buy_super_offer_pack,
    Constant.CMD_SET_STRATEGY: _handle_set_strategy,
    Constant.CMD_START_QUEST: _handle_start_quest,
    Constant.CMD_END_QUEST: _handle_end_quest,
    Constant.CMD_ADD_COLLECTABLE: _handle_add_collectable,
}

def do_command(USERID, cmd, args):
    save = session(USERID)
    log(" [+] COMMAND: ", cmd, "(", args, ") -> ", sep='', end='')
    handler = _COMMAND_HANDLERS.get(cmd)
    if handler is None:
        log(f"Unhandled command '{cmd}' -> args", args)
        return
    if handler(USERID, save, args):
        return
