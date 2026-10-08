"""The game-config pipeline: base config, patch files, and mods.txt.

``mods.txt`` documents that the ``.json`` extension is optional in its listing,
so both spellings must resolve to the same mod file.
"""

import copy
import json

import get_game_config


def build_mods_dir(tmp_path, listing, mod_files):
    """A private mods directory plus an empty patches directory."""
    mods = tmp_path / "mods"
    mods.mkdir()
    patches = tmp_path / "patches"
    patches.mkdir()
    for name, patch in mod_files.items():
        (mods / name).write_text(json.dumps(patch), encoding="utf-8")
    (mods / "mods.txt").write_text(listing, encoding="utf-8")
    return mods, patches


def isolated_config(monkeypatch, mods, patches):
    """Point the pipeline at temp directories and at a throwaway config copy."""
    monkeypatch.setattr(get_game_config, "MODS_DIR", str(mods))
    monkeypatch.setattr(get_game_config, "CONFIG_PATCH_DIR", str(patches))
    detached = copy.deepcopy(get_game_config.get_game_config())
    monkeypatch.setattr(get_game_config, "__game_config", detached)
    return detached


SET_XP_PATCH = [{"op": "replace", "path": "/levels/0/exp_required", "value": 7}]


def test_mod_listed_without_extension_is_applied(monkeypatch, tmp_path):
    mods, patches = build_mods_dir(
        tmp_path, "renamer\n", {"renamer.json": SET_XP_PATCH}
    )
    config = isolated_config(monkeypatch, mods, patches)

    get_game_config.patch_game_config()

    assert config["levels"][0]["exp_required"] == 7


def test_mod_listed_with_its_extension_is_still_applied(monkeypatch, tmp_path):
    """mods.txt says the extension is optional, so 'renamer.json' must work."""
    mods, patches = build_mods_dir(
        tmp_path, "renamer.json\n", {"renamer.json": SET_XP_PATCH}
    )
    config = isolated_config(monkeypatch, mods, patches)

    get_game_config.patch_game_config()

    assert config["levels"][0]["exp_required"] == 7


def test_comment_and_blank_lines_are_ignored(monkeypatch, tmp_path):
    mods, patches = build_mods_dir(
        tmp_path, "# disabled\n\n   \nrenamer\n", {"renamer.json": SET_XP_PATCH}
    )
    config = isolated_config(monkeypatch, mods, patches)

    get_game_config.patch_game_config()

    assert config["levels"][0]["exp_required"] == 7


def test_mod_listed_but_missing_on_disk_is_skipped_without_crashing(
    monkeypatch, tmp_path
):
    mods, patches = build_mods_dir(
        tmp_path, "does_not_exist\nrenamer\n", {"renamer.json": SET_XP_PATCH}
    )
    config = isolated_config(monkeypatch, mods, patches)

    get_game_config.patch_game_config()

    assert config["levels"][0]["exp_required"] == 7
