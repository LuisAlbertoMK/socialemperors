"""``CMD_ADD_COLLECTABLE``: the unit-collection state the client reports.

Everything here is grounded in captured evidence, not in guesses:

- captured payloads from a real session: ``args=[16, 1]`` and ``args=[16, 4]``
- the config's ``units_collections_categories["16"]`` is
  ``{"units": [529, 547, 530, 531, 589], "rewards": 589, ...}``, so index ``4``
  the client reported is exactly that collection's reward unit
- an original-server snapshot (``villages/quests/100000047.json``) stores
  ``privateState.collections`` as a list indexed by collection id, each slot a
  list of collected ids: ``[[], ..., [0, 1]]`` with the value at index 18

The player's own save has ``collections: null`` and the two captured pickups left
no trace in it, which is the observable damage this implementation fixes.
"""

import json

import pytest

import command as command_module
import sessions
from constants import Constant

CATEGORY_WITH_EVIDENCE = 16  # units [529, 547, 530, 531, 589], reward 589


@pytest.fixture
def user(tmp_path, monkeypatch):
    monkeypatch.setattr(sessions, "SAVES_DIR", str(tmp_path))
    userid = sessions.new_village()
    yield userid
    sessions.__saves.pop(userid, None)


def collect(userid, collection_id, collectible_id):
    command_module.do_command(
        userid, Constant.CMD_ADD_COLLECTABLE, [collection_id, collectible_id]
    )


def stored_collections(userid):
    return sessions.session(userid)["privateState"].get("collections")


def test_picking_up_a_collectible_is_recorded(user):
    collect(user, CATEGORY_WITH_EVIDENCE, 1)

    stored = stored_collections(user)

    assert stored[CATEGORY_WITH_EVIDENCE] == [1]
    assert len(stored) == CATEGORY_WITH_EVIDENCE + 1
    assert all(slot == [] for slot in stored[:CATEGORY_WITH_EVIDENCE])


def test_the_two_captured_pickups_accumulate_in_order(user):
    collect(user, CATEGORY_WITH_EVIDENCE, 1)
    collect(user, CATEGORY_WITH_EVIDENCE, 4)

    assert stored_collections(user)[CATEGORY_WITH_EVIDENCE] == [1, 4]


def test_receiving_the_same_pickup_twice_does_not_duplicate_it(user):
    """The envelope carries a retry counter and payloads can be re-flushed."""
    collect(user, CATEGORY_WITH_EVIDENCE, 1)
    collect(user, CATEGORY_WITH_EVIDENCE, 1)

    assert stored_collections(user)[CATEGORY_WITH_EVIDENCE] == [1]


def test_an_empty_or_missing_slot_is_repaired(user):
    """Saves written before this command worked have no collections at all."""
    sessions.session(user)["privateState"]["collections"] = None

    collect(user, CATEGORY_WITH_EVIDENCE, 4)

    assert stored_collections(user)[CATEGORY_WITH_EVIDENCE] == [4]


def test_the_list_grows_on_demand_for_any_real_category(user):
    collect(user, 3, 0)
    collect(user, 20, 2)

    stored = stored_collections(user)

    assert len(stored) == 21
    assert stored[3] == [0]
    assert stored[20] == [2]


def test_an_unknown_collection_is_ignored_without_touching_the_save(user):
    collect(user, 100000, 0)

    assert stored_collections(user) is None


def test_an_out_of_range_collectible_is_ignored(user):
    # Category 16 has five units, so index 99 cannot exist.
    collect(user, CATEGORY_WITH_EVIDENCE, 99)

    assert stored_collections(user) is None


def test_the_pickup_reaches_the_save_file(user, tmp_path):
    collect(user, CATEGORY_WITH_EVIDENCE, 4)

    sessions.save_session(user)

    saved = json.loads((tmp_path / f"{user}.save.json").read_text(encoding="utf-8"))
    assert saved["privateState"]["collections"][CATEGORY_WITH_EVIDENCE] == [4]
