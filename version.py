import copy
import random

from engine import timestamp_now

version_name = "alpha 0.05"
version_code = "0.05b"

# Fields the client reads that saves written before 0.05b do not carry. The values
# mirror the original server's own saves (villages/quests/*.json): a missing field is
# not a crash, it is the client quietly showing nothing, which is what made the newer
# clients look "experimental" while older ones seemed to work. Only missing keys are
# filled here; a value the player earned is never overwritten.
_PRIVATE_STATE_DEFAULTS = {
    "achievedUnits": [], "attacksLost": 0, "attacksPack": 0, "attacksReceived": [],
    "attacksWon": 0, "collectionsCompleted": [], "comebackBonusCollected": [],
    "countHack": 0, "deadHeroes": [], "dragonSocialHelp": [], "fakeNeighbors": [],
    "helpMap": [], "honor": 0, "honorPoints": None, "numFriends": 0,
    "receivedAssists": [], "spyings": [], "spyingsPack": 0, "templeStep": [],
    "timeStampMondayBonus": 0, "timeStampTemple": 0, "tsAttacksReset": 0,
    "tsSpyingsReset": 0, "version": 1, "worldChange": 0,
}
_MAP_DEFAULTS = {
    "currentQuestVars": [], "numTradesDone": 0, "resourceAlliesMarket": "n",
    "store": {}, "timestampLastTrade": 0, "unlockedEarlyBuildings": [],
    "warehousedUnits": [], "world_id": 0,
}
_PLAYER_SUMMARY_FIELDS = ("coins", "food", "level", "stone", "wood")


def _fill_missing_save_fields(save: dict) -> bool:
    """Add the fields the client reads that this save predates. Never overwrites."""
    changed = False
    private_state = save["privateState"]
    first_map = save["maps"][0]
    player_info = save["playerInfo"]

    for target, defaults in ((private_state, _PRIVATE_STATE_DEFAULTS),
                             (first_map, _MAP_DEFAULTS)):
        for key, value in defaults.items():
            if key not in target:
                target[key] = copy.deepcopy(value)
                changed = True

    if "maps" not in private_state:
        default_map = player_info.get("default_map", 0)
        names = player_info.get("map_names") or ["My Empire"]
        index = default_map if isinstance(default_map, int) and default_map < len(names) else 0
        private_state["maps"] = [{
            "n": names[index],
            "r": first_map.get("race", "h"),
            "s": 1,
        }]
        changed = True

    for key in _PLAYER_SUMMARY_FIELDS:
        if key not in player_info and key in first_map:
            player_info[key] = first_map[key]
            changed = True

    return changed

def migrate_loaded_save(save: dict) -> bool:

    # discard current version saves
    if save.get("version") == version_code:
        return False
    
    # fix 0.01a saves
    if "version" not in save or save["version"] is None:
        save["version"] = "0.01a"
    
    # 0.01a -> 0.02a
    if save["version"] == "0.01a":
        save["maps"][0]["timestamp"] = timestamp_now()
        save["privateState"]["dartsRandomSeed"] = abs(int((2**16 - 1) * random.random()))
        save["version"] = "0.02a"
        print("   > migrated to 0.02a")
    
    # 0.02a -> 0.03a
    if save["version"] == "0.02a":
        if "arrayAnimals" not in save["privateState"]:
            save["privateState"]["arrayAnimals"] = {} # fix no animal spawning
        if "strategy" not in save["privateState"]:
            save["privateState"]["strategy"] = 8 # fix crash when attacking a player
        if "universAttackWin" not in save["maps"][0]:
            save["maps"][0]["universAttackWin"] = [] # pvp current island progress
        if "questTimes" not in save["maps"][0]:
            save["maps"][0]["questTimes"] = [] # quests
        if "lastQuestTimes" not in save["maps"][0]:
            save["maps"][0]["lastQuestTimes"] = [] # 1.1.5 quests
        save["version"] = "0.03a"
        print("   > migrated to 0.03a")
    
    # 0.03a -> 0.04a
    if save["version"] == "0.03a":
        if "pic" not in save["playerInfo"]:
            save["playerInfo"]["pic"] = ""
        if("survivalVidaTimeStamp" not in save["privateState"]):
            save["privateState"]["survivalVidaTimeStamp"] = []
        if("survivalVidasExtra" not in save["privateState"]):
            save["privateState"]["survivalVidasExtra"] = 0
        if("survivalMaps" not in save["privateState"]):
            save["privateState"]["survivalMaps"] = {
                "100000035": {
                    "ts": 0,
                    "tp": 0
                },
                "100000036": {
                    "ts": 0,
                    "tp": 0
                },
                "100000037": {
                    "ts": 0,
                    "tp": 0
                }
            }
        save["version"] = "0.04a"
        print("   > migrated to 0.04a")

    # 0.04a -> 0.05a
    if save["version"] == "0.04a":
        save["version"] = "0.05a"
        print("   > migrated to 0.05a")

    # 0.05a -> 0.05b: fill in the fields the client reads that older saves lack
    if save["version"] == "0.05a":
        if _fill_missing_save_fields(save):
            print("   > filled the fields the client reads")
        save["version"] = "0.05b"
        print("   > migrated to 0.05b")

    return True