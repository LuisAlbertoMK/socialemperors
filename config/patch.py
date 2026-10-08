import json

import jsonpatch

with open("./config/game_config_20120826.json", 'r', encoding="utf-8") as original_file:
    original = json.load(original_file)
with open("./config/patched_config.json", 'r', encoding="utf-8") as patched_file:
    patched = json.load(patched_file)

patch = jsonpatch.make_patch(original, patched)

print(str(patch))
