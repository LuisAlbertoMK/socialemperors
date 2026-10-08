# quest-progress

Answer the question "does the server actually save the player's progress?" for the
four progressions that matter, and fix what it does not.

## What was checked, with evidence

| progression | saved? | evidence |
| --- | --- | --- |
| Territory expansion | **yes** | `CMD_EXPAND` has a branch (`command.py`) that appends the land id and charges `expansion_prices`; the player's own save carries 9 expansions `[13, 8, 14, 9, 7, 12, 17, 19, 18]`. |
| Level-ups | **yes** | `CMD_RT_LEVEL_UP` sets `map["level"]` and pads `map["xp"]` up to that level's minimum; the player's save is at level 40. |
| Conquest | **yes** | `CMD_END_QUEST` advances `privateState.unlockedQuestIndex` with a `max()` (so a replayed result cannot undo it) and applies the gold and xp; the player's save shows `100000009` and 36/36 missions completed and rewarded. |
| **Building upgrades** | **no** | `CMD_UPGRADE = "upgrade"` exists in `constants.py` and `command.py` has **no branch for it**, so it falls into "Unhandled command". And every item the server places is written with `level = 0 # TODO` (four sites), so a building's level never persists: all 396 items in the player's map are level 0. |

## Why the upgrade gap is not implemented yet

Implementing `CMD_UPGRADE` needs its argument shape, and the captured session does
not contain a single `upgrade` command: the player harvested, fought and placed
things, but never upgraded a building. Guessing the arguments would write the wrong
number into a player's save, which is the same trap the collectibles fix avoided by
capturing first.

The upgrade flow may also be partly covered already: the capture does contain
`CMD_SELL` with the reason `UPGR` (four times), which removes the old building, and
the replacement is presumably the following `CMD_BUY`. What is missing either way is
the item's **level**, which the server hardcodes to 0.

## Plan

- [x] T1 Regression tests for the three progressions that do work, so a later change
  cannot silently break them the way the collectibles were broken
  (`tests/test_progress_persistence.py`, 6 tests).
- [x] T2 Record the quest ids the client asks for, which doubles as the evidence for
  whether brand new islands are reachable: `get_quest_map` now writes a capture line
  per island on a cache miss, and for every id the server does not have.
- [ ] T3 Capture a real building upgrade (the user plays with `SE_CAPTURE` on), then
  implement `CMD_UPGRADE` test-first from the captured arguments.
- [ ] T4 Store the real level when placing an item, once the level is known to come
  from the client, instead of the four `level = 0 # TODO` sites.

## Verification plan

- `pytest tests/test_progress_persistence.py` covers expansion (including doing the
  same land twice), level-up (including the xp padding), and conquest (including a
  replayed older result not moving the index backwards).
- The capture extension is verified by requesting an island that exists and one that
  does not, and checking both lines land in the capture file.
- `pytest tests -q` and `ruff check .` stay clean.
