# harden-server-request-path

Feature: harden the request path and shared-state handling of the Social Emperors
local server (Flask). Scope chosen by the user: **defects and concurrency first**,
performance and cleanup deferred.

## Working context

- Worktree: `D:/socialemperors-odd` (linked worktree of `D:/socialemperors`,
  sparse-checkout with `assets/` excluded, 49 MB).
- Branch: `odd/harden-request-path`, based on `f642e0b`.
- Baseline: the 46 dirty entries that existed uncommitted in the main checkout
  were mirrored here verbatim (9 modified tracked files, 37 untracked files) so
  that work on this branch is isolated from the user's own in-flight changes.
  The main checkout was never modified.
- Main checkout remains dirty and untouched at `f642e0b`.

## User constraint (recorded deviation)

The user forbade commits: no commits to this repository at all (it is an external
upstream, `AcidCaos/socialemperors`). Therefore the ODD rule "every task closes
with a work-unit commit on the feature branch" is **explicitly waived** for this
feature. All work stays as uncommitted changes inside the isolated worktree, and
each task closes with observed test evidence instead of a commit identity.

Consequence to report at close: the diff is reviewable but not committed; a later
`git diff` in `D:/socialemperors-odd` is the whole deliverable.

## Findings under work (evidence from the audit)

| id | severity | evidence | defect |
| --- | --- | --- | --- |
| D1 | high | `server.py:253-265` | `/null`: `reason` only assigned inside three `if` branches, dereferenced at `:264` -> `UnboundLocalError` (500) for any other `sp_ref_cat`. This is the route the Flash client calls to recover from a sync error. Confirmed RED: `tests/test_null_route.py::test_null_route_redirects_for_unknown_ref_cat`. |
| D2 | high | `server.py:324`, `sessions.py:16,26,244-253`, `command.py:32` | `threaded=True` with no locking over the module-global `__saves`/`__villages`; `save_session` serializes the live dict while another thread mutates it -> torn save or `RuntimeError: dictionary changed size during iteration`. |
| D3 | high | `server.py:177-179,191-195,207-214,237-248,271-284,293-298` | Every dynamic route reads `request.values['X']` unguarded. Measured during T3: the missing parameter raises Werkzeug's `BadRequestKeyError`, so the client gets a **400 HTML** page (not 500 as first assumed) instead of a JSON or empty response it can handle. Confirmed RED: `tests/test_null_route.py::test_null_route_redirects_when_ref_cat_is_missing` (`assert 400 == 302`). |
| D4 | high | `server.py:282` | `assert data_str[64] == ';'` on client input; asserts vanish under `python -O`, leaving the payload boundary unvalidated. |
| D5 | medium | `command.py` (whole file) | No `try/except` anywhere; positional `args[N]` indexing without length validation (only `:172`, `:467` guard) -> `IndexError` aborts the whole command batch with a 500. |

Non-goals for this feature (deferred, still open): `neighbors()` duplication and
per-request rebuild, save-file `indent=4` cost, asset-fallback traversal/locking,
`backup_session` stub, test-free packaging (`bundle.py`, `.gitignore` gaps),
`get_game_config.py:54` discarded `replace()` result.

## Tasks

- [x] T1 Establish the isolated baseline worktree and mirror the user's dirty state.
- [ ] T2 Write this feature doc and its Engram mirror (before the first source write).
- [x] T3 Add the pytest harness and the failing (RED) test for `/null`.
  Evidence: `2 failed, 1 passed` — `UnboundLocalError` at `server.py:264` for an
  unknown `sp_ref_cat`, `400 != 302` for a missing one.
- [ ] T4 Fix D1 and make `app.secret_key` available outside `__main__`.
- [ ] T5 Fix D3: tolerant payload access on every dynamic route; no 500 HTML.
- [ ] T6 Fix D4: validate the command envelope, drop the assert.
- [ ] T7 Fix D2: per-player lock covering mutation + save, and safe shared-state access.
- [ ] T8 Fix D5: isolate malformed commands so one bad command cannot kill the batch.
- [ ] T9 Close: full suite + `ruff`, evidence, and report with the commit deviation.

## Verification plan

- Test-first per task: write the failing test, observe RED, apply the fix, observe GREEN.
- Run with the repo root as CWD (`bundle.BASE_DIR = "."` makes data paths CWD-relative).
- Deterministic checks only: Flask test client, no live server, no network.
- Concurrency check: drive the command path from several threads against a
  temporary save and assert the save file stays valid JSON and no exception escapes.
- `ruff check` on every touched file; `ruff` is available (0.16.10) though the
  repo has no config for it.
