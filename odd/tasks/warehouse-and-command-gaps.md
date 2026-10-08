# warehouse-and-command-gaps

Answer "make the client versions behave like the supported one" by finding which of
the commands a real client sends the server actually drops, and closing the ones the
evidence supports.

## What the analysis found

The server has 154 command constants and only **42 have a branch** in `command.py`.
Cross-referencing that with the 148-batch capture of a real session (24 distinct
commands actually sent) gives the list that matters, ordered by how often the client
sent it:

| command | sent | real arguments captured | status |
| --- | --- | --- | --- |
| `buy_si_help` | 20x | `[59, 62, 0, 299, 1]` | open: the state exists (an item's 8th element is `{"si": []}`), but what the list holds is unproven |
| `activate` | 18x | `[59, 46, 0, 13, 4]`, `[..., 0]` | open: the last argument is a small state (0-4); the item's 6th element is the level and the server always writes 0 |
| `store_item_frombug` | 5x | `[57, 59, 0, 4]` | **implemented** |
| `sell_stored_item` | 3x | `[299, 0]` | **implemented** |
| `buy_magic` | 2x | `[2, 0, 0]`, `[5, 0, 0]` | open: `privateState.magics` is a list and `mana` a number, and the config has a `magics` section with the costs |
| `finish_si` | 1x | `[59, 62, 0, 299]` | open: same `{"si": []}` state as `buy_si_help` |
| `place_stored_item` | 1x | `[5, 68, 33, 0, 0]` | **implemented** |
| `next_temple_step` | 1x | `["{\"w\":100000}", 2]` | open: `templeStep` / `templeUnit` / `timeStampTemple` exist in the schema |
| `pop_sell` | 1x | `[66, 40, 0, 225, 500]` | open, low value |

The player's save shows the damage for the warehouse in particular: `store` was
`null`, so it had never even been created.

## What was implemented

The three warehouse commands, because their storage shape is proven by the original
server's own saves (`villages/quests/100000023.json` has
`map.store == {"141": 1, "57": 1, ...}`: item id as a string, mapped to how many are
stored):

- `store_item_frombug` removes the item from the map and increments the warehouse.
- `place_stored_item` decrements the warehouse and puts the item back on the map.
- `sell_stored_item` decrements the warehouse **and nothing else**: the client never
  says what the sale paid, and inventing a refund would hand out free resources.

Nine tests in `tests/test_warehouse.py` cover the shape, the counts, the empty cases
and that it survives a reload. The full suite is 231 tests.

## Two things worth flagging

- `CMD_STORE_ITEM` (the *other* way to store an item) writes into
  `privateState.gifts`, not into `store`. `gifts` is what `CMD_PLACE_GIFT` and
  `CMD_SELL_GIFT` read, so this looks like a mis-implementation, but changing it
  would alter the gifts feature, so it is documented rather than touched.
- An item's 7th element is the list of units inside it (a ranch holds six cows:
  `[192, 47, 3, 0, ..., [504,504,504,504,504,504]]`) and the 8th is a dict like
  `{"si": []}`. So the "construction help" commands do have server-side state; the
  earlier note that they needed no action was wrong.

## On 1.1.5 specifically

- Its content is already covered: of its 36 art ids, 20 are not in the base config
  and **all 20 come from four mods that are enabled** (`mod_epicdragons`,
  `mod_extremedragons`, `mod_savagedragons`, `mod_ancientdragons`).
- Its command vocabulary matches the server's: it knows 149 of the 154 constants.
- Its one server-side trace is `version.py`'s comment
  `lastQuestTimes = [] # 1.1.5 quests`: 1.1.5 is the version that introduced per-quest
  times, and that is one of the two gaps still documented as unknown, so playing with
  1.1.5 will show empty quest times.
- Therefore what remains is **runtime behaviour, not data**, and the way to find it is
  the same one that found the collectibles and the warehouse: capture 1.1.5's own
  traffic with `SE_CAPTURE` and fix what it sends.
