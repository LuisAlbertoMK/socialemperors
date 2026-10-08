"""Failure paths of the save loader.

``load_saved_villages`` runs at import time on every boot, so when its
preconditions are not met it must stop the process in a way that works in every
runtime — including a frozen build, where ``site.py`` (and therefore the
``exit()`` builtin) is not executed.
"""

import json
import site as site_module
import subprocess
import sys

import pytest

import sessions


@pytest.fixture
def restored_village_state():
    """``load_saved_villages`` resets the module globals; put them back after."""
    villages = dict(sessions.__villages)
    saves = dict(sessions.__saves)
    yield
    sessions.__villages.clear()
    sessions.__villages.update(villages)
    sessions.__saves.clear()
    sessions.__saves.update(saves)


def test_saves_path_that_is_a_file_stops_the_process(
    tmp_path, monkeypatch, restored_village_state
):
    blocker = tmp_path / "saves"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(sessions, "SAVES_DIR", str(blocker))
    monkeypatch.setattr(sessions, "VILLAGES_DIR", str(tmp_path))

    with pytest.raises(SystemExit):
        sessions.load_saved_villages()


def test_uncreatable_saves_path_stops_the_process(
    tmp_path, monkeypatch, restored_village_state
):
    missing_parent = tmp_path / "no-such-parent" / "saves"
    monkeypatch.setattr(sessions, "SAVES_DIR", str(missing_parent))
    monkeypatch.setattr(sessions, "VILLAGES_DIR", str(tmp_path))

    with pytest.raises(SystemExit):
        sessions.load_saved_villages()


def test_failure_path_works_without_the_site_builtins():
    """A frozen build has no ``exit()``; the loader must not depend on site.py."""
    site_paths = site_module.getsitepackages()
    script = f"""
import os, sys, tempfile
sys.path[:0] = {site_paths!r}
sys.path.insert(0, ".")
import sessions

blocker = os.path.join(tempfile.mkdtemp(), "saves")
open(blocker, "w").close()
sessions.SAVES_DIR = blocker
sessions.VILLAGES_DIR = tempfile.mkdtemp()
try:
    sessions.load_saved_villages()
except SystemExit as exc:
    print("SystemExit", exc.code)
except BaseException as exc:
    print(type(exc).__name__ + ":", exc)
"""
    result = subprocess.run(
        [sys.executable, "-S", "-c", script],
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert result.stdout.strip().splitlines()[-1].startswith("SystemExit"), (
        result.stdout[-400:] + result.stderr[-400:]
    )


def test_save_with_a_broken_map_names_entry_still_loads(
    tmp_path, monkeypatch, restored_village_state
):
    """The map name is only used for a log line: it must never drop a save."""
    saves = tmp_path / "saves"
    saves.mkdir()
    villages = tmp_path / "villages"
    villages.mkdir()
    with open("villages/initial.json", encoding="utf-8") as template:
        village = json.load(template)
    village["playerInfo"]["pid"] = "broken-map-name"
    village["playerInfo"]["map_names"] = {}
    village["playerInfo"]["default_map"] = 0
    (saves / "broken-map-name.save.json").write_text(
        json.dumps(village), encoding="utf-8"
    )
    monkeypatch.setattr(sessions, "SAVES_DIR", str(saves))
    monkeypatch.setattr(sessions, "VILLAGES_DIR", str(villages))

    sessions.load_saved_villages()

    assert "broken-map-name" in sessions.all_saves_userid()


def test_missing_villages_directory_stops_with_a_clear_message(
    tmp_path, monkeypatch, restored_village_state, capsys
):
    """SAVES_DIR is validated on boot; VILLAGES_DIR must be too (broken bundle)."""
    saves = tmp_path / "saves"
    saves.mkdir()
    monkeypatch.setattr(sessions, "SAVES_DIR", str(saves))
    monkeypatch.setattr(sessions, "VILLAGES_DIR", str(tmp_path / "no-villages"))

    with pytest.raises(SystemExit):
        sessions.load_saved_villages()

    assert "no-villages" in capsys.readouterr().out
