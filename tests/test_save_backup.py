"""Rolling save backup.

The save file is the player's entire progress and it is rewritten on every
command batch, so a single bad write would lose everything. ``backup_session``
keeps one recent copy per player, refreshed at most every
``SE_BACKUP_SECONDS`` (default one hour, 0 disables it), taken from the file as
it was *before* the current write.
"""

import json
import os

import pytest

import sessions


@pytest.fixture
def user(tmp_path, monkeypatch):
    monkeypatch.setattr(sessions, "SAVES_DIR", str(tmp_path))
    userid = sessions.new_village()
    yield userid
    sessions.__saves.pop(userid, None)


def save_path(tmp_path, userid):
    return tmp_path / f"{userid}.save.json"


def backup_path(tmp_path, userid):
    return tmp_path / f"{userid}.save.json.bak"


def test_saving_keeps_a_copy_of_the_previous_state(tmp_path, user):
    sessions.session(user)["playerInfo"]["name"] = "After"

    sessions.save_session(user)

    saved = json.loads(save_path(tmp_path, user).read_text(encoding="utf-8"))
    backup = json.loads(backup_path(tmp_path, user).read_text(encoding="utf-8"))
    assert saved["playerInfo"]["name"] == "After"
    # The point of the backup: it holds the state from before the write.
    assert backup["playerInfo"]["name"] != "After"


def test_the_backup_is_not_refreshed_inside_the_interval(tmp_path, user):
    sessions.save_session(user)
    first_backup = backup_path(tmp_path, user).read_bytes()

    sessions.session(user)["playerInfo"]["name"] = "Later"
    sessions.save_session(user)

    assert backup_path(tmp_path, user).read_bytes() == first_backup


def test_an_old_backup_is_refreshed(tmp_path, user):
    sessions.save_session(user)  # file = first state, .bak = same
    first = json.loads(backup_path(tmp_path, user).read_text(encoding="utf-8"))

    sessions.session(user)["playerInfo"]["name"] = "Segundo"
    sessions.save_session(user)  # .bak is fresh, so it is skipped
    # Age the backup instead of mocking the clock.
    os.utime(backup_path(tmp_path, user), (0, 0))

    sessions.session(user)["playerInfo"]["name"] = "Tercero"
    sessions.save_session(user)

    refreshed = json.loads(backup_path(tmp_path, user).read_text(encoding="utf-8"))
    # Refreshed from the file as it was before this last write, i.e. "Segundo".
    assert refreshed["playerInfo"]["name"] == "Segundo"
    assert refreshed["playerInfo"]["name"] != first["playerInfo"]["name"]


def test_backing_up_an_unknown_player_does_nothing(tmp_path):
    sessions.backup_session("no-such-player")

    assert not (tmp_path / "no-such-player.save.json.bak").exists()


def test_the_backup_can_be_disabled(tmp_path, user, monkeypatch):
    monkeypatch.setattr(sessions, "BACKUP_INTERVAL_SECONDS", 0)

    sessions.save_session(user)

    assert not backup_path(tmp_path, user).exists()


def test_a_corrupted_save_is_recoverable_from_the_backup(tmp_path, user):
    """The real purpose of the feature, end to end."""
    sessions.session(user)["playerInfo"]["name"] = "Intacto"
    sessions.save_session(user)
    os.utime(backup_path(tmp_path, user), (0, 0))
    sessions.save_session(user)  # refresh the backup with 'Intacto'

    save_path(tmp_path, user).write_text("{ truncated", encoding="utf-8")

    recovered = json.loads(backup_path(tmp_path, user).read_text(encoding="utf-8"))
    assert recovered["playerInfo"]["name"] == "Intacto"
    assert recovered["maps"][0]["items"] is not None


def test_a_failed_backup_does_not_block_the_save(tmp_path, user, monkeypatch):
    """Losing a backup is bad; refusing to save because of it is worse."""
    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(sessions.shutil, "copyfile", boom)
    sessions.session(user)["playerInfo"]["name"] = "Igual se guarda"

    sessions.save_session(user)

    saved = json.loads(save_path(tmp_path, user).read_text(encoding="utf-8"))
    assert saved["playerInfo"]["name"] == "Igual se guarda"
