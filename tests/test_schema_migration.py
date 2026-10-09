"""Migrating existing saves to the fields the client reads.

Adding the fields to ``villages/initial.json`` only helps new villages. A save that
already exists (the player's own is at 0.05a) needs a migration step, and that step
must be safe: it fills what is missing and never overwrites a value the player earned.
"""

import copy

import version

SAVE = {
    "version": "0.05a",
    "playerInfo": {
        "pid": "test-player",
        "map_names": ["My Empire"],
        "default_map": 0,
        "cash": 500,
    },
    "maps": [
        {
            "id": 0,
            "race": "h",
            "coins": 1234,
            "food": 700,
            "level": 40,
            "stone": 250,
            "wood": 850,
            "items": [],
        }
    ],
    "privateState": {"gifts": [], "honor": 7},
}


def test_an_existing_save_gets_the_fields_the_client_reads():
    save = copy.deepcopy(SAVE)

    assert version.migrate_loaded_save(save) is True

    for field in ("deadHeroes", "collectionsCompleted", "spyings", "honorPoints"):
        assert field in save["privateState"], field
    assert "store" in save["maps"][0]
    for field in ("coins", "food", "level", "stone", "wood"):
        assert field in save["playerInfo"], field


def test_the_migration_never_overwrites_a_value_the_player_earned():
    save = copy.deepcopy(SAVE)
    save["privateState"]["honor"] = 7

    version.migrate_loaded_save(save)

    assert save["privateState"]["honor"] == 7


def test_the_player_summary_mirrors_the_map():
    save = copy.deepcopy(SAVE)

    version.migrate_loaded_save(save)

    assert save["playerInfo"]["coins"] == save["maps"][0]["coins"]
    assert save["playerInfo"]["level"] == save["maps"][0]["level"]


def test_the_private_state_map_summary_matches_the_save():
    save = copy.deepcopy(SAVE)

    version.migrate_loaded_save(save)

    summary = save["privateState"]["maps"]
    assert summary[0]["n"] == "My Empire"
    assert summary[0]["r"] == "h"


def test_the_migration_converges():
    save = copy.deepcopy(SAVE)

    assert version.migrate_loaded_save(save) is True
    assert version.migrate_loaded_save(save) is False
    assert save["version"] == version.version_code


def test_a_save_that_already_has_everything_is_still_marked_current():
    """A 0.05b save is left alone, but a 0.05a one must reach the current version."""
    save = copy.deepcopy(SAVE)
    version.migrate_loaded_save(save)
    already_current = copy.deepcopy(save)

    assert version.migrate_loaded_save(already_current) is False
    assert already_current == save


def test_the_oldest_save_walks_the_whole_chain_and_ends_up_with_everything():
    save = copy.deepcopy(SAVE)
    save["version"] = "0.01a"

    assert version.migrate_loaded_save(save) is True
    assert save["version"] == version.version_code
    assert "deadHeroes" in save["privateState"]
    assert "store" in save["maps"][0]
    assert "coins" in save["playerInfo"]
