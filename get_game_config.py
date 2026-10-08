import bisect
import json
import os

import jsonpatch

from bundle import CONFIG_DIR, CONFIG_PATCH_DIR, MODS_DIR

with open(os.path.join(CONFIG_DIR, "game_config_20120826.json"), 'r', encoding='utf-8') as config_file:
    __game_config = json.load(config_file)

def remove_duplicate_items():
    items = __game_config["items"]
    seen = set()
    unique_items = []
    num_duplicate = 0

    for item in items:
        item_id = item["id"]
        if item_id in seen:
            num_duplicate += 1
            continue
        seen.add(item_id)
        unique_items.append(item)

    if num_duplicate:
        items[:] = unique_items
        print(f" * Removed {num_duplicate} duplicate items from config patches")

def apply_config_patch(filename):
    with open(filename, 'r', encoding='utf-8') as patch_file:
        patch = json.load(patch_file)
    jsonpatch.apply_patch(__game_config, patch, in_place=True)

def patch_game_config():

    # Apply patches

    for patch_file in os.listdir(CONFIG_PATCH_DIR):
        if patch_file.endswith(".json"):
            f = os.path.join(CONFIG_PATCH_DIR, patch_file)
            apply_config_patch(f)
            patch = patch_file.replace(".json", "")
            print(" * Patch applied:", patch)

    # Apply mods

    if os.path.exists(MODS_DIR + "/mods.txt"):
        with open(MODS_DIR + "/mods.txt", "r", encoding="utf-8") as f:
            lines = f.readlines()

        for line in lines:
            mod = line.strip()
            if mod.startswith("#"):
                continue
            if mod != "":
                # mods.txt documents that the extension is optional, so strip it
                # before building the path: otherwise "x.json" is looked up as
                # "x.json.json" and the mod is skipped in silence.
                mod = mod.replace(".json", "")
                mod_path = f"{MODS_DIR}/{mod}.json"
                if os.path.exists(mod_path):
                    apply_config_patch(mod_path)
                    print(" * Mod applied:", mod)

    remove_duplicate_items()

print (" [+] Applying config patches and mods...")
patch_game_config()

_level_xp_thresholds = [int(lvl["exp_required"]) for lvl in __game_config["levels"]]

def get_game_config() -> dict:
    return __game_config

def game_config() -> dict:
    return get_game_config()

##########
# PLAYER #
##########

def get_xp_from_level(level: int) -> int:
    return __game_config["levels"][int(level)]["exp_required"]

def get_level_from_xp(xp: int) -> int:
    # Binary search over sorted exp thresholds. Returns count of levels
    # with exp_required <= xp (0-based level index for next threshold).
    thresholds = _level_xp_thresholds
    return bisect.bisect_right(thresholds, int(xp))

#########
# ITEMS #
#########

# ID

items_dict_id_to_items_index = {int(item["id"]): i for i, item in enumerate(__game_config["items"])}

def get_item_from_id(id: int) -> dict:
    items_index = items_dict_id_to_items_index.get(int(id))
    return __game_config["items"][items_index] if items_index is not None else None

def get_attribute_from_item_id(id: int, attribute_name: str) -> str:
    item = get_item_from_id(id)
    return item[attribute_name] if item and attribute_name in item else None

def get_name_from_item_id(id: int) -> str:
    return get_attribute_from_item_id(id, "name")

# subcat_functional

items_dict_subcat_functional_to_items_index = {int(item["subcat_functional"]): i for i, item in enumerate(__game_config["items"])}

def get_item_from_subcat_functional(subcat_functional: int) -> dict:
    items_index = items_dict_subcat_functional_to_items_index.get(int(subcat_functional))
    return __game_config["items"][items_index] if items_index is not None else None

############
# MISSIONS #
############

missions_dict_id_to_missions_index = {int(item["id"]): i for i, item in enumerate(__game_config["missions"])}

def get_mission_from_id(id: int) -> dict:
    items_index = missions_dict_id_to_missions_index.get(int(id))
    return __game_config["missions"][items_index] if items_index is not None else None

def get_attribute_from_mission_id(id: int, attribute_name: str) -> str:
    mission = get_mission_from_id(id)
    return mission[attribute_name] if mission and attribute_name in mission else None