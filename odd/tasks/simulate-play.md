# simulate-play

Find real gameplay bugs by driving the server through a **simulated play session**
instead of guessing from the source. The client is a Flash SWF that cannot be driven
headlessly without the Flash runtime, so "playing" here means speaking the client's
own protocol: the same routes, the same envelope, the same command batches, in an
order a real player would produce.

## Why

Static reading finds missing branches. It does not find the bugs that only appear
when commands are **combined**: an item placed then harvested, an expansion followed
by a level-up, a warehouse deposit then a sale, a batch where one command fails and
the rest must still be applied. Those are the bugs the player actually feels.

## Isolation (non-negotiable)

The simulation must never touch the developer's real village in `saves/`.

- Set `sessions.SAVES_DIR = tempfile.mkdtemp(...)` **before importing `server`**, the
  same way `tests/conftest.py` does, and `os.chdir(ROOT)` first because
  `bundle.BASE_DIR = "."`.
- Assert at the end that the real save files' mtimes are unchanged; fail loudly if not.
- `app.secret_key` is only set under `if __name__ == '__main__'`, so set it explicitly
  before using the test client.

## Protocol facts (measured from the source, 2026-10-09)

- Route: `POST /dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/command.php`
  form fields: `USERID`, `data`.
- `data` is `<64-char digest>;<json>`; the digest is not verified
  (`server._parse_command_envelope`, `server.py:351-373`).
- Payload keys, all required: `ts`, `first_number`, `accessToken`, `tries`,
  `publishActions`, `commands`. `commands` is `[{"cmd": <wire string>, "args": [...]}]`.
- Wire names are `Constant.CMD_*` values in `constants.py` (snake_case strings).
- `command()` (`command.py:55`) applies every command in the batch, contains
  per-command failures, then saves once.
- A fresh village comes from `sessions.new_village()`.
- Player state read: `POST .../get_player_info.php` with `USERID`.

## What the simulated session must do

A seeded, reproducible script that covers the flows a real player performs, in
coherent order, across many batches:

1. Onboarding: `complete_tutorial`, initial placement (`buy`), `move`, `harvest`.
2. Economy: `sell`, warehouse (`store_item`, `take_from_warehouse`, `place_stored_item`,
   `sell_stored_item`), `expand`, `rt_level_up`, `end_quest`.
3. Combat/meta: `end_attack`, `spy`, gift commands, `activate`, `buy_si_help`,
   `finish_si`, `next_temple_step`, `pop_sell` — the commands a captured real client
   sent that the server has no branch for (see `warehouse-and-command-gaps.md`).
4. Adversarial-but-real: repeated identical commands, out-of-order commands, a batch
   where one command has the wrong argument shape, unknown wire names, empty batches.

## Invariants to check after every batch

- Every response is HTTP 200 and `{"result": "success"}` unless deliberately malformed.
- No unhandled exception reaches the server log.
- Save is still loadable and `version == "0.05b"`.
- Resources (`coins`, `cash`, `xp`, `level`, population) never negative and never NaN.
- Every item is a well-formed record; no duplicate `(id, x, y)` collisions created by
  the server; `level` never decreases.
- Warehouse counts never negative; stored + placed items conserve counts.
- Expansions and unlocked-quest counters are monotonic.
- Re-loading a save from disk yields the same state as the in-memory session.

## Deliverable

- `tools/sim_play.py`: the simulator, runnable as
  `python tools/sim_play.py --sessions N --seed S --json <path>`.
- `tests/test_sim_play.py`: tests for the simulator itself (envelope builder, invariant
  checks catch a deliberately corrupted save, isolation guard).
- A findings report: one entry per distinct failure with the command wire name, its
  args, the observed response/state, and the smallest reproducing batch.

## Tasks

- [x] T1 Write this feature doc and its Engram mirror (before the first source write). Doc written 2026-10-09; mirror pending.
- [x] T2 Build the isolated simulator and its tests; prove it never touches `saves/`. `tools/sim_play.py` (903 lines) + `tests/test_sim_play.py` (6 passed); full suite 257 passed.
- [x] T3 Run the soak (many sessions, many seeds) and collect findings. Soak seed 1 x 5 sessions (1063 batches) + seed 7 x 20 sessions (4251 batches, 4331 commands): 0 failed batches.
- [x] T4 Triage findings: real bug vs simulator artifact; smallest repro per bug. Only finding is the deliberate malformed `move [0]` adversarial case (needs 8 args): contained per-command by design (`command.py:68`), batch survives, save intact. Artifact, no fix needed.
- [ ] T5 Fix confirmed bugs test-first, one work unit per bug. None confirmed; nothing to fix.
- [ ] T6 Re-run the soak and the full suite to prove the fixes. N/A while T5 is empty.
- [ ] T7 Independent verification of the findings and the fix evidence.

## Verification plan

- `python -m pytest tests -q` and `ruff check .` stay green.
- `tests/test_sim_play.py` proves isolation and the invariant detector.
- The soak reproduces every reported bug from a recorded seed, so a fix can be shown
  to remove it and a regression test can pin it.
