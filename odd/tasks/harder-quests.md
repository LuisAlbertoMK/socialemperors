# harder-quests

Make the quest islands harder, using only units the game already has.

## Why

The request was "new levels, more powerful units like dragons, and more powerful
enemies". Exploration settled what is actually possible:

| question | answer | evidence |
| --- | --- | --- |
| Can new units be added? | **No, not faithfully** | every sprite in `assets/buildingsprites` (956 ids) already has a config entry, and no other asset folder holds unit art without one (`externalized` 0, `images_new` 0, `fx` is effects). A genuinely new unit would need new art, which means SWF work. |
| Are the powerful units already there? | **Yes** | the config has 1,781 items, 303 of them dragons or draggys, up to Dark Horror Ancient Dragon Rider (10,950 life / 285 attack) and the game's own bosses (Chock Nurris 50,000 / 999). The 33 mods add 194 units and change 0 stat fields. |
| Are the islands' garrisons data? | **Yes** | each island is a mock village whose `map.items` are `[item_id, x, y, orientation, timestamp]`, and the id selects the unit from the config. 29 of the 35 islands have units, from ~1,000 to 17,079 total attack. |
| Can new islands be reached? | **Unknown, needs evidence** | the client asks for islands by id (the server 404s a missing file), but how it discovers the ids is not established. Tracked separately. |

So the honest, no-invention version of "more powerful enemies" is: swap the weakest
defenders of each island for elite units that already exist in the config, at the
same coordinates, and let the player opt in.

## Design

- `tools/make_harder_quests.py` reads `villages/quests/*.json` and writes changed
  islands to `villages/quests_hard/`, leaving the originals untouched so the
  preservation baseline stays intact.
- The elite unit is chosen from the island's current garrison strength, using a
  ladder **built from the base config** (never from the patched one, so a hard island
  cannot depend on a mod being enabled) and ordered by attack, which is what makes an
  island hard. In the base config that ladder comes out as Red Bahamut Dragon (60
  attack), Electric Bahamut Dragon Rider (87), Golden Extreme Dragon Rider (150) and
  Supreme Bahamut Dragon (500); islands at or above 10,000 total attack also get one
  of the game's own boss units (Chock Nurris, 50,000 life / 999 attack).
- Only the weakest defenders are replaced, in place, and the difficulty is budgeted
  per island: at most +50% attack and 5x life, at most 25% of the defenders and 12
  per island. A budget is what stops a big island from turning into a wall: without
  the life ceiling, an island with a large attack but fragile units grew 14x.
- The generator refuses to write an island that references a unit the base config
  lacks, instead of producing a broken reference.
- The server serves the hard version only when `SE_HARD_QUESTS=1`, matching the
  project's existing environment switches (`SE_VERBOSE`, `SE_CAPTURE`,
  `SE_BACKUP_SECONDS`). Without the flag, or for an island that has no hard variant,
  the original file is served.

## Steps

- [x] T1 Generator script with the documented ladder and limits.
- [x] T2 Generate the hard islands and record the before/after garrisons: 31 islands
  changed, originals untouched, attack growth between +12% and +50%.
- [x] T3 Server side: `get_quest_map` prefers the hard folder when the flag is on.
- [x] T4 Tests for the generator's invariants and for the serving switch (128 cases).
- [x] T5 Verified over HTTP: island 100000020 served with 21,128 total attack without
  the flag and 23,627 with it, same 77 items and same layout. 216 tests pass.

## Verification plan

- Invariants per island: the item count is unchanged, every coordinate pair is
  unchanged, no scenery item (type `b`) is touched, every id still exists in the
  config, and the total attack and life of the island went up.
- `get_quest_map` serves the hard file with `SE_HARD_QUESTS=1`, the original without
  it, and falls back to the original when a hard file is missing.
- `pytest tests -q` and `ruff check .` stay clean.

## Out of scope

- Brand new units (needs new art / SWF work).
- Brand new islands (blocked on how the client discovers island ids).
- Boosting the player's own dragons: that is a balance change rather than restored
  content, so it is a separate decision.
