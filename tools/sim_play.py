#!/usr/bin/env python3
"""Isolated Social Emperors play simulator.

Drives the real Flask application through a seeded, reproducible client session
without touching the developer's real ``saves/`` folder.  Every command batch is
checked against the invariants documented in ``odd/tasks/simulate-play.md``.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import io
import json
import math
import os
import random
import shutil
import sys
import tempfile
import traceback
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ---------------------------------------------------------------------------
# Envelope builder
# ---------------------------------------------------------------------------

_COMMAND_PAYLOAD_KEYS = ("ts", "first_number", "accessToken", "tries", "publishActions", "commands")


def build_envelope(
    commands: list[dict[str, Any]],
    ts: int | None = None,
    first_number: int = 0,
    access_token: str = "",
    tries: int = 0,
    publish_actions: str = "",
) -> str:
    """Build the real client envelope ``<64-char digest>;<json>``.

    The digest is not verified by the server, but the separator and the payload
    shape must match what ``server._parse_command_envelope`` expects.
    """
    payload = {
        "ts": ts if ts is not None else 0,
        "first_number": first_number,
        "accessToken": access_token,
        "tries": tries,
        "publishActions": publish_actions,
        "commands": commands,
    }
    digest = "0" * 64
    return f"{digest};{json.dumps(payload, separators=(',', ':'))}"


def _parse_envelope(data: str) -> dict[str, Any] | None:
    """Parse an envelope back into a payload dict (for self-tests)."""
    if not isinstance(data, str) or len(data) < 66 or data[64] != ";":
        return None
    try:
        payload = json.loads(data[65:])
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    if any(key not in payload for key in _COMMAND_PAYLOAD_KEYS):
        return None
    if not isinstance(payload["commands"], list):
        return None
    return payload


# ---------------------------------------------------------------------------
# Invariant checker
# ---------------------------------------------------------------------------


def _save_path(userid: str) -> str:
    import sessions

    return os.path.join(sessions.SAVES_DIR, f"{userid}.save.json")


def _load_disk(userid: str) -> dict[str, Any] | None:
    try:
        with open(_save_path(userid), encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        return {"__load_error__": str(error)}


def check_invariants(
    userid: str,
    state: dict[str, Any] | None = None,
    disk: dict[str, Any] | None = None,
    previous_state: dict[str, Any] | None = None,
    resp: Any = None,
    expected_success: bool = True,
    exception: BaseException | None = None,
    warnings: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return a list of invariant failures for the current session state."""
    import sessions

    failures: list[dict[str, Any]] = []

    if state is None:
        state = sessions.session(userid)
    if disk is None:
        disk = _load_disk(userid)

    # 1. HTTP envelope result.
    if expected_success and resp is not None:
        if getattr(resp, "status_code", None) != 200:
            failures.append(
                {
                    "invariant": "http_success",
                    "expected": 200,
                    "observed": getattr(resp, "status_code", None),
                    "body": _safe_body(resp),
                }
            )
        else:
            body = _safe_json(resp)
            if body != {"result": "success"}:
                failures.append(
                    {
                        "invariant": "result_success",
                        "expected": {"result": "success"},
                        "observed": body,
                    }
                )

    if (
        not expected_success
        and resp is not None
        and getattr(resp, "status_code", None) == 500
    ):
        failures.append(
            {
                "invariant": "no_crash_on_malformed",
                "observed": _safe_body(resp),
            }
        )

    # 2. Unhandled exception reaching the route.
    if exception is not None:
        failures.append(
            {
                "invariant": "no_unhandled_exception",
                "observed": f"{type(exception).__name__}: {exception}",
                "traceback": traceback.format_exception(exception),
            }
        )

    # 3. Server-side warnings (contained command rejections are expected for
    #    adversarial batches, but we still surface them).
    for warning in warnings or []:
        failures.append(
            {
                "invariant": "command_warning",
                "observed": warning,
            }
        )

    # 4. Save is loadable and has the expected version.
    load_error = disk.get("__load_error__") if isinstance(disk, dict) else None
    if load_error:
        failures.append(
            {
                "invariant": "save_loadable",
                "observed": load_error,
            }
        )
    elif isinstance(disk, dict) and disk.get("version") != "0.05b":
        failures.append(
            {
                "invariant": "version",
                "expected": "0.05b",
                "observed": disk.get("version"),
            }
        )

    # Helper to test numeric sanity.
    def _bad_number(value: Any) -> bool:
        if isinstance(value, bool):
            return False
        if isinstance(value, (int, float)):
            return math.isnan(value) or value < 0
        return False

    # 5. Resources never negative / NaN.
    if isinstance(state, dict):
        for idx, map_state in enumerate(state.get("maps") or []):
            for key in ("coins", "xp", "level", "stone", "wood", "food"):
                if _bad_number(map_state.get(key)):
                    failures.append(
                        {
                            "invariant": "resource_non_negative",
                            "path": f"maps[{idx}].{key}",
                            "observed": map_state.get(key),
                        }
                    )
            # population stand-in: the save schema uses increasedPopulation.
            if _bad_number(map_state.get("increasedPopulation", 0)):
                failures.append(
                    {
                        "invariant": "population_non_negative",
                        "path": f"maps[{idx}].increasedPopulation",
                        "observed": map_state.get("increasedPopulation"),
                    }
                )
        player_info = state.get("playerInfo") or {}
        for key in ("cash", "coins", "food", "stone", "wood", "level"):
            if _bad_number(player_info.get(key)):
                failures.append(
                    {
                        "invariant": "resource_non_negative",
                        "path": f"playerInfo.{key}",
                        "observed": player_info.get(key),
                    }
                )

    # 6. Item shape and duplicate (id, x, y) collisions.
    if isinstance(state, dict):
        for idx, map_state in enumerate(state.get("maps") or []):
            items = map_state.get("items") or []
            seen: dict[tuple[int, int, int], int] = {}
            for item in items:
                if not isinstance(item, list) or len(item) < 6:
                    failures.append(
                        {
                            "invariant": "item_well_formed",
                            "path": f"maps[{idx}].items",
                            "observed": item,
                        }
                    )
                    continue
                try:
                    key = (int(item[0]), int(item[1]), int(item[2]))
                except (TypeError, ValueError):
                    failures.append(
                        {
                            "invariant": "item_well_formed",
                            "path": f"maps[{idx}].items",
                            "observed": item[:3],
                        }
                    )
                    continue
                if key in seen:
                    failures.append(
                        {
                            "invariant": "no_duplicate_item_position",
                            "path": f"maps[{idx}].items",
                            "item": key,
                            "positions": [seen[key], len(seen)],
                        }
                    )
                else:
                    seen[key] = len(seen)

    # 7. Monotonic level / expansions / quest counter.
    if isinstance(state, dict) and isinstance(previous_state, dict):
        for idx, (prev_map, cur_map) in enumerate(
            zip(
                previous_state.get("maps") or [],
                state.get("maps") or [],
                strict=False,
            )
        ):
            if (cur_map.get("level") or 0) < (prev_map.get("level") or 0):
                failures.append(
                    {
                        "invariant": "level_monotonic",
                        "path": f"maps[{idx}].level",
                        "previous": prev_map.get("level"),
                        "current": cur_map.get("level"),
                    }
                )
            prev_exps = set(prev_map.get("expansions") or [])
            cur_exps = set(cur_map.get("expansions") or [])
            if not prev_exps <= cur_exps:
                failures.append(
                    {
                        "invariant": "expansions_monotonic",
                        "path": f"maps[{idx}].expansions",
                        "lost": list(prev_exps - cur_exps),
                    }
                )
        prev_quest = (previous_state.get("privateState") or {}).get("unlockedQuestIndex", 0)
        cur_quest = (state.get("privateState") or {}).get("unlockedQuestIndex", 0)
        if cur_quest < prev_quest:
            failures.append(
                {
                    "invariant": "unlockedQuestIndex_monotonic",
                    "previous": prev_quest,
                    "current": cur_quest,
                }
            )

    # 8. Warehouse counts never negative.
    if isinstance(state, dict):
        for idx, map_state in enumerate(state.get("maps") or []):
            store = map_state.get("store")
            if isinstance(store, dict):
                for item_id, count in store.items():
                    if _bad_number(count):
                        failures.append(
                            {
                                "invariant": "warehouse_non_negative",
                                "path": f"maps[{idx}].store[{item_id}]",
                                "observed": count,
                            }
                        )

    # 9. Re-loading a save from disk yields the same state as memory.
    if (
        isinstance(state, dict)
        and isinstance(disk, dict)
        and "__load_error__" not in disk
        and disk != state
    ):
        failures.append(
            {
                "invariant": "disk_matches_memory",
                "observed": "in-memory state differs from file on disk",
            }
        )

    return failures


def _safe_json(resp: Any) -> Any:
    try:
        return resp.get_json()
    except Exception as error:
        return {"__parse_error__": str(error)}


def _safe_body(resp: Any) -> Any:
    try:
        return resp.get_data(as_text=True)
    except Exception as error:
        return str(error)


# ---------------------------------------------------------------------------
# Real-save isolation guard
# ---------------------------------------------------------------------------


def _real_save_dir() -> str:
    return os.path.join(ROOT, "saves")


def _record_mtimes(directory: str) -> dict[str, float]:
    mtimes: dict[str, float] = {}
    if not os.path.isdir(directory):
        return mtimes
    for name in os.listdir(directory):
        if not name.endswith(".save.json"):
            continue
        path = os.path.join(directory, name)
        with contextlib.suppress(OSError):
            mtimes[path] = os.path.getmtime(path)
    return mtimes


def real_saves_changed(before: dict[str, float], directory: str | None = None) -> list[str]:
    """Return paths under ``directory`` (default real ``saves/``) whose mtimes changed."""
    after = _record_mtimes(directory if directory is not None else _real_save_dir())
    changed: list[str] = []
    for path, mtime in before.items():
        if after.get(path) != mtime:
            changed.append(path)
    for path in after:
        if path not in before:
            changed.append(path)
    return changed


# ---------------------------------------------------------------------------
# Seeded session script
# ---------------------------------------------------------------------------


class SessionScript:
    """Generate coherent, reproducible command batches for one village."""

    # Item ids chosen because they are cheap and cover buildings / units.
    BUILDING_IDS = (1, 5, 8, 13, 16, 19, 23, 29, 34, 41)
    UNIT_IDS = (500, 509, 512, 516)
    LAND_IDS = (1001, 1002, 1003, 1004, 1005, 1006)

    def __init__(self, rng: random.Random, town_id: int = 0) -> None:
        self.rng = rng
        self.town_id = town_id
        self.items_on_map: list[dict[str, Any]] = []
        self.warehouse: dict[int, int] = {}
        self.gifts: dict[int, int] = {}
        self.placed_count: dict[int, int] = {}
        self.next_x = 20
        self.next_y = 20
        self.current_level = 1

    def free_coordinate(self) -> tuple[int, int]:
        """Return a fresh coordinate far from the initial village centre."""
        x, y = self.next_x, self.next_y
        self.next_x += 1
        if self.next_x > 80:
            self.next_x = 20
            self.next_y += 1
        return x, y

    def remember_item(self, item_id: int, x: int, y: int) -> dict[str, Any]:
        record = {"id": item_id, "x": x, "y": y}
        self.items_on_map.append(record)
        self.placed_count[item_id] = self.placed_count.get(item_id, 0) + 1
        return record

    def remove_item_at(self, x: int, y: int) -> dict[str, Any] | None:
        for idx, record in enumerate(self.items_on_map):
            if record["x"] == x and record["y"] == y:
                return self.items_on_map.pop(idx)
        return None

    def pick_existing(self) -> dict[str, Any] | None:
        if not self.items_on_map:
            return None
        return self.rng.choice(self.items_on_map)

    def buy(self, item_id: int | None = None, free: bool = False) -> dict[str, Any]:
        if item_id is None:
            item_id = self.rng.choice(self.BUILDING_IDS + self.UNIT_IDS)
        x, y = self.free_coordinate()
        _ = self.remember_item(item_id, x, y)
        return {
            "cmd": "buy",
            "args": [
                item_id,
                x,
                y,
                0,  # frame
                self.town_id,
                1 if free else 0,  # bool_dont_modify_resources
                1,  # price_multiplier
                "b",
            ],
        }

    def move(self) -> dict[str, Any] | None:
        record = self.pick_existing()
        if record is None:
            return None
        nx, ny = self.free_coordinate()
        old = (record["x"], record["y"])
        record["x"], record["y"] = nx, ny
        return {
            "cmd": "move",
            "args": [
                old[0],
                old[1],
                record["id"],
                nx,
                ny,
                0,
                self.town_id,
                "moveTo",
            ],
        }

    def collect(self) -> dict[str, Any] | None:
        record = self.pick_existing()
        if record is None:
            return None
        return {
            "cmd": "collect_new",
            "args": [
                record["x"],
                record["y"],
                self.town_id,
                record["id"],
                0,
                1,
                0,
            ],
        }

    def sell(self, reason: str = "DEBUG") -> dict[str, Any] | None:
        record = self.pick_existing()
        if record is None:
            return None
        self.remove_item_at(record["x"], record["y"])
        return {
            "cmd": "sell",
            "args": [
                record["x"],
                record["y"],
                record["id"],
                self.town_id,
                0,
                reason,
            ],
        }

    def store_frombug(self) -> dict[str, Any] | None:
        record = self.pick_existing()
        if record is None:
            return None
        self.remove_item_at(record["x"], record["y"])
        self.warehouse[record["id"]] = self.warehouse.get(record["id"], 0) + 1
        return {
            "cmd": "store_item_frombug",
            "args": [record["x"], record["y"], self.town_id, record["id"]],
        }

    def place_stored(self) -> dict[str, Any] | None:
        available = [iid for iid, count in self.warehouse.items() if count > 0]
        if not available:
            return None
        item_id = self.rng.choice(available)
        self.warehouse[item_id] -= 1
        x, y = self.free_coordinate()
        self.remember_item(item_id, x, y)
        return {
            "cmd": "place_stored_item",
            "args": [item_id, x, y, self.town_id],
        }

    def sell_stored(self) -> dict[str, Any] | None:
        available = [iid for iid, count in self.warehouse.items() if count > 0]
        if not available:
            return None
        item_id = self.rng.choice(available)
        self.warehouse[item_id] -= 1
        return {
            "cmd": "sell_stored_item",
            "args": [item_id, self.town_id],
        }

    def expand(self) -> dict[str, Any]:
        land_id = self.rng.choice(self.LAND_IDS)
        return {
            "cmd": "expand",
            "args": [land_id, "gold", self.town_id],
        }

    def level_up(self) -> dict[str, Any]:
        self.current_level += self.rng.randint(1, 3)
        return {
            "cmd": "rt_level_up",
            "args": [self.current_level],
        }

    def end_quest(self) -> dict[str, Any]:
        quest_id = self.rng.randint(1, 10)
        payload = {
            "map": self.town_id,
            "resources": {"g": self.rng.randint(0, 100), "x": self.rng.randint(0, 50)},
            "units": [],
            "win": 1,
            "duration": self.rng.randint(10, 300),
            "voluntary_end": 0,
            "quest_id": quest_id,
            "item_rewards": [],
            "activators_left": [],
            "difficulty": 1,
        }
        return {
            "cmd": "end_quest",
            "args": [json.dumps(payload)],
        }

    def complete_tutorial(self) -> dict[str, Any]:
        return {"cmd": "complete_tutorial", "args": [31]}

    def game_status(self) -> dict[str, Any]:
        return {"cmd": "game_status", "args": ["ping"]}

    def name_map(self) -> dict[str, Any]:
        return {
            "cmd": "name_map",
            "args": [self.town_id, f"SimEmpire{self.rng.randint(0, 9999)}"],
        }

    def unhandled_gap(self) -> dict[str, Any]:
        """Commands a captured real client sent that have no server branch."""
        gaps = [
            {"cmd": "buy_si_help", "args": [59, 62, 0, 299, 1]},
            {"cmd": "activate", "args": [59, 46, 0, 13, 4]},
            {"cmd": "buy_magic", "args": [2, 0, 0]},
            {"cmd": "finish_si", "args": [59, 62, 0, 299]},
            {"cmd": "next_temple_step", "args": ['{"w":100000}', 2]},
            {"cmd": "pop_sell", "args": [66, 40, 0, 225, 500]},
            {"cmd": "end_attack", "args": [1, 0, 0]},
            {"cmd": "spy_player", "args": ["12345"]},
            {"cmd": "set_strategy", "args": [8]},
        ]
        return self.rng.choice(gaps)

    def generate_batches(self) -> list[list[dict[str, Any]]]:
        """Return all batches for one session (well over 200 commands)."""
        batches: list[list[dict[str, Any]]] = []

        def add(batch: list[dict[str, Any] | None]) -> None:
            clean = [cmd for cmd in batch if cmd is not None]
            if clean:
                batches.append(clean)

        # Onboarding: complete tutorial, place a few buildings, move, harvest.
        add([self.complete_tutorial()])
        for _ in range(5):
            add([self.buy(free=False)])
        for _ in range(3):
            cmd = self.move()
            if cmd:
                add([cmd])
        for _ in range(4):
            cmd = self.collect()
            if cmd:
                add([cmd])

        # Economy: sell, warehouse round-trip, expansion, level-up, quest end.
        for _ in range(4):
            cmd = self.sell()
            if cmd:
                add([cmd])
        for _ in range(3):
            cmd = self.store_frombug()
            if cmd:
                add([cmd])
        for _ in range(2):
            cmd = self.place_stored()
            if cmd:
                add([cmd])
        add([self.sell_stored()] if self.warehouse else [self.game_status()])
        add([self.expand()])
        add([self.level_up()])
        add([self.end_quest()])

        # Repeated identical commands.
        cmd = self.complete_tutorial()
        add([cmd, copy.deepcopy(cmd)])

        # Out-of-order: sell something that is not there, then buy one.
        x, y = self.free_coordinate()
        add([
            {"cmd": "sell", "args": [x, y, 1, self.town_id, 0, "DEBUG"]},
            self.buy(item_id=1),
        ])

        # Batch with a wrong argument shape (caught) plus a valid one.
        add([
            {"cmd": "move", "args": [0]},
            self.game_status(),
        ])

        # Unknown wire name plus a valid one.
        add([
            {"cmd": "no_such_command", "args": []},
            self.game_status(),
        ])

        # Gaps (commands with no server branch).
        for _ in range(8):
            add([self.unhandled_gap()])

        # More economy / random walks to reach 200+ commands.
        for _ in range(220):
            choices = [
                self.buy,
                self.move,
                self.collect,
                self.sell,
                self.store_frombug,
                self.place_stored,
                self.sell_stored,
                self.expand,
                self.level_up,
                self.end_quest,
                self.unhandled_gap,
                self.name_map,
                self.game_status,
            ]
            choice = self.rng.choice(choices)
            cmd = choice()
            if cmd is not None:
                add([cmd])

        # Empty batch is legal.
        add([])

        return batches


# ---------------------------------------------------------------------------
# Simulator harness
# ---------------------------------------------------------------------------


def _run_session(
    app: Any,
    sessions: Any,
    seed: int,
    session_index: int,
    verbose: bool,
) -> dict[str, Any]:
    """Run one full village session and return its report."""
    rng = random.Random(seed + session_index)
    script = SessionScript(rng)
    batches = script.generate_batches()

    summary: dict[str, Any] = {
        "seed_offset": session_index,
        "batches": len(batches),
        "commands": sum(len(b) for b in batches),
        "failed_batches": 0,
        "findings": [],
    }

    with app.test_client() as client:
        app.config.update(TESTING=True)
        userid = sessions.new_village()
        summary["userid"] = userid

        for batch_index, commands in enumerate(batches):
            previous_state = copy.deepcopy(sessions.session(userid))

            data = build_envelope(commands)
            stdout_buf = io.StringIO()
            stderr_buf = io.StringIO()
            exception: BaseException | None = None
            try:
                with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(
                    stderr_buf
                ):
                    resp = client.post(
                        "/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/command.php",
                        data={"USERID": userid, "data": data},
                    )
            except BaseException as exc:
                exception = exc
                resp = None

            stdout = stdout_buf.getvalue()
            stderr = stderr_buf.getvalue()
            warnings = [
                line
                for line in (stdout + stderr).splitlines()
                if "[WARN] command" in line
            ]

            failures = check_invariants(
                userid,
                previous_state=previous_state,
                resp=resp,
                expected_success=True,
                exception=exception,
                warnings=warnings,
            )

            for failure in failures:
                failure.setdefault(
                    "category",
                    "warning" if failure.get("invariant") == "command_warning" else "violation",
                )
                finding = {
                    "session_index": session_index,
                    "batch_index": batch_index,
                    "commands": copy.deepcopy(commands),
                    **failure,
                }
                summary["findings"].append(finding)
                if finding["category"] == "violation":
                    summary["failed_batches"] += 1
                if verbose:
                    print(f"  [FINDING] {finding}")

    return summary


def run_simulation(app: Any, sessions: int, seed: int, verbose: bool) -> dict[str, Any]:
    """Run the soak across many sessions."""
    import sessions as sessions_module

    report: dict[str, Any] = {
        "seed": seed,
        "sessions": sessions,
        "session_summaries": [],
        "findings": [],
    }

    for i in range(sessions):
        if verbose:
            print(f"[session {i + 1}/{sessions}] seed={seed + i}")
        summary = _run_session(app, sessions_module, seed, i, verbose)
        report["session_summaries"].append(summary)
        report["findings"].extend(summary["findings"])

    report["total_batches"] = sum(s["batches"] for s in report["session_summaries"])
    report["total_commands"] = sum(s["commands"] for s in report["session_summaries"])
    report["failed_batches"] = sum(
        s["failed_batches"] for s in report["session_summaries"]
    )
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Isolated Social Emperors simulator")
    parser.add_argument("--sessions", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--json", dest="json_path", required=True)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    # Isolation: pin cwd and redirect saves before importing the app.
    os.chdir(ROOT)
    real_saves_before = _record_mtimes(_real_save_dir())

    import sessions as sessions_module

    temp_saves = tempfile.mkdtemp(prefix="se-sim-saves-")
    sessions_module.SAVES_DIR = temp_saves

    # Suppress the noisy boot progress unless verbose.
    boot_stdout = io.StringIO()
    try:
        with contextlib.redirect_stdout(
            boot_stdout if not args.verbose else sys.stdout
        ):
            import server as server_module
    except Exception as exc:
        print(f"[FATAL] could not import server: {exc}", file=sys.stderr)
        shutil.rmtree(temp_saves, ignore_errors=True)
        return 2

    app = server_module.app
    app.secret_key = "sim-play-secret"

    try:
        report = run_simulation(app, args.sessions, args.seed, args.verbose)
    finally:
        shutil.rmtree(temp_saves, ignore_errors=True)

    # Final isolation check: the real saves/ folder must be untouched.
    changed = real_saves_changed(real_saves_before, directory=_real_save_dir())
    report["real_saves_changed"] = changed
    if changed:
        print(
            f"[FATAL] real saves/ mtimes changed: {changed}. "
            "The simulator is not isolated!",
            file=sys.stderr,
        )
        # Write the report anyway, then fail loudly.
        with open(args.json_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
        return 3

    with open(args.json_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    _print_summary(report)
    return 0 if report["failed_batches"] == 0 else 1


def _print_summary(report: dict[str, Any]) -> None:
    findings = report["findings"]
    print("=" * 60)
    print("Social Emperors play simulator summary")
    print("=" * 60)
    print(f"Seed:            {report['seed']}")
    print(f"Sessions:        {report['sessions']}")
    print(f"Total batches:   {report['total_batches']}")
    print(f"Total commands:  {report['total_commands']}")
    print(f"Failed batches:  {report['failed_batches']}")
    print(f"Distinct findings: {len(findings)}")
    if findings:
        by_invariant: dict[str, int] = {}
        for finding in findings:
            by_invariant[finding.get("invariant", "unknown")] = (
                by_invariant.get(finding.get("invariant", "unknown"), 0) + 1
            )
        print("Findings by invariant:")
        for invariant, count in sorted(by_invariant.items(), key=lambda kv: -kv[1]):
            print(f"  - {invariant}: {count}")
        print("First 5 findings:")
        for finding in findings[:5]:
            print(f"  {finding}")
    print("=" * 60)


if __name__ == "__main__":
    sys.exit(main())
