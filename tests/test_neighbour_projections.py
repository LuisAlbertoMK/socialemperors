"""Characterisation tests for the neighbour and friend projections.

``neighbors()`` and ``fb_friends_str()`` are two views over the same population:
static villages first, then saved ones. These tests pin the exact contract before
the duplication is folded into one helper.
"""

import copy
import json

import pytest

import sessions
from constants import Constant

REQUESTER = "me"
DERIVED_RESOURCE_KEYS = {"coins", "xp", "level", "stone", "wood", "food"}
PIC_FALLBACK = "/img/profile/1025.png"


def make_village(pid, name, pic, resources):
    with open("villages/initial.json", encoding="utf-8") as template:
        village = json.load(template)
    village["playerInfo"]["pid"] = pid
    village["playerInfo"]["map_names"] = [name]
    village["playerInfo"]["pic"] = pic
    village["playerInfo"]["default_map"] = 0
    village["maps"][0].update(resources)
    return village


RESOURCES_A = {"coins": 11, "wood": 22, "food": 33, "stone": 44, "xp": 55, "level": 6}
RESOURCES_B = {"coins": 111, "wood": 222, "food": 333, "stone": 444, "xp": 555, "level": 60}
RESOURCES_ME = {"coins": 1, "wood": 2, "food": 3, "stone": 4, "xp": 5, "level": 1}


@pytest.fixture
def known_world():
    """Two static villages (one is Arthur) and two saves (one is the requester)."""
    villages = {
        "static-neighbour": make_village("static-neighbour", "Static", "static.png", RESOURCES_A),
        Constant.NEIGHBOUR_ARTHUR_GUINEVERE_1: make_village(
            Constant.NEIGHBOUR_ARTHUR_GUINEVERE_1, "Arthur", "", RESOURCES_B
        ),
    }
    saves = {
        REQUESTER: make_village(REQUESTER, "Mine", "me.png", RESOURCES_ME),
        "other": make_village("other", "Other", "other.png", RESOURCES_B),
    }
    previous_villages = dict(sessions.__villages)
    previous_saves = dict(sessions.__saves)
    sessions.__villages.clear()
    sessions.__villages.update(copy.deepcopy(villages))
    sessions.__saves.clear()
    sessions.__saves.update(copy.deepcopy(saves))
    yield
    sessions.__villages.clear()
    sessions.__villages.update(previous_villages)
    sessions.__saves.clear()
    sessions.__saves.update(previous_saves)


def test_neighbors_lists_static_villages_first_then_saves(known_world):
    listed = sessions.neighbors(REQUESTER)

    assert [entry["pid"] for entry in listed] == ["static-neighbour", "other"]


def test_neighbors_carries_the_derived_resources_of_the_first_map(known_world):
    by_pid = {entry["pid"]: entry for entry in sessions.neighbors(REQUESTER)}

    for pid, resources in (("static-neighbour", RESOURCES_A), ("other", RESOURCES_B)):
        for key, value in resources.items():
            assert by_pid[pid][key] == value, f"{pid}.{key}"


def test_neighbors_is_the_player_info_plus_the_derived_resources(known_world):
    source = sessions.__villages["static-neighbour"]["playerInfo"]
    entry = sessions.neighbors(REQUESTER)[0]

    assert set(entry) == set(source) | DERIVED_RESOURCE_KEYS
    assert entry["map_names"] == source["map_names"]


def test_friends_exclude_the_requester_and_use_a_picture_fallback(known_world):
    friends = sessions.fb_friends_str(REQUESTER)

    assert [friend["uid"] for friend in friends] == ["static-neighbour", "other"]
    assert friends[0]["pic_square"] == "static.png"
    assert friends[1]["pic_square"] == "other.png"


def test_friends_fall_back_when_a_player_has_no_picture(known_world):
    sessions.__villages["static-neighbour"]["playerInfo"]["pic"] = ""

    friends = sessions.fb_friends_str(REQUESTER)

    assert friends[0]["pic_square"] == PIC_FALLBACK


def test_arthur_is_never_listed_as_a_neighbour_or_friend(known_world):
    arthur = Constant.NEIGHBOUR_ARTHUR_GUINEVERE_1

    assert arthur not in [entry["pid"] for entry in sessions.neighbors(REQUESTER)]
    assert arthur not in [friend["uid"] for friend in sessions.fb_friends_str(REQUESTER)]


def test_arthur_is_not_listed_even_when_it_is_a_save(known_world):
    """The client fetches the story islands through the quest endpoint."""
    arthur = Constant.NEIGHBOUR_ARTHUR_GUINEVERE_1
    sessions.__saves[arthur] = make_village(arthur, "Arthur", "", RESOURCES_B)

    assert arthur not in [entry["pid"] for entry in sessions.neighbors(REQUESTER)]
    assert arthur not in [friend["uid"] for friend in sessions.fb_friends_str(REQUESTER)]
