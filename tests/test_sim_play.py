"""Tests for the isolated play simulator harness.

These tests exercise the envelope builder, the invariant checker and the real
save isolation guard.  They deliberately do **not** test game logic; they test
that the simulator can speak the protocol and notice when a save is broken.
"""

import json
import os
import tempfile
import time

from tools.sim_play import (
    _record_mtimes,
    build_envelope,
    check_invariants,
    real_saves_changed,
)

COMMAND_URL = "/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/command.php"


def _invariants_present(failures, *names):
    """Return True when every named invariant appears at least once."""
    found = {f["invariant"] for f in failures}
    return set(names) <= found


class TestEnvelopeBuilder:
    def test_build_produces_valid_payload(self):
        payload = build_envelope([{"cmd": "game_status", "args": ["ping"]}])
        assert isinstance(payload, str)
        assert payload[64] == ";"
        assert len(payload) >= 66
        parsed = json.loads(payload[65:])
        for key in ("ts", "first_number", "accessToken", "tries", "publishActions", "commands"):
            assert key in parsed
        assert parsed["commands"] == [{"cmd": "game_status", "args": ["ping"]}]

    def test_envelope_is_accepted_by_server(self, client, user):
        data = build_envelope([{"cmd": "complete_tutorial", "args": [31]}])
        resp = client.post(COMMAND_URL, data={"USERID": user, "data": data})
        assert resp.status_code == 200
        assert resp.get_json() == {"result": "success"}


class TestInvariantChecker:
    def test_clean_save_has_no_violations(self, user):
        failures = check_invariants(user)
        violations = [f for f in failures if f.get("category") == "violation"]
        assert violations == []

    def test_checker_fires_on_corrupted_save(self, user):
        import sessions

        state = sessions.session(user)
        # Negative resource.
        state["maps"][0]["coins"] = -100
        # Duplicate item position.
        state["maps"][0]["items"].append([1, 50, 50, 0, 0, 0])
        state["maps"][0]["items"].append([1, 50, 50, 0, 0, 0])

        failures = check_invariants(user)

        assert _invariants_present(
            failures,
            "resource_non_negative",
            "no_duplicate_item_position",
            "disk_matches_memory",
        )


class TestIsolationGuard:
    def test_detects_modified_save_mtime(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "test.save.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"version": "0.05b"}, handle)
            before = _record_mtimes(directory)
            time.sleep(0.01)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"version": "0.05b", "extra": 1}, handle)
            changed = real_saves_changed(before, directory=directory)
            assert path in changed

    def test_empty_directory_has_no_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            before = _record_mtimes(directory)
            assert real_saves_changed(before, directory=directory) == []
