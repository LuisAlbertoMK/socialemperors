"""``bundle.py`` anchors saves/ and mods/ to the right directory.

Running from source keeps the working directory (so tests and ``python
server.py`` behave as before). A frozen build must anchor to the executable's
own directory: the process working directory depends on how the exe was launched
(double-click, shortcut, "open with"), so resolving against "." would scatter
player data wherever the launcher happened to point.
"""

import os
import subprocess
import sys

import bundle


def test_source_run_uses_the_working_directory(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert bundle._resolve_base_dir() == "."


def test_frozen_build_uses_the_executable_directory(monkeypatch):
    executable = os.path.join("C:" + os.sep, "games", "social-emperors.exe")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", executable)

    assert bundle._resolve_base_dir() == os.path.dirname(executable)


def test_saves_and_mods_are_derived_from_base_dir():
    assert os.path.join(bundle.BASE_DIR, "saves") == bundle.SAVES_DIR
    assert os.path.join(bundle.BASE_DIR, "mods") == bundle.MODS_DIR


def test_frozen_import_reads_meipass_and_the_executable_directory():
    """The real frozen import path, in a fresh interpreter.

    ``sys.frozen`` alone is not enough for bundled data: a frozen runtime
    exposes ``sys._MEIPASS``, and reading it unguarded crashed before. Bundled
    data must come from ``_MEIPASS`` (a temp dir) while saves/mods stay next to
    the executable.
    """
    script = (
        "import sys; "
        "sys.frozen = True; "
        "sys._MEIPASS = 'MEIPASS_DIR'; "
        "sys.executable = 'EXE_DIR/server.exe'; "
        "import bundle; "
        "print(bundle.TMP_BUNDLED_DIR); print(bundle.BASE_DIR); print(bundle.ASSETS_DIR)"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True
    )

    assert result.returncode == 0, result.stderr
    meipass, base, assets = result.stdout.split()
    assert meipass == "MEIPASS_DIR"
    assert base == os.path.dirname("EXE_DIR/server.exe")
    assert assets == os.path.join("MEIPASS_DIR", "assets")
