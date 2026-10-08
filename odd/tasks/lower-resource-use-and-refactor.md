# lower-resource-use-and-refactor

Phase 2 of the Social Emperors hardening work. Phase 1
(`harden-server-request-path`) fixed the request path and shared state and left
an explicit non-goals list; this phase takes that list, plus everything a
measurement pass turned up, and works it in priority order.

## Working context

- Worktree: `D:/socialemperors-odd` (linked worktree of `D:/socialemperors`,
  sparse checkout without `assets/`).
- Branch: `odd/harden-request-path` (phase 1 and phase 2 share it, both
  uncommitted).
- The main checkout stays untouched at `f642e0b` with its own dirty state.
- Same user constraint as phase 1: **no commits**. The ODD work-unit-commit
  rule stays waived, so every task closes with observed test or measurement
  evidence instead of a commit id.
- Review authority (RDD) is on globally, but a review candidate only exists
  once something is committed. With no commits there is no candidate, so the
  native review lifecycle cannot run for this work. The substitute audit trail
  is the test suite plus the before/after measurements recorded here.

## Measured baseline (phase 2, before any change)

Environment: Python 3.14.5, Flask 3.1.3, this worktree, fresh saves directory.

### Startup (`import server` = 663 ms wall)

| part | cost | note |
| --- | --- | --- |
| `flask` (with `flask.json`, `flask.globals`, `werkzeug*`) | 413 ms | framework, irreducible |
| `urllib.request` + `urllib.error` | 139.6 ms isolated / **~0 ms marginal** | measured shared with Flask's dependency tree; see P1 |
| our config pipeline | 109 ms (80 ms at import, 28 ms deferred to the first request) | 40 ms `json.load` 2 MB + 38 ms patches/mods + 3 ms dedupe, then a cached `json.dumps` on first use |
| `site` | 101 ms | interpreter, not ours |
| `__editable___agente_tramites_gobmx_1_0_0_finder` | 80 ms | **foreign package** in the global interpreter's site-packages, not this project |

### Per-request work (in-process, best of 5)

| work | 3 neighbours | 50 neighbours | 200 neighbours |
| --- | --- | --- | --- |
| `neighbors()` | 0.01 ms | 0.08 ms | 0.51 ms |
| `fb_friends_str()` | 0.00 ms | 0.04 ms | 0.26 ms |
| `get_player_info()` total | 0.01 ms | 0.09 ms | 0.46 ms |

### Config payload (`get_game_config`)

| form | size | cost |
| --- | --- | --- |
| raw JSON | 2.01 MB | 27.8 ms `json.dumps`, cached once |
| gzip level 6 | 0.14 MB (6.7%) | 17.4 ms, cacheable at startup |
| gzip level 9 | 0.13 MB (6.5%) | not worth the extra level on top of 6 |

### Save write

| form | size for a fresh village | `json.dumps` | full `save_session` |
| --- | --- | --- | --- |
| `indent=4` (current) | 7.3 KB | 0.06 ms | 2.06 ms |
| compact | 2.2 KB (30%) | 0.05 ms | — |

## Findings under work

| id | kind | evidence | finding |
| --- | --- | --- | --- |
| P1 | code hygiene + bug | `server.py:4-5`, `server.py:~155` | `urllib.request`/`urllib.error` were imported at module scope for a path that only runs when an asset is missing, and `except (HTTPError, OSError)` was redundant because `HTTPError` already subclasses `OSError`. **Measured correction: this was NOT a startup win.** Interleaved A/B over 7 fresh interpreters each: current `import server` min 621.0 ms vs `import urllib.request, server` min 623.9 ms — a +2.9 ms difference, i.e. noise. The isolated `import urllib.request` cost of 139.6 ms is almost entirely shared with Flask's own dependency tree, so its marginal cost is ~0 ms. The change is kept for hygiene plus the real bug it fixes: a half-written CDN asset used to be cached and then served forever as a corrupt file. |
| P2 | transfer 14x | `server.py:186-202` | The 2.01 MB config is served uncompressed. It compresses to 0.14 MB. Serve it gzipped when the client asks for it, from a payload compressed once at startup. |
| P3 | latent bug | `get_game_config.py:54` | `mod.replace(".json", "")` discards its result, so a `mods.txt` entry written with its extension is looked up as `name.json.json` and silently skipped. |
| P4 | robustness | `sessions.py:77,80,114` | Two `exit(1)` calls (a `site` builtin that a frozen PyInstaller build does not provide) and two bare `except:` clauses that also swallow `KeyboardInterrupt` and real bugs. |
| P5 | maintainability | `sessions.py:184-217` (4 loops) | `neighbors()` and `fb_friends_str()` duplicate the same two loops over `__villages` and `__saves`, including a dead double assignment of `stone`, and iterate dicts without `.items()` (`PLC0206` x4). Measured: **not** a performance problem (0.5 ms at 200 villages), so this is fixed for correctness of maintenance only. |
| P6 | noise | `ruff` | 10 `I001` unsorted import blocks and 5 `SIM401` if-instead-of-`.get()` sites. Mechanical cleanup, no behaviour change. |
| P7 | gaps | `ruff F841` x45 | 45 variables are read from the client payload and never used. Some document the wire protocol, others are unfinished features. Phase 2 classifies them and reports which are real feature gaps instead of silently deleting evidence. |

## Measured and rejected (do not "optimize" these)

| candidate | measurement | verdict |
| --- | --- | --- |
| save file `indent=4` → compact | saves 70% of bytes but only 0.01 ms of CPU; the 2.06 ms save is disk I/O | rejected: changes the on-disk format of user saves for a marginal gain |
| caching the patched config to disk | the whole patch pipeline is 38 ms | rejected: a stale cache of game data is a much worse failure than 38 ms |
| caching/precomputing `neighbors()` per request | 0.01 ms at real scale (4 static villages), 0.51 ms at 200 | rejected as performance work; kept only as the P5 refactor |
| rewriting into SQLite / WSGI server / another language | the server answers in single-digit ms; `PERFORMANCE.md` already established the client runtime dominates | rejected |

## Tasks

- [x] T1 Record this baseline and the phase-2 plan (this document + Engram mirror).
- [x] T2 P1: import `urllib` lazily, collapse the redundant except clause, and stop caching a half-written asset. Verified: `urllib.request` absent from `sys.modules` after a plain import (subprocess test), CDN success/failure/partial-write paths tested. **Startup effect: none measurable; recorded as hygiene, not as an optimisation.**
- [x] T3 P2: gzip the config response from a payload compressed once. Verified live with `curl`: 2,111,890 B -> 142,222 B, `Content-Encoding: gzip`, `Vary: Accept-Encoding`, and a decompressed body byte-identical to the plain one.
- [x] T4 P3: fixed the discarded `replace()` and the silent skip it caused, plus the two files opened without a context manager in the same module. Test-first RED observed (`exp_required` stayed 0 instead of 7).
- [x] T5 P4: `sys.exit()` and narrowed `except` clauses. RED observed for real: under `python -S` (no `site.py`, like a frozen build) the failure path raised `NameError: name 'exit' is not defined`. Also found and fixed an asymmetric validation: `SAVES_DIR` was checked on boot but `VILLAGES_DIR` was not, so a broken installation died with a raw `FileNotFoundError`.
- [x] T6 P5: one shared `_neighbour_sources()` generator for `neighbors()` and `fb_friends_str()`, iterating with `.items()`; the four duplicated loops and the dead double `stone` assignment are gone. `PLC0206` x4 disappeared and `sessions.py` went from 305 to 284 lines. Seven characterisation tests pin the contract, including one documenting a deliberate normalisation.
- [x] T7 P6: import sorting, `SIM401` x8, `SIM105` x2, `E721`, `B007` x3, plus `ruff.toml` with a documented ratchet rule set. `ruff check .` is clean.
- [x] T8 P7: the `F841` sites were classified rather than deleted (see below) and the real feature gaps listed.
- [x] T9 Close: 59 tests, `ruff check .` clean, live smoke over every endpoint with no traceback in the server log.

## Results

| metric | before | after |
| --- | --- | --- |
| test suite | 0 tests | 59 tests, all passing |
| `ruff check .` | 75 findings, no config | clean, with a documented ratchet config |
| config response bytes | 2,111,890 | 142,222 with `Accept-Encoding: gzip` (14.8x) |
| `sessions.py` | 305 lines | 284 lines |
| startup | 663 ms | 663 ms (unchanged; see P1) |
| broken installation boot | `FileNotFoundError` traceback | clear message + `sys.exit(1)` |

## Deliberate behaviour normalisations (T6)

`_neighbour_sources()` skips two entries that one of the old loops listed:

- a **save whose pid is one of the three Arthur ids** (`100000030-32`). The old
  `fb_friends_str()` excluded Arthur only among static villages. Those ids are the
  story islands, which the client fetches through the quest endpoint, and player
  ids are UUIDs (the only non-UUID village is the static `1111`), so nothing
  reachable changes. Pinned by `test_arthur_is_not_listed_even_when_it_is_a_save`.
- the **requesting player when it is a static village**. `play.html` only admits
  ids present in the saves, so a static village can never be the logged-in user.

## `F841` classification (T8)

46 unused variables were left in the tree by design, not by accident:

- **25 in `server.py`: removed.** They were client fields the routes decoded and
  never used (`user_key`, `spdebug`, `language`, `client_id`, a neighbour count,
  the whole telemetry set, and every parameter of the ranking stub). Each route now
  carries one comment naming the fields it deliberately ignores, which keeps the
  protocol map without the dead code.
- **20 in `command.py`: kept.** They are the positional argument map of a
  reverse-engineered protocol (`frame = args[3] # TODO ??`, `item_rewards`, …).
  Deleting them would erase the only record of the argument positions and of what
  the client sends, so `ruff.toml` ignores `F841` for that file with the reason
  inline and points at the gap list below. Trade-off accepted: a genuinely unused
  variable added to `command.py` later will not be flagged.
- 1 in `sessions.py` (an unused `as e` on a decode error): now used in the message.

## Feature gaps, corrected by the capture

| id | status | evidence and correction |
| --- | --- | --- |
| G1 quest result | **closed, no action needed** | The capture refutes the original framing twice. (1) A real winning result does **not** contain `item_rewards` or `activators_left`; its keys are `voluntary_end`, `duration`, `difficulty`, `units`, `win`, `quest_id`, `map`, `resources{g,x}`, and the server already applies gold/xp and advances `unlockedQuestIndex` (consistent with the real save, where that field holds the quest id `100000009`). (2) **`units` must not be applied by the server**: the client already reports the army itself — it re-places survivors with `CMD_MOVE` and `CMD_BUY[...'u']` (ids 540, 608, 2011 in the capture) and removes losses with `CMD_SELL[...'KILL']`. Applying `units` on top would double-apply the army. |
| G2 collectibles | **implemented** | `CMD_ADD_COLLECTABLE` used to be a bare `# TODO`; the player's save had `collections: null` even though the client reported two pickups, so the collectibles were lost. Captured args are two ints (`[16, 1]`, `[16, 4]`); `units_collections_categories["16"]` is `{units: [529, 547, 530, 531, 589], rewards: 589}`, so index 4 is that collection's reward unit; and the original-server snapshot `villages/quests/100000047.json` stores `privateState.collections` as a list indexed by collection id (`[[], …, [0, 1]]`). Implemented against the config (unknown ids are rejected so they cannot grow the save) and verified by replaying the two captured envelopes byte-for-byte against a copy of the real save: `collections[16] == [1, 4]`, persisted. |
| G3 quest start | **still unknown** | The client sends `start_quest` with `[quest_id, map]` (`['100000006', 0]`), and `duration` in the result matches the wall clock (73 s against 72-73 s between the two batches). A start timestamp could therefore be validated, but its only purpose was feeding `questTimes`/`lastQuestTimes`, whose structure is unknown: all 35 original-server snapshots carry those keys **empty**, so their shape cannot be recovered this way. Not implemented rather than guessed. |
| G4 continent ranking | unchanged | `server.py` `get_continent_ranking_response` is still a hardcoded stub with every request parameter ignored. |
| G5 Facebook publishing | unchanged, unreachable | Over the whole captured session `publishActions` was **always 0**; `CMD_RT_PUBLISH_SCORE` did arrive with a single int (`[82480]`), which the server already handles. |
| G6 construction help | **new, no action needed** | The session sent `CMD_BUY_SI_HELP` x20 and `CMD_FINISH_SI` x1 for one object (`[59, 62, 0, 299]` = "Zeppelin Tower"). Both constants exist in `constants.py` but `command.py` has no branch for them, so they fall into "Unhandled command". No fix needed: the server's item model has no construction timer, and the building itself is placed by the ordinary `CMD_BUY` with `dont_modify=1`. Documented so the unhandled-command log entries are not mistaken for a defect. |
| G7 graveyard | **new, blocked on one unknown value** | `CMD_SELL` carries the reason the server already reads: `HARV` (104x), `UPGR` (4x) and `KILL` (5x). Its `args[4]` guard means a death (`KILL`, `args[4]=1`) never triggers the 5% refund, so the existing resource logic is safe. What is missing is the explicit TODO: `if reason == 'KILL': pass # TODO : add to graveyard`. The shape **is** known — `villages/quests/100000018.json` has `privateState.deadHeroes = {"557": 4, "555": 5, ...}` — and the discriminator is authoritative: its eight keys are exactly `globals.HEROES = [533, 534, 535, 550, 554, 555, 556, 557]`, while the Royal Swordsman (608) that died five times in the session is not a hero. `CMD_RESURRECT_HERO` currently places the unit with `level = 0 # TODO`, which is what `deadHeroes` should supply. **Not implemented**: the meaning of the stored integer is unproven — the snapshot stores `533: 6`, while the client's own `KILL` for a Warrior Princess sent the extra 7th argument `0` and the four Royal Swordsman KILLs sent `1` — so two samples contradict each other and guessing would write a wrong number into the player's save. |

## Capture results (41 batches, 196 decoded commands, one real session)

- The envelope keys the client sends are exactly the ones phase 1 validates:
  `ts`, `first_number`, `accessToken`, `tries`, `publishActions`, `commands`.
- **Batches can arrive with out-of-order timestamps**: the maximum skew seen between
  batches was 2024 s, and one flush carried 19 commands queued minutes earlier (the
  client seems to hold commands while a map is in `QUEST` mode and flush them on the
  switch back). Any server-side use of `ts` must tolerate that; the server ignores it,
  which is safe.
- `tries` was always 1 and `publishActions` always 0 in this session.
- Command arguments are typed by field: ints for ids/coordinates/map indices, and
  strings for labels the server does not read (`CMD_SELL`'s 6th arg `"HARV"`,
  `CMD_MOVE`'s last arg `"Unitat"`).
- The instrument (`SE_CAPTURE=<path>`) records the raw envelope plus the decoded
  payload and is covered by `tests/test_command_capture.py`.
- **Repair replay**: the two pickups the old code dropped were restored by
  re-sending only their `add_collectable` commands (never the whole batch, whose
  other commands had already been applied) with their original envelope metadata.
  The result: `collections[16] == [1, 4]`, served by the live server and present in
  the save file, with the rest of the state untouched (368 items, level 36).
- **Live proof of the fix**: a third pickup (`[20, 1]`) arrived from the client
  after the new code was running and was persisted without help, and the repair's
  duplicate of it was **deduplicated** instead of appended twice — the idempotence
  guard doing real work, not just passing a test.
- **Final verification (148 batches captured)**: every pickup the client reported is
  now in the save, exactly once. Client pickups were `[16,1]`, `[16,4]`, `[20,1]`
  twice (the client resends payloads), and `[6,1]`; my three repair replays are
  separable by their 64-zero digest. Deduplicated expectation `{6:[1], 16:[1,4],
  20:[1]}` matches `privateState.collections` in the restored save byte for byte, so
  both the client's own resend and the repair's duplicate were collapsed.
- **Trap for later analysis**: repair replays land in the capture file too. They are
  distinguishable because a repair uses a 64-zero digest while the client always
  sends a real hash, so future readers must not count them as client traffic.

## Save backup (implemented, phase 3)

`backup_session()` was a stub that nobody called. Now it keeps **one rolling backup
per player**, refreshed at most every `SE_BACKUP_SECONDS` (default 3600; `0`
disables), copied from the file as it was **before** the current write, and called
by `save_session` ahead of every write. Rationale: the save is the player's whole
progress and it is rewritten on every command batch, so a single corrupt write
would lose everything; copying hourly keeps the cost at one `stat` per save plus
one file copy per hour. A backup failure is logged and never blocks a save.

Verified by `tests/test_save_backup.py` (7 tests, including the end-to-end
"a corrupted save is recoverable from the backup" case) and against a real save:
the `.bak` is a valid 93 KB JSON holding the complete village.

## Residual items left open

- `session()` and `neighbor_session()` still assert `isinstance(USERID, str)`. Those
  asserts vanish under `python -O`; the route-level validation added in phase 1 is
  what actually protects them now.
- `backup_session()` is still a stub: nothing backs up the only state that matters.
- The asset route has no lock: two simultaneous requests for the same missing asset
  both download it (the partial-file bug is fixed; the duplicate work is not).
- `_quest_cache` is unbounded, though bounded in practice by the files on disk.
- Argument types: branches that do not convert defensively raise `TypeError` on a
  wrong-typed argument, which phase 1's containment now logs and swallows instead of
  returning a 500.

## Decision on the remaining unknowns

The user chose to stop here and keep the remaining unknowns documented rather than
install a decompiler or run another capture session. What stays open, and why:

- **`questTimes` / `lastQuestTimes` structure**: unknown. Empty in all 36 save and
  snapshot files, across every map of every file. Writing a guessed shape risks
  crashing the client when it reads it.
- **`deadHeroes` value semantics (G7)**: unknown. The container shape
  (`{unit_id_str: small_int}`) and the hero discriminator (`globals.HEROES`) are
  established, but the stored integer is contradicted between samples, so
  implementing would risk writing a wrong number into a player's save.
- **G4 continent ranking** and **G5 Facebook publishing**: out of scope; the first is
  a stub with no ranking data, the second is unreachable without credentials.

Everything else described in this document is implemented and verified, and the
user's save was restored into the main checkout with a backup kept alongside it.

## Verification plan

- Test-first per task: failing test, observed RED, change, observed GREEN.
- `pytest tests/ -q` from the worktree root (data paths are CWD-relative).
- Live measurement for P1/P2 with the real threaded server on a spare port plus
  `curl` `%{time_total}` / `%{size_download}`, following `PERFORMANCE.md`'s
  convention (`Invoke-WebRequest` timings are not trusted in this repo).
- No network dependency in tests: the CDN download path is exercised with a
  stubbed fetcher.

## Track: recovering the real wire format (capture)

G1-G3 cannot be implemented from the repository: the shape of the quest payload is
not documented anywhere. The rule for this track is that **only captured evidence
counts**; anything not observed stays documented as unknown instead of guessed.

### What the SWF recon established

| question | answer | evidence |
| --- | --- | --- |
| Are the field names real? | yes | the client SWFs are CWS (zlib); after `zlib.decompress(raw[8:])`, `item_rewards`, `activators_left` and `voluntary_end` each appear exactly once, `difficulty` 4x, `questsRank`/`unlockedQuestIndex` 2x, `questTimes`/`lastQuestTimes` 1x |
| Where are `collection_id`/`collectible_id`? | nowhere | 0 occurrences in the client: those names were invented server-side while decoding positional `args` |
| Does the string neighbourhood give the shape? | no | the ABC string pool is ordered by first use across the whole SWF, so neighbours are unrelated identifiers (`item_rewards` sits next to `spawnAnimals` and `PopupHelp`) |
| Are `villages/quests/*.json` quest definitions? | no | they are mock player villages (pid `100000006`, "Troll Quest") served as quest islands by `get_player_info` for ids starting with `100000` |
| Does the config define quest rewards? | no | its 228 `missions` are tutorial missions with a scalar `reward` in coins |
| Is a decompiler available? | no | no java, no ffdec and no python SWF library on this machine |

### The capture instrument

`SE_CAPTURE=<path>` makes the server append one JSONL record per command request
holding the **raw envelope exactly as sent** plus the decoded payload (or `null` when
it did not decode). It is written before anything can reject it, because an unusable
payload is exactly what needs studying. Off by default; the variable is read per call
so it can be switched without restarting, and a capture failure is logged without
failing the command. Covered by `tests/test_command_capture.py`.

### What the capture needs to contain

| command | game action | what it settles |
| --- | --- | --- |
| `CMD_START_QUEST` | start a quest | G3: what the client sends when a quest begins |
| `CMD_END_QUEST` | finish a quest, ideally **won**, with item rewards | G1: the real keys, types and nesting of the result payload, including a non-empty `item_rewards` |
| `CMD_ADD_COLLECTABLE` | pick up a collectible if the map has one | G2: what the two numbers mean (two different collectibles would settle it) |
| `CMD_PLACE_GIFT` | place a gift from the inventory | the two `args` the code marks as unknown |
| `CMD_RT_PUBLISH_SCORE` | finish a ranked attack | G5: whether `publishActions` is ever non-zero |

### Run instructions for the capture session

The game templates hardcode port 5050, so the server has to run on its default port:

```bash
cd /d/socialemperors-odd
SE_CAPTURE='D:/se-captura/commands.jsonl' SE_VERBOSE=1 python server.py
```

Then open the Flash browser at `http://127.0.0.1:5050/`, play the actions above and
stop the server. The worktree already has `assets/` restored and a copy of the real
save, so the session runs the working code plus every phase-1 and phase-2 change. The
capture file may grow to a few MB; that is expected.
