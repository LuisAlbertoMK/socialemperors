import os
import sys

# Bundled data (extracted to a temp dir)

TMP_BUNDLED_DIR = getattr(sys, "_MEIPASS", ".")

ASSETS_DIR = os.path.join(TMP_BUNDLED_DIR, "assets")
STUB_DIR = os.path.join(TMP_BUNDLED_DIR, "stub")
TEMPLATES_DIR = os.path.join(TMP_BUNDLED_DIR, "templates")
VILLAGES_DIR = os.path.join(TMP_BUNDLED_DIR, "villages")
QUESTS_DIR = os.path.join(VILLAGES_DIR, "quests")
CONFIG_DIR = os.path.join(TMP_BUNDLED_DIR, "config")
CONFIG_PATCH_DIR = os.path.join(CONFIG_DIR, "patch")

# Not bundled data (next to the server)

def _resolve_base_dir() -> str:
    """Directory that holds the non-bundled data (saves/, mods/).

    In a frozen (PyInstaller) build the executable's own directory is the only
    stable anchor: the process working directory depends on how the exe was
    launched (double-click, shortcut, "open with"), so resolving saves/ and
    mods/ against "." would scatter player data wherever the launcher happened
    to point. Running from source keeps "." so the tests and ``python server.py``
    stay CWD-relative, exactly as before.
    """
    if getattr(sys, "frozen", None):
        return os.path.dirname(sys.executable)
    return "."


BASE_DIR = _resolve_base_dir()

MODS_DIR = os.path.join(BASE_DIR, "mods")
SAVES_DIR = os.path.join(BASE_DIR, "saves")
