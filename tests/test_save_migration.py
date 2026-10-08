"""Save migration.

``version_code`` is what every save is stamped with, and ``migrate_loaded_save``
walks a save forward through the chain until it reaches that version. Two things
must hold, and the second one is the one that used to be broken: the walk must
actually reach the current version, and a second pass must report "not modified"
so the loader does not rewrite the same file on every startup.
"""

import json

import pytest

import sessions
import version


def make_save(save_version):
    return {
        "version": save_version,
        "playerInfo": {"pid": "test-player"},
        "maps": [{"timestamp": 0}],
        "privateState": {},
    }


@pytest.fixture
def isolated_state():
    """``load_saved_villages`` resets the module globals; put them back after."""
    villages = dict(sessions.__villages)
    saves = dict(sessions.__saves)
    yield
    sessions.__villages.clear()
    sessions.__villages.update(villages)
    sessions.__saves.clear()
    sessions.__saves.update(saves)


def test_a_save_at_the_current_version_is_not_modified():
    save = make_save(version.version_code)

    assert version.migrate_loaded_save(save) is False


def test_the_previous_release_migrates_to_the_current_version():
    save = make_save("0.04a")

    assert version.migrate_loaded_save(save) is True
    assert save["version"] == version.version_code


def test_migration_converges_after_one_pass():
    """Otherwise the loader rewrites the save on every single startup."""
    save = make_save("0.04a")

    assert version.migrate_loaded_save(save) is True
    assert version.migrate_loaded_save(save) is False


def test_a_save_without_a_version_walks_the_whole_chain():
    save = make_save(None)

    assert version.migrate_loaded_save(save) is True

    assert save["version"] == version.version_code
    # Fields introduced along the chain are still created.
    assert "dartsRandomSeed" in save["privateState"]
    assert "arrayAnimals" in save["privateState"]
    assert "strategy" in save["privateState"]
    assert "questTimes" in save["maps"][0]
    assert "lastQuestTimes" in save["maps"][0]
    assert "pic" in save["playerInfo"]
    assert "survivalMaps" in save["privateState"]


def test_the_oldest_saves_still_converge():
    for old_version in ("0.01a", "0.02a", "0.03a"):
        save = make_save(old_version)

        assert version.migrate_loaded_save(save) is True, old_version
        assert version.migrate_loaded_save(save) is False, old_version
        assert save["version"] == version.version_code, old_version


def test_a_save_whose_migration_fails_is_skipped_instead_of_killing_the_boot(
    tmp_path, monkeypatch, isolated_state
):
    """A save that passes validation but breaks the migration must be skipped.

    ``is_valid_village`` accepts an empty ``maps`` list, and the migration then
    indexes ``maps[0]``. Before this guard the whole server refused to start.
    """
    saves_dir = tmp_path / "saves"
    saves_dir.mkdir()
    villages_dir = tmp_path / "villages"
    villages_dir.mkdir()
    with open("villages/initial.json", encoding="utf-8") as template:
        broken = json.load(template)
    broken["playerInfo"]["pid"] = "broken-migration"
    broken["maps"] = []
    # 0.01a is the step that indexes maps[0]; later steps never touch it.
    broken["version"] = "0.01a"
    (saves_dir / "broken-migration.save.json").write_text(
        json.dumps(broken), encoding="utf-8"
    )
    monkeypatch.setattr(sessions, "SAVES_DIR", str(saves_dir))
    monkeypatch.setattr(sessions, "VILLAGES_DIR", str(villages_dir))

    sessions.load_saved_villages()

    assert "broken-migration" not in sessions.all_saves_userid()
