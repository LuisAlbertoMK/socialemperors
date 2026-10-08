"""Regression tests for the four progressions a player cares about.

Three of them already persist and these tests pin that down, so a later change
cannot silently break them the way the collectibles were broken. The fourth,
building upgrades, does not: ``CMD_UPGRADE`` exists in ``constants.py`` but has no
branch in ``command.py``, and every placed item is written with ``level = 0``.
That gap is recorded in ``odd/tasks/quest-progress.md`` and needs a capture of a
real upgrade to be implemented without guessing.
"""

import json

import pytest

import command as command_module
import sessions
from constants import Constant


@pytest.fixture
def user(tmp_path, monkeypatch):
    saves = tmp_path / "saves"
    saves.mkdir()
    monkeypatch.setattr(sessions, "SAVES_DIR", str(saves))
    userid = sessions.new_village()
    yield userid
    sessions.__saves.pop(userid, None)


def state(userid):
    return sessions.session(userid)


def saved(tmp_path, userid):
    with open(tmp_path / "saves" / f"{userid}.save.json", encoding="utf-8") as handle:
        return json.load(handle)


def test_territory_expansion_is_recorded_and_saved(tmp_path, user):
    before = list(state(user)["maps"][0]["expansions"])

    command_module.do_command(user, Constant.CMD_EXPAND, ["42", "gold", 0])
    sessions.save_session(user)

    after = state(user)["maps"][0]["expansions"]
    assert "42" in after or 42 in after
    assert len(after) == len(before) + 1
    assert len(saved(tmp_path, user)["maps"][0]["expansions"]) == len(after)


def test_expanding_the_same_land_twice_changes_nothing(user):
    command_module.do_command(user, Constant.CMD_EXPAND, ["42", "gold", 0])
    once = list(state(user)["maps"][0]["expansions"])

    command_module.do_command(user, Constant.CMD_EXPAND, ["42", "gold", 0])

    assert state(user)["maps"][0]["expansions"] == once


def test_a_level_up_is_recorded_and_saved(tmp_path, user):
    command_module.do_command(user, Constant.CMD_RT_LEVEL_UP, [7])
    sessions.save_session(user)

    assert int(state(user)["maps"][0]["level"]) == 7
    assert int(saved(tmp_path, user)["maps"][0]["level"]) == 7


def test_a_level_up_never_leaves_the_player_below_its_own_level_xp(user):
    """The branch pads xp up to the new level, which is what the client expects."""
    command_module.do_command(user, Constant.CMD_RT_LEVEL_UP, [5])

    from get_game_config import get_xp_from_level

    assert int(state(user)["maps"][0]["xp"]) >= int(get_xp_from_level(4))


QUEST_PAYLOAD = {
    "voluntary_end": 0,
    "duration": 73,
    "difficulty": 1,
    "units": [[540, 9, 0, 0], [608, 17, 0, 0]],
    "win": 1,
    "quest_id": "100000006",
    "map": 0,
    "resources": {"g": 1600, "x": 170},
}


def test_conquest_progress_is_recorded_and_saved(tmp_path, user):
    before_index = state(user)["privateState"].get("unlockedQuestIndex")
    before_coins = state(user)["maps"][0]["coins"]

    command_module.do_command(user, Constant.CMD_END_QUEST, [json.dumps(QUEST_PAYLOAD)])
    sessions.save_session(user)

    after_index = state(user)["privateState"]["unlockedQuestIndex"]
    assert int(after_index) >= int(before_index or 0)
    assert state(user)["maps"][0]["coins"] >= before_coins
    assert saved(tmp_path, user)["privateState"]["unlockedQuestIndex"] == after_index


def test_an_unlocked_quest_index_never_goes_backwards(user):
    """A repeated or replayed result must not undo the conquest."""
    command_module.do_command(user, Constant.CMD_END_QUEST, [json.dumps(QUEST_PAYLOAD)])
    reached = state(user)["privateState"]["unlockedQuestIndex"]

    older = dict(QUEST_PAYLOAD, quest_id="100000002")
    command_module.do_command(user, Constant.CMD_END_QUEST, [json.dumps(older)])

    assert state(user)["privateState"]["unlockedQuestIndex"] == reached
