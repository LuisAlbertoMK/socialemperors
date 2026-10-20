# Deep audit pass 2 — evidence-based improvement plan

Second pass over the Social Emperors server: disassemble each area, keep only
what measurably improves security, correctness or speed, and prove every change
with tests. Work happens on `audit/deep-pass-2`; `main` stays at `bfd67ab`.

## Results

Four fixes landed, each with a regression test; `main` was never touched.

| Change | Commit | Proof |
|---|---|---|
| The asset fallback cannot write outside its data dir, directory creation is idempotent, and the session cookie is `SameSite=Lax` | `f313a8c` | `tests/test_asset_loader.py`, `tests/test_hardening.py` |
| A corrupt save recovers from `<save>.json.bak` at boot and the recovery is persisted | `d223462` | `tests/test_sessions_robustness.py` |
| The onefile launcher ships `mods/` and `saves/` next to the exe | `7fadedd` | build script review |
| The server binds `127.0.0.1` by default; LAN is an explicit, warned `SE_HOST=0.0.0.0` opt-in | `485c74c` | `tests/test_server_bind.py` |

Verification on the branch tip: **293 tests pass**, `ruff check .` clean, and
`tools/sim_play.py --sessions 5 --seed 1` reports **1063 batches, 0 failed**
(5 expected `command_warning` findings, all the same `move` edge case).

## Quick path

1. Read "Findings ledger" for the ranked list.
2. Each item lands as its own commit with a focused test and a before/after note.
3. Re-run `python -m pytest tests -q` + `ruff check .` after every batch.

## How this pass is measured

| Metric | Baseline (pass 1) | How |
|---|---|---|
| Test suite | 281 passed, ~5 s | `python -m pytest tests -q` |
| Command soak | 1063 batches, 0 failed | `python tools/sim_play.py --sessions 5 --seed 1` |
| Config payload | 2.01 MB raw / 0.14 MB gzip | `get_game_config.php` |
| Request latency | capture with `tools/measure_perf.py` on a live server | curl, warm server |

Security items are measured as "attack attempt blocked by a test", not as
latency: eliminating a write outside the data dir has no ms to report.

## Area A — Backend security (highest priority)

| # | Finding | Evidence | Impact | Fix | Risk |
|---|---|---|---|---|---|
| S1 | Asset loader writes outside `download_assets/assets/` when `path` contains `..` | `server.py:278-306` (`os.path.join(download_dir, path)` then `open(..., "wb")`) | Arbitrary file write with CDN-controlled bytes | Resolve and confine to `download_dir`; 404 on escape | Low |
| S2 | `command.php` authorizes the client-supplied `USERID`, not the session | `server.py:483-503` | Any LAN client can mutate any save (the old default bound `0.0.0.0`) | Loopback by default; LAN is an explicit `SE_HOST=0.0.0.0` opt-in, warned and documented. Session binding was rejected: the cookie-less desktop launcher needs the request `USERID`. | Low — LAN play becomes opt-in |
| S3 | No CSRF protection on cookie-authenticated POSTs | Flask default `SESSION_COOKIE_SAMESITE=None` | A hostile page can trigger `/mods/collect_all` | `SESSION_COOKIE_SAMESITE="Lax"` | Low (SWF is same-origin; desktop launcher has no cookie) |
| S4 | `os.makedirs()` without `exist_ok` races on concurrent first fetch | `server.py:162-164` | `FileExistsError` -> 500 under two cold requests | `exist_ok=True` | None |
| S5 | `SE_SECRET_KEY` unset mints a random key per run | `server.py:61-66` | Old login cookies die on restart (documented) | Keep; warn is accurate | N/A |
| S6 | `0.0.0.0` default exposes the server on the LAN | `server.py:53` | Intentional LAN play; amplifies S2 | Document; pair with S2 | N/A |

## Area B — Backend performance

Profiled with `cProfile` over `tools/sim_play.py --sessions 1 --seed 1`
(218 batches, 3.14 s total). The dominant server cost is `save_session`
(0.52 s, ~2.4 ms/batch), split between `open` and the atomic `os.replace`;
that is disk I/O, not CPU. The large `deepcopy` (0.80 s) is the simulator's
invariant checker, not the server. Conclusion: no honest micro-optimisation
moves the needle; the remaining work is correctness.

| # | Finding | Evidence | Verdict |
|---|---|---|---|
| P1 | `all_saves_userid()` allocates a list per command request | `sessions.py:200-203`, `server.py:458` | Negligible at local scale; not worth the churn |
| P2 | `get_game_config()` and config+gzip payloads are already cached | `get_game_config.py:73`, `server.py:319-335` | Correct; leave as is |
| P3 | Full save rewrite per command batch | `sessions.py:336-357` | I/O-bound and throttled by design; a debounce would trade durability for speed |
| P4 | `_download_miss` is unbounded | `server.py:130` | Bounded by the asset set in practice; revisit only if it grows |
| P5 | `log(session)` dumps the session on every play/ruffle | `server.py:210,228` | Already gated by `SE_VERBOSE` in `logger.py:12`; no change |

## Area C — Backend correctness / robustness

| # | Finding | Evidence | Impact | Action |
|---|---|---|---|---|
| C1 | `get_player_info_response` assumes `user` is a `str` before `.startswith` | `server.py:389` | None: `_param` always returns `str` or `None`, and `None` is handled first | Verified not reachable |
| C2 | `config/patch.py` reads a non-existent `patched_config.json` | `config/patch.py:7` | Dead/broken dev helper | Fix or delete |
| C3 | `mods_collect_all` assumes `neighbor_session` is non-None | `server.py:490` | Safe: membership is checked first and saves are never removed at runtime | No change |
| C4 | The rolling `.bak` was written but never read on boot | `sessions.py:142-173`, `sessions.py:335-357` | A corrupt save was skipped even though a good backup existed | Try the `.bak` through the same validation/migration path and persist the recovery |

## Area D — Frontend

The UI is a thin shell around a fixed 760x600 Flash movie, so most web-surface
work is deliberately N/A.

| # | Topic | Verdict |
|---|---|---|
| D1 | Responsive | N/A for the movie; login page already centers. No viewport meta, but the canvas is fixed. |
| D2 | SEO | N/A: private local server, no crawlers. |
| D3 | Forms | Login form has no CSRF token (low impact); keep unless S3 changes it |
| D4 | Minimalism | Already minimal; `base.html` removed the duplication |
| D5 | Accessibility | Game bar uses `<a href="#">`; add `aria-label` only if it earns its keep |

## Area E — Tooling / build / docs

| # | Finding | Evidence | Action |
|---|---|---|---|
| E1 | `build.bat` ships every runtime dir; `launcher_build.bat` did not copy `mods/` next to the exe | `build/*.bat` | Fixed: the launcher now creates `saves/` and copies `mods/` |
| E2 | Docs repeat stale claims (ported paths, old counts) | `odd/tasks/*` | Fix only what a change directly contradicts |
| E3 | `tools/measure_perf.py` is curl-based and reliable | `tools/measure_perf.py` | Use it for the latency numbers |

## Area F — Tests / CI

| # | Finding | Evidence | Action |
|---|---|---|---|
| F1 | Windows + Linux CI now runs | `.github/workflows/tests.yml` | Keep green |
| F2 | No test for the asset-loader traversal | `tests/test_asset_route.py` | Add with S1 |
| F3 | Concurrency covered for state, not for asset writes | `tests/test_state_concurrency.py` | Add with S4 |

## Findings ledger

| ID | Area | Status | Commit |
|---|---|---|---|
| S1 | security | done | `f313a8c` |
| S4 | security | done | `f313a8c` |
| S3 | security | done | `f313a8c` |
| C4 | correctness | done | this commit |
| C5 | correctness | done: recovery no longer overwrites the `.bak` it was rebuilt from | review |
| S2 | security | mitigated: loopback default, explicit LAN opt-in | this commit |
| S7 | security | done: a NUL byte in an asset path is a 404, not a 500 | review |
| P1–P5 | perf | measured; no change justified | — |
| C1, C3 | correctness | verified not reachable / safe | — |
| C2 | tooling | by design: a dev-only generator that expects a hand-made `patched_config.json` | — |
| E1 | packaging | done | this commit |

## Execution order

1. **Batch 1 (done):** S1, S4, S3, F2, F3 — `f313a8c`.
2. **Batch 2 (done):** C4, plus measurement that closes P1–P5, C1 and C3.
3. **Batch 3 (done):** S2 (loopback default), C2 ruled by design, E1 launcher packaging.
