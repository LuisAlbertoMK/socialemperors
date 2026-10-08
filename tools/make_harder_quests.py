"""Build a harder set of quest islands out of the originals.

The islands are mock villages whose ``map.items`` are
``[item_id, x, y, orientation, timestamp]``, and the item id selects the unit from
the game config. Swapping the weakest defenders for elite units that already exist
in the config makes an island harder without inventing anything and without moving
a single object.

The elite units are chosen from the **base** config, not from the patched one, so a
hard island never depends on a mod being enabled. The originals stay untouched:
changed islands are written to ``villages/quests_hard`` and the server only serves
them when ``SE_HARD_QUESTS=1``.

Usage:
    python tools/make_harder_quests.py [--share 0.25] [--cap 12] [--dry-run]
"""

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bundle import CONFIG_DIR, QUESTS_DIR

BASE_CONFIG = "game_config_20120826.json"
OUT_DIR_NAME = "quests_hard"
BOSS_FROM_ATTACK = 10000  # islands at or above this also get one boss


def load_base_config():
    with open(os.path.join(CONFIG_DIR, BASE_CONFIG), encoding="utf-8") as handle:
        return json.load(handle)


def stat(item, field):
    try:
        return int(item.get(field) or 0)
    except (TypeError, ValueError):
        return 0


def build_ladder(units):
    """Four elite unit ids from the base config, by attack band, deduplicated.

    Attack is what makes an island hard, so the ladder is ordered by it and not by
    life (the base config has a 6,000-life dragon with only 40 attack, which would
    sit above a 3,000-life one with 77). Dragons are preferred because that is what
    the request was about; with none available the bands still pick the strongest
    units there are.
    """
    dragons = [unit for unit in units if "dragon" in str(unit.get("name", "")).lower()]
    ordered = sorted(dragons or units, key=lambda unit: stat(unit, "attack"))
    ladder = []
    for ceiling in (60, 90, 150, None):
        if ceiling is None:
            candidate = ordered[-1]
        else:
            within = [unit for unit in ordered if stat(unit, "attack") <= ceiling]
            candidate = within[-1] if within else ordered[0]
        if candidate not in ladder:
            ladder.append(candidate)
    return ladder


def elite_for(ladder, total_attack):
    """The ladder step that matches how strong the island already is."""
    tier = 0
    for ceiling in (2000, 5000, 10000):
        if total_attack >= ceiling:
            tier += 1
    return ladder[min(tier, len(ladder) - 1)]


def replacements_that_fit(weakest, by_id, elite, attack_before, life_before, budget, life_budget):
    """How many defenders can be upgraded before the island grows past its budgets.

    Keeps the difficulty bump proportional. Attack is the primary budget because that
    is what makes an island hard, but life needs its own ceiling: replacing fragile
    defenders with dragons raises life far faster than attack, and an island with a
    huge attack and paper units would otherwise turn into a wall.
    """
    attack_limit = attack_before * budget
    life_limit = life_before * life_budget
    attack, life = attack_before, life_before
    count = 0
    for _index, item in weakest:
        current = by_id[str(item[0])]
        attack += stat(elite, "attack") - stat(current, "attack")
        life += stat(elite, "life") - stat(current, "life")
        if attack > attack_limit or life > life_limit:
            break
        count += 1
    return count


def pick_boss(units):
    """The strongest unit that is not a dragon: the game's own boss units."""
    others = [unit for unit in units if "dragon" not in str(unit.get("name", "")).lower()]
    if not others:
        return None
    return max(others, key=lambda unit: (stat(unit, "life"), stat(unit, "attack")))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--share", type=float, default=0.25,
                        help="maximum share of an island's units to replace")
    parser.add_argument("--cap", type=int, default=12,
                        help="maximum units to replace per island")
    parser.add_argument("--growth", type=float, default=1.5,
                        help="maximum attack growth per island (1.5 = +50%%)")
    parser.add_argument("--life-growth", type=float, default=5.0,
                        help="maximum life growth per island")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would change without writing files")
    args = parser.parse_args()

    base = load_base_config()
    by_id = {str(item["id"]): item for item in base["items"]}
    units = [item for item in base["items"] if str(item.get("type")) == "u"]
    ladder = build_ladder(units)
    boss = pick_boss(units)

    print("ladder from the base config:")
    for step in ladder:
        print(f"  {step['id']:>5} {str(step['name'])[:32]:34} "
              f"life={stat(step, 'life'):>6} attack={stat(step, 'attack'):>4}")
    print(f"boss: {boss['id']} {boss['name']} "
          f"life={stat(boss, 'life')} attack={stat(boss, 'attack')}\n")

    out_dir = os.path.join(os.path.dirname(QUESTS_DIR), OUT_DIR_NAME)
    if not args.dry_run:
        os.makedirs(out_dir, exist_ok=True)

    print(f"{'island':>10} {'name':<20} {'units':>5} {'repl':>4} {'attack':>8} -> {'attack':>8} "
          f"{'life':>8} -> {'life':>8}  elite")
    changed = 0
    skipped = []
    for path in sorted(glob.glob(os.path.join(QUESTS_DIR, "*.json"))):
        with open(path, encoding="utf-8") as handle:
            island = json.load(handle)
        items = island.get("map", {}).get("items")
        if not items:
            continue

        defenders = [(index, item) for index, item in enumerate(items)
                     if isinstance(item, list) and len(item) >= 5
                     and by_id.get(str(item[0]), {}).get("type") == "u"]
        if not defenders:
            continue

        unknown = sorted({str(item[0]) for _i, item in defenders if str(item[0]) not in by_id})
        if unknown:
            # Never write an island that points at a unit the base config lacks.
            skipped.append((os.path.basename(path), unknown))
            continue

        attack_before = sum(stat(by_id[str(item[0])], "attack") for _i, item in defenders)
        life_before = sum(stat(by_id[str(item[0])], "life") for _i, item in defenders)

        count = min(int(len(defenders) * args.share), args.cap)
        if count <= 0:
            continue
        weakest = sorted(defenders, key=lambda pair: stat(by_id[str(pair[1][0])], "life"))[:count]
        elite = elite_for(ladder, attack_before)
        count = replacements_that_fit(weakest, by_id, elite, attack_before, life_before,
                                      args.growth, args.life_growth)
        if count <= 0:
            continue
        weakest = weakest[:count]
        for _index, item in weakest:
            item[0] = int(elite["id"])
        if attack_before >= BOSS_FROM_ATTACK and boss is not None:
            # One of the game's bosses, where the weakest defender stood.
            weakest[0][1][0] = int(boss["id"])

        attack_after = sum(stat(by_id[str(item[0])], "attack") for _i, item in defenders)
        life_after = sum(stat(by_id[str(item[0])], "life") for _i, item in defenders)
        name = str(island.get("playerInfo", {}).get("name"))[:20]
        print(f"{os.path.basename(path):>10} {name:<20} {len(defenders):>5} {count:>4} "
              f"{attack_before:>8} -> {attack_after:>8} {life_before:>8} -> {life_after:>8}"
              f"  {elite['name']}")

        if not args.dry_run:
            with open(os.path.join(out_dir, os.path.basename(path)), "w",
                      encoding="utf-8") as handle:
                json.dump(island, handle, indent=1)
        changed += 1

    print(f"\nislands changed: {changed}")
    for name, unknown in skipped:
        print(f"skipped {name}: references units missing from the base config {unknown}")
    print("(dry run: nothing written)" if args.dry_run else f"written to: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
