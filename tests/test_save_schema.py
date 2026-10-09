"""The save schema the client reads.

The original server's own saves (``villages/quests/*.json``) are the reference for the
shape, and the client SWF strings say which fields it reads. Comparing both against
what this server writes showed 48 fields missing, 39 of which the client actually
reads: 26 in ``privateState``, 8 in the map and 5 in ``playerInfo``.

A missing field is not a crash: the client quietly shows nothing, which is what made
the newer clients look "experimental" while older ones seemed to work.

This file is the contract. If someone adds a field the client needs, it belongs in
these lists and in ``villages/initial.json``.
"""

import json

import pytest

# Read by both 0.9.26b and 1.1.5 unless noted.
PRIVATE_STATE_FIELDS = [
    "achievedUnits",
    "attacksLost",  # only 1.1.5
    "attacksPack",
    "attacksReceived",
    "attacksWon",
    "collectionsCompleted",
    "comebackBonusCollected",
    "countHack",
    "deadHeroes",
    "dragonSocialHelp",
    "fakeNeighbors",
    "helpMap",
    "honor",
    "honorPoints",
    "maps",
    "numFriends",  # only 1.1.5
    "receivedAssists",
    "spyings",
    "spyingsPack",
    "templeStep",
    "timeStampMondayBonus",
    "timeStampTemple",
    "tsAttacksReset",
    "tsSpyingsReset",
    "version",
    "worldChange",
]

MAP_FIELDS = [
    "currentQuestVars",
    "numTradesDone",
    "resourceAlliesMarket",
    "store",
    "timestampLastTrade",
    "unlockedEarlyBuildings",
    "warehousedUnits",
    "world_id",
]

PLAYER_INFO_FIELDS = ["coins", "food", "level", "stone", "wood"]


@pytest.fixture(scope="module")
def initial_village():
    with open("villages/initial.json", encoding="utf-8") as handle:
        return json.load(handle)


def test_a_new_village_has_every_private_state_field_the_client_reads(initial_village):
    missing = sorted(set(PRIVATE_STATE_FIELDS) - set(initial_village["privateState"]))

    assert missing == []


def test_a_new_village_has_every_map_field_the_client_reads(initial_village):
    missing = sorted(set(MAP_FIELDS) - set(initial_village["maps"][0]))

    assert missing == []


def test_a_new_village_has_the_player_summary_the_client_reads(initial_village):
    missing = sorted(set(PLAYER_INFO_FIELDS) - set(initial_village["playerInfo"]))

    assert missing == []


def test_the_player_summary_matches_the_first_map(initial_village):
    """The newer clients read the resources from playerInfo, the map holds the truth."""
    player = initial_village["playerInfo"]
    first_map = initial_village["maps"][0]

    for field in PLAYER_INFO_FIELDS:
        assert player[field] == first_map[field], field


def test_the_private_state_map_summary_describes_the_first_map(initial_village):
    """privateState.maps is [{name, race, size}] and the client shows it in the UI."""
    summary = initial_village["privateState"]["maps"]

    assert len(summary) == 1
    assert summary[0]["n"] == initial_village["playerInfo"]["map_names"][0]
    assert summary[0]["r"] == initial_village["maps"][0]["race"]
    assert summary[0]["s"] == 1
