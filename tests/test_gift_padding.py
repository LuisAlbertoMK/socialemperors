"""The gift-array padding shared by three commands.

``CMD_STORE_ITEM``, ``CMD_WIN_BONUS`` and ``CMD_BUY_SUPER_OFFER_PACK`` all grow
``privateState.gifts`` with zeros up to some item index. They used a
``for _ in range(n): append(0)`` loop and now use ``extend([0] * n)``; these
tests pin the resulting shape.

Note on argument types: the client sends command arguments already typed (ints
for ids, coordinates and map indices, a CSV string for item lists), which is why
branches that do not convert still work.
"""

import pytest

import command as command_module
import sessions
from constants import Constant


@pytest.fixture
def user(tmp_path, monkeypatch):
    monkeypatch.setattr(sessions, "SAVES_DIR", str(tmp_path))
    userid = sessions.new_village()
    sessions.session(userid)["privateState"]["gifts"] = []
    yield userid
    sessions.__saves.pop(userid, None)


def test_super_offer_pack_pads_the_gifts_array_up_to_the_highest_item(user):
    command_module.do_command(
        user, Constant.CMD_BUY_SUPER_OFFER_PACK, [0, 0, "3,5", 0]
    )

    assert sessions.session(user)["privateState"]["gifts"] == [0, 0, 0, 1, 0, 1]


def test_store_item_pads_and_increments_a_single_slot(user):
    command_module.do_command(user, Constant.CMD_STORE_ITEM, [10, 20, 0, 2])

    assert sessions.session(user)["privateState"]["gifts"] == [0, 0, 1]


def test_storing_an_item_without_a_gift_slot_keeps_the_array_short(user):
    """The low index case: no padding happens at all."""
    command_module.do_command(user, Constant.CMD_STORE_ITEM, [10, 20, 0, 0])

    assert sessions.session(user)["privateState"]["gifts"] == [1]
