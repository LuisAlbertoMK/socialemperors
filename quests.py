import json
import os

from bundle import QUESTS_DIR

_quest_cache = {}

def get_quest_map(questid):
    if questid in _quest_cache:
        return (_quest_cache[questid], 200)
    file = os.path.join(QUESTS_DIR, str(questid) + ".json")
    if not os.path.exists(file):
        return("", 404)
    with open(file, 'r', encoding='utf-8') as f:
        d = json.load(f)
    _quest_cache[questid] = d
    return(d, 200)
