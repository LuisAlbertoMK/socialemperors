import contextlib
import copy
import functools
import json
import os
import random
import shutil
import sys
import threading
import time
import uuid

from bundle import SAVES_DIR, VILLAGES_DIR
from constants import Constant
from engine import timestamp_now
from logger import log
from version import migrate_loaded_save, version_code

try:
    import orjson

    _HAS_ORJSON = True
except ImportError:  # local fallback without the native dependency
    orjson = None
    _HAS_ORJSON = False


def _pretty_save_enabled() -> bool:
    return os.environ.get("SE_PRETTY_SAVE", "0") not in ("", "0", "false", "False")


def _dumps_village(village: dict) -> bytes:
    if _HAS_ORJSON and not _pretty_save_enabled():
        return orjson.dumps(village)
    indent = 4 if _pretty_save_enabled() else None
    return json.dumps(village, indent=indent).encode("utf-8")


def _loads_json_bytes(data: bytes):
    if _HAS_ORJSON:
        try:
            return orjson.loads(data)
        except orjson.JSONDecodeError:
            pass
    return json.loads(data.decode("utf-8"))

# from flask_session import SqlAlchemySessionInterface, current_app

__villages = {}  # ALL static neighbors
'''__villages = {
    "USERID_1": {
        "playerInfo": {...},
        "maps": [{...},{...}]
        "privateState": {...}
    },
    "USERID_2": {...}
}'''

__saves = {}  # ALL saved villages
'''__saves = {
    "USERID_1": {
        "playerInfo": {...},
        "maps": [{...},{...}]
        "privateState": {...}
    },
    "USERID_2": {...}
}'''

# One re-entrant lock for all in-memory village state. The dev server runs
# threaded (see server.py) and a command batch is a read-modify-write over the
# very dictionaries save_session serializes. Without this, concurrent requests
# either tear a save file or make json.dump fail with "dictionary changed size
# during iteration". Single global lock on purpose: a local server has no
# throughput problem to solve, and correctness here beats granularity. If the
# server ever needs per-player concurrency, the next step is one lock per
# USERID plus copy-on-write snapshots, not a weaker global lock.
state_lock = threading.RLock()


def synchronized(function):
    """Hold the state lock for a whole call. Re-entrant, so nesting is safe."""
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        with state_lock:
            return function(*args, **kwargs)
    return wrapper


with open(os.path.join(VILLAGES_DIR, "initial.json"), "rb") as f:
    __initial_village = _loads_json_bytes(f.read())

# Load saved villages

# One rolling backup per player, refreshed at most this often (seconds). Set
# SE_BACKUP_SECONDS=0 to disable, or a larger value to back up less often.
BACKUP_INTERVAL_SECONDS = int(os.environ.get("SE_BACKUP_SECONDS", 3600))


@synchronized
def load_saved_villages():
    global __villages
    global __saves
    # Empty in memory
    __villages = {}
    __saves = {}
    # Saves dir check
    if not os.path.exists(SAVES_DIR):
        try:
            print(f"Creating '{SAVES_DIR}' folder...")
            os.mkdir(SAVES_DIR)
        except OSError:
            print(f"Could not create '{SAVES_DIR}' folder.")
            # sys.exit, not exit(): the builtin comes from site.py, which a
            # frozen (PyInstaller) build never executes.
            sys.exit(1)
    if not os.path.isdir(SAVES_DIR):
        print(f"'{SAVES_DIR}' is not a folder... Move the file somewhere else.")
        sys.exit(1)
    # villages/ ships with the app (and is bundled into the frozen build), so a
    # missing one means a broken installation, not a user mistake: say so
    # instead of dying with a bare FileNotFoundError from os.listdir.
    if not os.path.isdir(VILLAGES_DIR):
        print(f"'{VILLAGES_DIR}' is not a folder... The installation is incomplete.")
        sys.exit(1)
    # Static neighbors in /villages
    for file in os.listdir(VILLAGES_DIR):
        if file == "initial.json" or not file.endswith(".json"):
            continue
        print(f" * Loading static neighbour {file}... ", end='')
        with open(os.path.join(VILLAGES_DIR, file), "rb") as vf:
            village = _loads_json_bytes(vf.read())
        if not is_valid_village(village):
            print("Invalid neighbour")
            continue
        USERID = village["playerInfo"]["pid"]
        if str(USERID) in __villages:
            print(f"Ignored: duplicated PID '{USERID}'.")
        else:
            __villages[str(USERID)] = village
            print("Ok.")
    # Saves in /saves. A save that cannot be read, validated or migrated is
    # retried from its rolling .bak before it is given up on: backup_session()
    # has been writing that copy all along, and a backup nobody loads protects
    # nothing.
    for file in os.listdir(SAVES_DIR):
        if not file.endswith(".save.json"):
            continue
        print(f" * Loading save at {file}... ", end='')
        path = os.path.join(SAVES_DIR, file)
        loaded = _load_one_save(path)
        recovered = False
        if loaded is None:
            backup_path = path + ".bak"
            loaded = _load_one_save(backup_path)
            recovered = loaded is not None
            if recovered:
                print(f"Recovered from {os.path.basename(backup_path)}.")
        if loaded is None:
            print("Skipped: no usable save or backup.")
            continue
        save, modified = loaded
        USERID = save["playerInfo"]["pid"]
        try:
            map_name = save["playerInfo"]["map_names"][ save["playerInfo"]["default_map"] ]
        except (KeyError, IndexError, TypeError):
            # Only the log line below needs it; a save must never be dropped
            # because its map name is missing or of the wrong shape.
            map_name = '?'
        print(f"({map_name}) Ok.")
        __saves[str(USERID)] = save
        # Persist a recovered file immediately, so the next restart does not
        # have to recover it again.
        if modified or recovered:
            save_session(USERID)
    

# New village

@synchronized
def new_village() -> str:
    # Generate USERID
    USERID: str = str(uuid.uuid4())
    if USERID in all_userid():
        raise RuntimeError(f"generated duplicate USERID: {USERID}")
    # Copy init
    village = copy.deepcopy(__initial_village)
    # Custom values
    village["version"] = version_code
    village["playerInfo"]["pid"] = USERID
    village["maps"][0]["timestamp"] = timestamp_now()
    village["privateState"]["dartsRandomSeed"] = abs(int((2**16 - 1) * random.random()))
    # Memory saves
    __saves[USERID] = village
    # Generate save file
    save_session(USERID)
    print("Done.")
    return USERID

# Access functions

@synchronized
def all_saves_userid() -> list:
    "Returns a list of the USERID of every saved village."
    return list(__saves.keys())

@synchronized
def all_userid() -> list:
    "Returns a list of the USERID of every village."
    return list(__villages.keys()) + list(__saves.keys())

@synchronized
def save_info(USERID: str) -> dict:
    save = __saves[USERID]
    default_map = save["playerInfo"]["default_map"]
    empire_name = str(save["playerInfo"]["map_names"][default_map])
    xp = save["maps"][default_map]["xp"]
    level = save["maps"][default_map]["level"]
    return{"userid": USERID, "name": empire_name, "xp": xp, "level": level}

@synchronized
def all_saves_info() -> list:
    saves_info = []
    for userid in __saves:
        saves_info.append(save_info(userid))
    return list(saves_info)

@synchronized
def session(USERID: str) -> dict:
    # An explicit raise (not assert) so the guard survives ``python -O``.
    if not isinstance(USERID, str):
        raise TypeError("USERID must be a str")
    return __saves.get(USERID)

@synchronized
def neighbor_session(USERID: str) -> dict:
    if not isinstance(USERID, str):
        raise TypeError("USERID must be a str")
    if USERID in __saves:
        return __saves[USERID]
    if USERID in __villages:
        return __villages[USERID]

# The three Arthur ids are story islands, not players: the client requests them
# through the quest endpoint, so they must never be listed as a neighbour.
_ARTHUR_PIDS = frozenset(str(pid) for pid in (
    Constant.NEIGHBOUR_ARTHUR_GUINEVERE_1,
    Constant.NEIGHBOUR_ARTHUR_GUINEVERE_2,
    Constant.NEIGHBOUR_ARTHUR_GUINEVERE_3,
))


def _neighbour_sources(USERID: str):
    """Yield ``(playerInfo, first map)`` for everyone a client may see.

    Static villages come first, then saved ones, which is the order the client
    already receives. The requesting player is never listed to itself.
    """
    for entry in list(__villages.values()) + list(__saves.values()):
        player_info = entry["playerInfo"]
        pid = str(player_info["pid"])
        if pid == USERID or pid in _ARTHUR_PIDS:
            continue
        yield player_info, entry["maps"][0]


@synchronized
def fb_friends_str(USERID: str) -> list:
    friends = []
    for player_info, _first_map in _neighbour_sources(USERID):
        friends.append({
            "uid": player_info["pid"],
            "pic_square": player_info["pic"] or "/img/profile/1025.png",
        })
    return friends


@synchronized
def neighbors(USERID: str) -> list:
    neighbours = []
    for player_info, first_map in _neighbour_sources(USERID):
        neigh = dict(player_info)
        for resource in ("coins", "xp", "level", "stone", "wood", "food"):
            neigh[resource] = first_map[resource]
        neighbours.append(neigh)
    return neighbours

# Check for valid village
# The reason why this was implemented is to warn the user if a save game from Social Wars was used by accident

def _load_one_save(path: str):
    """Read, validate and migrate one save file.

    Returns ``(save, modified)``, or ``None`` when the file is unusable. The
    loader calls this for the main file and, if that fails, for its ``.bak``, so
    both paths share exactly the same validation rules.
    """
    try:
        with open(path, "rb") as save_file:
            save = _loads_json_bytes(save_file.read())
    except FileNotFoundError:
        return None
    except (OSError, ValueError, UnicodeDecodeError) as error:
        print(f"Unreadable {os.path.basename(path)}: {error}")
        return None
    if not is_valid_village(save):
        print(f"Invalid save {os.path.basename(path)}.")
        return None
    try:
        modified = migrate_loaded_save(save)  # check save version for migration
    except Exception as error:
        # A save that passes is_valid_village but cannot be migrated (an empty
        # maps list reaches maps[0]) must not stop the server from starting:
        # skip it the same way a corrupted file is skipped.
        print(f"Could not migrate {os.path.basename(path)}: {error!r}")
        return None
    return save, modified


def is_valid_village(save: dict):
    if "playerInfo" not in save or "maps" not in save or "privateState" not in save:
        # These are obvious
        return False
    for map in save["maps"]:
        if "oil" in map or "steel" in map:
            return False
        if "stone" not in map or "food" not in map:
            return False
        if "items" not in map:
            return False
        if not isinstance(map["items"], list):
            return False

    return True

# Persistency

@synchronized
def backup_session(USERID: str):
    """Keep one recent copy of the save file, so a bad write stays recoverable.

    The save file is the player's entire progress and it is rewritten on every
    command batch, so one corrupt write would lose everything. One backup per
    player, refreshed at most every SE_BACKUP_SECONDS (default one hour; 0
    disables it), taken from the file as it was *before* the current write.
    """
    if BACKUP_INTERVAL_SECONDS <= 0:
        return
    final_path = os.path.join(SAVES_DIR, f"{USERID}.save.json")
    backup_path = final_path + ".bak"
    if not os.path.exists(final_path):
        return
    try:
        if os.path.exists(backup_path):
            age = time.time() - os.path.getmtime(backup_path)
            if age < BACKUP_INTERVAL_SECONDS:
                return
        shutil.copyfile(final_path, backup_path)
        log(f" * Backed up {os.path.basename(final_path)}")
    except OSError as error:
        # Not being able to back up is bad; refusing to save because of it is
        # worse, so this never propagates.
        print(f"[WARN] could not back up {final_path}: {error!r}")


@synchronized
def save_session(USERID: str):
    file = f"{USERID}.save.json"
    log(f" * Saving village at {file}... ", end='')
    village = session(USERID)
    backup_session(USERID)
    final_path = os.path.join(SAVES_DIR, file)
    # Unique temp name per writer: a fixed "<save>.tmp" collides when two threads
    # (or two server processes) save at once, and Windows refuses to reopen a
    # file that another writer still holds.
    tmp_path = f"{final_path}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        # Compact binary write (orjson 5-10x faster than indent=4). The file
        # stays valid JSON UTF-8, so old pretty saves still load.
        with open(tmp_path, 'wb') as f:
            f.write(_dumps_village(village))
        os.replace(tmp_path, final_path)
    except BaseException:
        # Never leave a partial temp file behind.
        with contextlib.suppress(OSError):
            os.remove(tmp_path)
        raise
    log("Done.")