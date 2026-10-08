"""The optional harder quest islands.

``tools/make_harder_quests.py`` writes upgraded copies of some islands to
``villages/quests_hard`` and the originals stay untouched, so these tests check two
different things: that a generated island is the original island with stronger
defenders in the very same places, and that the server only serves it when
``SE_HARD_QUESTS`` is on.
"""

import json
import os

import pytest

import quests
from bundle import QUESTS_DIR


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def base_items():
    from get_game_config import get_game_config

    config = get_game_config()
    return {str(item["id"]): item for item in config["items"]}


def hard_files():
    if not os.path.isdir(quests.HARD_QUESTS_DIR):
        return []
    return sorted(
        os.path.join(quests.HARD_QUESTS_DIR, name)
        for name in os.listdir(quests.HARD_QUESTS_DIR)
        if name.endswith(".json")
    )


def defender_attack(island, by_id):
    total = 0
    for item in island["map"]["items"]:
        if isinstance(item, list) and len(item) >= 5:
            unit = by_id.get(str(item[0]), {})
            if str(unit.get("type")) == "u":
                total += int(unit.get("attack") or 0)
    return total


def test_there_is_something_to_check():
    assert hard_files(), "no generated islands: run tools/make_harder_quests.py"


@pytest.mark.parametrize("path", hard_files(), ids=os.path.basename)
def test_the_hard_variant_keeps_every_object_in_place(path):
    original = load(os.path.join(QUESTS_DIR, os.path.basename(path)))
    harder = load(path)

    assert len(harder["map"]["items"]) == len(original["map"]["items"])
    for before, after in zip(original["map"]["items"], harder["map"]["items"], strict=True):
        # Same position and orientation: only the item id may change.
        assert before[1:5] == after[1:5]


@pytest.mark.parametrize("path", hard_files(), ids=os.path.basename)
def test_the_hard_variant_never_touches_scenery(path):
    by_id = base_items()
    original = load(os.path.join(QUESTS_DIR, os.path.basename(path)))
    harder = load(path)

    for before, after in zip(original["map"]["items"], harder["map"]["items"], strict=True):
        if str(by_id.get(str(before[0]), {}).get("type")) != "u":
            assert before[0] == after[0]


@pytest.mark.parametrize("path", hard_files(), ids=os.path.basename)
def test_the_hard_variant_only_uses_units_from_the_base_config(path):
    by_id = base_items()
    harder = load(path)

    unknown = {
        str(item[0])
        for item in harder["map"]["items"]
        if isinstance(item, list) and str(item[0]) not in by_id
    }
    assert unknown == set()


@pytest.mark.parametrize("path", hard_files(), ids=os.path.basename)
def test_the_hard_variant_is_harder(path):
    by_id = base_items()
    original = load(os.path.join(QUESTS_DIR, os.path.basename(path)))
    harder = load(path)

    assert defender_attack(harder, by_id) > defender_attack(original, by_id)


def test_the_server_serves_the_original_by_default(monkeypatch):
    monkeypatch.setattr(quests, "HARD_QUESTS", False)
    monkeypatch.setattr(quests, "_quest_cache", {})
    questid = os.path.basename(hard_files()[0]).removesuffix(".json")

    served, status = quests.get_quest_map(questid)

    assert status == 200
    assert served == load(os.path.join(QUESTS_DIR, f"{questid}.json"))


def test_the_server_serves_the_hard_variant_when_enabled(monkeypatch):
    monkeypatch.setattr(quests, "HARD_QUESTS", True)
    monkeypatch.setattr(quests, "_quest_cache", {})
    questid = os.path.basename(hard_files()[0]).removesuffix(".json")

    served, status = quests.get_quest_map(questid)

    assert status == 200
    assert served == load(os.path.join(quests.HARD_QUESTS_DIR, f"{questid}.json"))


def test_an_island_without_a_hard_variant_falls_back(monkeypatch):
    monkeypatch.setattr(quests, "HARD_QUESTS", True)
    monkeypatch.setattr(quests, "_quest_cache", {})
    originals = {
        name.removesuffix(".json")
        for name in os.listdir(QUESTS_DIR)
        if name.endswith(".json")
    }
    without = sorted(originals - {os.path.basename(p).removesuffix(".json") for p in hard_files()})
    if not without:
        pytest.skip("every island has a hard variant")

    served, status = quests.get_quest_map(without[0])

    assert status == 200
    assert served == load(os.path.join(QUESTS_DIR, f"{without[0]}.json"))
