import json
import traceback

from constants import Constant
from engine import apply_collect, apply_collect_xp, apply_cost, timestamp_now
from get_game_config import (
    get_attribute_from_item_id,
    get_attribute_from_mission_id,
    get_game_config,
    get_item_from_subcat_functional,
    get_level_from_xp,
    get_name_from_item_id,
    get_xp_from_level,
)
from logger import log
from sessions import save_session, session, synchronized


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
    save_session(USERID) # Save session

def do_command(USERID, cmd, args):
    save = session(USERID)
    log (" [+] COMMAND: ", cmd, "(", args, ") -> ", sep='', end='')

    if cmd == Constant.CMD_GAME_STATUS:
        log(" ".join(args))

    elif cmd == Constant.CMD_BUY:
        id = args[0]
        x = args[1]
        y = args[2]
        frame = args[3] # TODO ??
        town_id = args[4]
        bool_dont_modify_resources = bool(args[5]) # 1 if the game "buys" for you, so does not substract whatever the item cost is.
        price_multiplier = args[6]
        type = args[7]
        log("Add", str(get_name_from_item_id(id)), "at", f"({x},{y})")
        collected_at_timestamp = timestamp_now()
        level = 0 # TODO 
        orientation = 0
        map = save["maps"][town_id]
        if not bool_dont_modify_resources:
            apply_cost(save["playerInfo"], map, id, price_multiplier)
            xp = int(get_attribute_from_item_id(id, "xp"))
            map["xp"] = map["xp"] + xp
        map["items"] += [[id, x, y, orientation, collected_at_timestamp, level]]
    
    elif cmd == Constant.CMD_COMPLETE_TUTORIAL:
        tutorial_step = args[0]
        log("Tutorial step", tutorial_step, "reached.")
        if tutorial_step >= 31: # 31 is Dragon choosing. After that, you have some freedom. There's at least until step 45.
            log("Tutorial COMPLETED!")
            save["playerInfo"]["completed_tutorial"] = 1
            save["privateState"]["dragonNestActive"] = 1 
    
    elif cmd == Constant.CMD_MOVE:
        ix = args[0]
        iy = args[1]
        id = args[2]
        newx = args[3]
        newy = args[4]
        frame = args[5]
        town_id = args[6]
        reason = args[7] # "Unitat", "moveTo", "colisio", "MouseUsed"
        log("Move", str(get_name_from_item_id(id)), "from", f"({ix},{iy})", "to", f"({newx},{newy})")
        map = save["maps"][town_id]
        for item in map["items"]:
            if item[0] == id and item[1] == ix and item[2] == iy:
                item[1] = newx
                item[2] = newy
                break
    
    elif cmd == Constant.CMD_COLLECT:
        x = args[0]
        y = args[1]
        town_id = args[2]
        id = args[3]
        num_units_contained_when_harvested = args[4]#TODO does this affect multiplier?
        resource_multiplier = args[5]
        cash_to_substract = args[6]
        log("Collect", str(get_name_from_item_id(id)))
        map = save["maps"][town_id]
        apply_collect(save["playerInfo"], map, id, resource_multiplier)
        save["playerInfo"]["cash"] = max(save["playerInfo"]["cash"] - cash_to_substract, 0)
    
    elif cmd == Constant.CMD_SELL:
        x = args[0]
        y = args[1]
        id = args[2]
        town_id = args[3]
        bool_dont_modify_resources = args[4]
        reason = args[5]
        log("Remove", str(get_name_from_item_id(id)), "from", f"({x},{y}). Reason: {reason}")
        map = save["maps"][town_id]
        for idx, item in enumerate(map["items"]):
            if item[0] == id and item[1] == x and item[2] == y:
                del map["items"][idx]
                break
        if not bool_dont_modify_resources:
            price_multiplier = -0.05
            if get_attribute_from_item_id(id, "cost_type") != "c":
                apply_cost(save["playerInfo"], save["maps"][town_id], id, price_multiplier)
        if reason == 'KILL':
            pass # TODO : add to graveyard
    
    elif cmd == Constant.CMD_KILL:
        x = args[0]
        y = args[1]
        id = args[2]
        town_id = args[3]
        type = args[4]
        log("Kill", str(get_name_from_item_id(id)), "from", f"({x},{y}).")
        map = save["maps"][town_id]
        for idx, item in enumerate(map["items"]):
            if item[0] == id and item[1] == x and item[2] == y:
                apply_collect_xp(map, id)
                del map["items"][idx]
                break
    
    elif cmd == Constant.CMD_COMPLETE_MISSION:
        mission_id = args[0]
        skipped_with_cash = bool(args[1])
        log("Complete mission", mission_id, ":", str(get_attribute_from_mission_id(mission_id, "title")))
        if skipped_with_cash:
            cash_to_substract = 0 # TODO 
            save["playerInfo"]["cash"] = max(save["playerInfo"]["cash"] - cash_to_substract, 0)
        save["privateState"]["completedMissions"] += [mission_id]
    
    elif cmd == Constant.CMD_REWARD_MISSION:
        town_id = args[0]
        mission_id = args[1]
        log("Reward mission", mission_id, ":", str(get_attribute_from_mission_id(mission_id, "title")))
        reward = int(get_attribute_from_mission_id(mission_id, "reward")) # gold
        save["maps"][town_id]["coins"] += reward   
        save["privateState"]["rewardedMissions"] += [mission_id]
    
    elif cmd == Constant.CMD_PUSH_UNIT:
        unit_x = args[0]
        unit_y = args[1]
        unit_id = args[2]
        b_x = args[3]
        b_y = args[4]
        town_id = args[5]
        log("Push", str(get_name_from_item_id(unit_id)), "to", f"({b_x},{b_y}).")
        map = save["maps"][town_id]
        # Unit into building
        for item in map["items"]:
            if item[1] == b_x and item[2] == b_y:
                if len(item) < 7:
                    item += [[]]
                item[6] += [unit_id]
                break
        # Remove unit
        for idx, item in enumerate(map["items"]):
            if item[0] == unit_id and item[1] == unit_x and item[2] == unit_y:
                del map["items"][idx]
                break
    
    elif cmd == Constant.CMD_POP_UNIT:
        b_x = args[0]
        b_y = args[1]
        town_id = args[2]
        unit_id = args[3]
        place_popped_unit = len(args) > 4
        if place_popped_unit:
            unit_x = args[4]
            unit_y = args[5]
            unit_frame = args[6] # unknown use
        log("Pop", str(get_name_from_item_id(unit_id)), "from", f"({b_x},{b_y}).")
        map = save["maps"][town_id]
        # Remove unit from building
        for item in map["items"]:
            if item[1] == b_x and item[2] == b_y:
                if len(item) < 7:
                    break
                item[6].remove(unit_id)
                break
        if place_popped_unit:
            # Spawn unit outside
            collected_at_timestamp = timestamp_now()
            level = 0 # TODO 
            orientation = 0
            map["items"] += [[unit_id, unit_x, unit_y, orientation, collected_at_timestamp, level]]
    
    elif cmd == Constant.CMD_RT_LEVEL_UP:
        new_level = args[0]
        log("Level Up!:", new_level)
        map = save["maps"][0] # TODO : xp must be general, since theres no given town_id
        map["level"] = args[0]
        current_xp = map["xp"]
        min_expected_xp = get_xp_from_level(max(0, new_level - 1))
        map["xp"] = max(min_expected_xp, current_xp) # try to fix problems with not counting XP... by keeping up with client-side level counting

    elif cmd == Constant.CMD_RT_PUBLISH_SCORE:
        new_xp = args[0]
        log("xp set to", new_xp)
        map = save["maps"][0] # TODO : xp must be general, since theres no given town_id
        map["xp"] = new_xp
        map["level"] = get_level_from_xp(new_xp)

    elif cmd == Constant.CMD_EXPAND:
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

    elif cmd == Constant.CMD_NAME_MAP:
        town_id =int(args[0])
        new_name = args[1]
        log(f"Map name changed to '{new_name}'.")
        save["playerInfo"]["map_names"][town_id] = new_name

    elif cmd == Constant.CMD_EXCHANGE_CASH:
        town_id = args[0]
        log("Exchange cash -> coins.")
        save["playerInfo"]["cash"] = max(save["playerInfo"]["cash"] - 5, 0)#maybe make function for editing resources
        save["maps"][town_id]["coins"] += 2500

    elif cmd == Constant.CMD_STORE_ITEM:
        x = args[0]
        y = args[1]
        town_id = int(args[2])
        item_id = args[3]
        log("Store", str(get_name_from_item_id(item_id)), "from", f"({x},{y})")
        map = save["maps"][town_id]
        for idx, item in enumerate(map["items"]):
            if item[0] == item_id and item[1] == x and item[2] == y:
                del map["items"][idx]
                break
        length = len(save["privateState"]["gifts"])
        if length <= item_id:
            save["privateState"]["gifts"].extend([0] * (item_id - length + 1))
        save["privateState"]["gifts"][item_id] += 1

    elif cmd == Constant.CMD_STORE_ITEM_FROMBUG:
        # The client's other way of storing an item. CMD_STORE_ITEM feeds the gifts
        # list; this one feeds the warehouse, which the original server kept in
        # privateState.store as {item_id: count}.
        x = args[0]
        y = args[1]
        town_id = int(args[2])
        item_id = int(args[3])
        map = save["maps"][town_id]
        for idx, item in enumerate(map["items"]):
            if isinstance(item, list) and item[0] == item_id and item[1] == x and item[2] == y:
                del map["items"][idx]
                warehouse = _warehouse(map)
                warehouse[str(item_id)] = int(warehouse.get(str(item_id), 0)) + 1
                log("Stored", str(get_name_from_item_id(item_id)), "in the warehouse")
                break

    elif cmd == Constant.CMD_PLACE_STORED_ITEM:
        item_id = int(args[0])
        x = args[1]
        y = args[2]
        town_id = int(args[3])
        map = save["maps"][town_id]
        warehouse = _warehouse(map)
        if int(warehouse.get(str(item_id), 0)) > 0:
            _take_from_warehouse(warehouse, item_id)
            map["items"] += [[item_id, x, y, 0, timestamp_now(), 0]]
            log("Placed", str(get_name_from_item_id(item_id)), "from the warehouse")

    elif cmd == Constant.CMD_SELL_STORED:
        item_id = int(args[0])
        town_id = int(args[1]) if len(args) > 1 else 0
        warehouse = _warehouse(save["maps"][town_id])
        if int(warehouse.get(str(item_id), 0)) > 0:
            # Only the stored count changes. The client did not say what the sale
            # paid, and inventing a refund would hand out resources for free.
            _take_from_warehouse(warehouse, item_id)
            log("Sold", str(get_name_from_item_id(item_id)), "from the warehouse")

    elif cmd == Constant.CMD_PLACE_GIFT:
        item_id = args[0]
        x = args[1]
        y = args[2]
        town_id = args[3]#unsure, both 3 and 4 seem to stay 0
        args[4]#unknown yet
        log("Add", str(get_name_from_item_id(item_id)), "at", f"({x},{y})")
        items = save["maps"][town_id]["items"]
        orientation = 0#TODO
        collected_at_timestamp = timestamp_now()
        level = 0
        items += [[item_id, x, y, orientation, collected_at_timestamp, level]]#maybe make function for adding items
        save["privateState"]["gifts"][item_id] -= 1
        if save["privateState"]["gifts"][item_id] == 0: #removes excess zeros at end if necessary
            while(save["privateState"]["gifts"][-1] == 0):
                save["privateState"]["gifts"].pop()  

    elif cmd == Constant.CMD_SELL_GIFT:
        item_id = args[0]
        town_id = args[1]
        log("Gift", str(get_name_from_item_id(item_id)), "sold on town:",town_id)
        gifts = save["privateState"]["gifts"]
        gifts[item_id] -= 1
        if gifts[item_id] == 0: #removes excess zeros at end if necessary
            while(len(gifts) != 0 and gifts[-1] == 0):
                gifts.pop()
        price_multiplier = -0.05
        if get_attribute_from_item_id(item_id, "cost_type") != "c":
            apply_cost(save["playerInfo"], save["maps"][town_id], item_id, price_multiplier)
    
    elif cmd == Constant.CMD_ACTIVATE_DRAGON:
        currency = args[0]
        log("Dragon nest activated.")
        if currency == 'c':
            save["playerInfo"]["cash"] = max(int(save["playerInfo"]["cash"] - 50), 0)
        elif currency == 'g':
            map = save["maps"]
            map[0]["coins"] = max(int(map[0]["coins"] - 100000), 0)
        save["privateState"]["dragonNestActive"] = 1
        save["privateState"]["timeStampTakeCare"] = -1 # remove timer if any
    
    elif cmd == Constant.CMD_DESACTIVATE_DRAGON:
        log("Dragon nest deactivated.")
        pState = save["privateState"]
        pState["dragonNestActive"] = 0
        # reset step and dragon numbers
        pState["stepNumber"] = 0
        pState["dragonNumber"] = 0
        pState["timeStampTakeCare"] = -1 # remove timer if any

    elif cmd == Constant.CMD_NEXT_DRAGON_STEP:
        unknown = args[0]
        log("Dragon step increased.")
        pState = save["privateState"]
        pState["stepNumber"] += 1
        pState["timeStampTakeCare"] = timestamp_now()

    elif cmd == Constant.CMD_NEXT_DRAGON:
        log("Dragon step reset and dragonNumber increased.")
        pState = save["privateState"]
        pState["stepNumber"] = 0
        pState["dragonNumber"] += 1
        pState["timeStampTakeCare"] = -1 # remove timer

    elif cmd == Constant.CMD_DRAGON_BUY_STEP_CASH:
        price = args[0]
        log("Buy dragon step with cash.")
        save["playerInfo"]["cash"] = max(int(save["playerInfo"]["cash"] - price), 0)
        save["privateState"]["timeStampTakeCare"] = -1 # remove timer

    elif cmd == Constant.CMD_RIDER_BUY_STEP_CASH:
        price = args[0]
        log("Buy rider step with cash.")
        save["playerInfo"]["cash"] = max(int(save["playerInfo"]["cash"] - price), 0)
        save["privateState"]["riderTimeStamp"] = -1 # remove timer

    elif cmd == Constant.CMD_NEXT_RIDER_STEP:
        log("Rider step increased.")
        pState = save["privateState"]
        pState["riderStepNumber"] += 1
        pState["riderTimeStamp"] = timestamp_now()
    
    elif cmd == Constant.CMD_SELECT_RIDER:
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
    
    elif cmd == Constant.CMD_ORIENT:
        x = args[0]
        y = args[1]
        new_orientation = args[2]
        town_id = args[3]
        log("Item at", f"({x},{y})", "changed to orientation", new_orientation)
        map = save["maps"][town_id]
        for item in map["items"]:
            if item[1] == x and item[2] == y:
                item[3] = new_orientation
                break
    
    elif cmd == Constant.CMD_MONSTER_BUY_STEP_CASH:
        price = args[0]
        log("Buy monster step with cash.")
        save["playerInfo"]["cash"] = max(int(save["playerInfo"]["cash"] - price), 0)
        save["privateState"]["timeStampTakeCareMonster"] = -1 # remove timer
    
    elif cmd == Constant.CMD_ACTIVATE_MONSTER:
        currency = args[0]
        log("Monster nest activated.")
        if currency == 'c':
            save["playerInfo"]["cash"] = max(int(save["playerInfo"]["cash"] - 50), 0)
        elif currency == 'g':
            map = save["maps"]
            map[0]["coins"] = max(int(map[0]["coins"] - 100000), 0)
        save["privateState"]["monsterNestActive"] = 1
        save["privateState"]["timeStampTakeCareMonster"] = -1 # remove timer if any
    
    elif cmd == Constant.CMD_DESACTIVATE_MONSTER: # cmd called too late
        log("Monster nest deactivated.")
        pState = save["privateState"]
        pState["monsterNestActive"] = 0
        pState["stepMonsterNumber"] = 0
        pState["MonsterNumber"] = 0
        pState["timeStampTakeCareMonster"] = -1 # remove timer if any


    elif cmd == Constant.CMD_NEXT_MONSTER_STEP:
        log("Monster Step increased.")
        pState = save["privateState"]
        pState["stepMonsterNumber"] += 1
        pState["timeStampTakeCareMonster"] = timestamp_now()

    elif cmd == Constant.CMD_NEXT_MONSTER:
        log("Monster Step reset and Monster Number increased.")
        pState = save["privateState"]
        pState["stepMonsterNumber"] = 0
        pState["monsterNumber"] += 1
        pState["timeStampTakeCareMonster"] = -1 # remove timer

    elif cmd == Constant.CMD_WIN_BONUS:
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

    elif cmd == Constant.CMD_ADMIN_ADD_ANIMAL:
        subcatFunc = str(args[0])
        toBeAdded = int(args[1])
        log("Added", toBeAdded, get_item_from_subcat_functional(subcatFunc)["name"])

        # TODO
        oAnimals: dict = save["privateState"]["arrayAnimals"]
        oAnimals[subcatFunc] = toBeAdded + oAnimals.get(subcatFunc, 0)
    
    elif cmd == Constant.CMD_GRAVEYARD_BUY_POTIONS:
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

    elif cmd == Constant.CMD_RESURRECT_HERO:
        unit_id = args[0]
        x = args[1]
        y = args[2]
        town_id = args[3]
        bool_used_potion = len(args) > 4 and args[4] == '1'
        log("Resurrect", str(get_name_from_item_id(unit_id)), "from graveyard")
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

    elif cmd == Constant.CMD_BUY_SUPER_OFFER_PACK:
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

    elif cmd == Constant.CMD_SET_STRATEGY:
        strategy_type = args[0]
        type_name = get_strategy_type(strategy_type)
        save["privateState"]["strategy"] = strategy_type
        log(f"Set defense strategy type to {type_name}")

    elif cmd == Constant.CMD_START_QUEST:
        quest_id = args[0]
        town_id = args[1]
        log(f"Start quest {quest_id}")

    elif cmd == Constant.CMD_END_QUEST:
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

    elif cmd == Constant.CMD_ADD_COLLECTABLE:
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

    else:
        log(f"Unhandled command '{cmd}' -> args", args)
        return
    
