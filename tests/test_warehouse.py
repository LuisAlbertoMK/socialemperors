"""The warehouse commands, which the client sends and the server used to drop.

Evidence, all from this repository:

- captured payloads from a real session: ``store_item_frombug [57, 59, 0, 4]``,
  ``place_stored_item [5, 68, 33, 0, 0]`` and ``sell_stored_item [299, 0]``, none of
  which had a branch in ``command.py``.
- the storage shape is proven by the original server's own saves
  (``villages/quests/100000023.json``): ``map.store == {"141": 1, "57": 1, ...}``, a
  mapping of item id (as a string) to how many are stored. The player's save has
  ``store: null``, so the field was never even created.
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


def store_of(userid):
    return state(userid)["privateState"].get("store")


def put_item_on_map(userid, item_id, x, y, level=0):
    state(userid)["maps"][0]["items"].append([item_id, x, y, 0, 0, level])


def test_storing_an_item_removes_it_from_the_map(user):
    put_item_on_map(user, 4, 57, 59)

    command_module.do_command(user, Constant.CMD_STORE_ITEM_FROMBUG, [57, 59, 0, 4])

    assert not [i for i in state(user)["maps"][0]["items"] if i[0] == 4 and i[1] == 57]
    assert store_of(user) == {"4": 1}


def test_the_warehouse_matches_the_original_servers_shape(user):
    """The original saves key the warehouse by item id as a string, not an int."""
    put_item_on_map(user, 141, 10, 10)

    command_module.do_command(user, Constant.CMD_STORE_ITEM_FROMBUG, [10, 10, 0, 141])

    assert json.loads(json.dumps(store_of(user))) == {"141": 1}
    assert all(isinstance(key, str) for key in store_of(user))


def test_storing_the_same_item_twice_counts_two(user):
    put_item_on_map(user, 141, 10, 10)
    put_item_on_map(user, 141, 11, 10)

    command_module.do_command(user, Constant.CMD_STORE_ITEM_FROMBUG, [10, 10, 0, 141])
    command_module.do_command(user, Constant.CMD_STORE_ITEM_FROMBUG, [11, 10, 0, 141])

    assert store_of(user)["141"] == 2


def test_storing_something_that_is_not_there_changes_nothing(user):
    command_module.do_command(user, Constant.CMD_STORE_ITEM_FROMBUG, [99, 99, 0, 141])

    assert store_of(user) in (None, {})


def test_placing_a_stored_item_takes_it_out_and_puts_it_on_the_map(user):
    put_item_on_map(user, 5, 10, 10)
    command_module.do_command(user, Constant.CMD_STORE_ITEM_FROMBUG, [10, 10, 0, 5])

    command_module.do_command(user, Constant.CMD_PLACE_STORED_ITEM, [5, 68, 33, 0, 0])

    placed = [i for i in state(user)["maps"][0]["items"] if i[0] == 5 and i[1] == 68]
    assert placed, "the item should be back on the map"
    assert placed[0][2] == 33
    assert store_of(user) == {}


def test_placing_an_item_that_is_not_stored_changes_nothing(user):
    command_module.do_command(user, Constant.CMD_PLACE_STORED_ITEM, [999, 1, 1, 0, 0])

    assert not [i for i in state(user)["maps"][0]["items"] if i[0] == 999]


def test_selling_a_stored_item_removes_one_from_the_warehouse(user):
    put_item_on_map(user, 299, 10, 10)
    put_item_on_map(user, 299, 11, 10)
    command_module.do_command(user, Constant.CMD_STORE_ITEM_FROMBUG, [10, 10, 0, 299])
    command_module.do_command(user, Constant.CMD_STORE_ITEM_FROMBUG, [11, 10, 0, 299])

    command_module.do_command(user, Constant.CMD_SELL_STORED, [299, 0])

    assert store_of(user)["299"] == 1


def test_selling_the_last_one_leaves_no_empty_slot(user):
    put_item_on_map(user, 416, 10, 10)
    command_module.do_command(user, Constant.CMD_STORE_ITEM_FROMBUG, [10, 10, 0, 416])

    command_module.do_command(user, Constant.CMD_SELL_STORED, [416, 0])

    assert store_of(user) == {}


def test_the_warehouse_survives_a_reload(tmp_path, user):
    put_item_on_map(user, 141, 10, 10)
    command_module.do_command(user, Constant.CMD_STORE_ITEM_FROMBUG, [10, 10, 0, 141])

    sessions.save_session(user)

    with open(tmp_path / "saves" / f"{user}.save.json", encoding="utf-8") as handle:
        saved = json.load(handle)
    assert saved["privateState"]["store"] == {"141": 1}
