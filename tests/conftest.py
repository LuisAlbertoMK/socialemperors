"""Shared pytest fixtures for the Social Emperors server.

The application resolves its data paths relative to the process working
directory (``bundle.BASE_DIR`` is ``"."``), so every test session is pinned to
the repository root before the application modules are imported.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.chdir(ROOT)

import pytest  # noqa: E402 - must follow the path setup above

import sessions  # noqa: E402
from server import app  # noqa: E402
from sessions import new_village  # noqa: E402


@pytest.fixture
def client():
    """Flask test client with ``TESTING`` on, so view errors surface loudly."""
    app.config.update(TESTING=True)
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture
def user(tmp_path, monkeypatch):
    """A real save registered in memory, with its file written under ``tmp_path``.

    ``SAVES_DIR`` is redirected so tests never touch the developer's saves
    folder, and the in-memory entry is removed again afterwards.
    """
    monkeypatch.setattr(sessions, "SAVES_DIR", str(tmp_path))
    userid = new_village()
    yield userid
    sessions.__saves.pop(userid, None)
