"""Asset loader hardening.

The CDN fallback writes whatever it downloads to a path derived from the URL,
so two properties matter:

- a crafted ``..`` path must never resolve (or write) outside the data dir;
- creating the target directory must be idempotent, because two cold requests
  can race between the ``exists`` check and the ``mkdir``.
"""

import os

import pytest

import server

BASE = "/default01.static.socialpointgames.com/static/socialempires"


def test_safe_join_keeps_nested_paths_inside(tmp_path):
    resolved = server._safe_join(str(tmp_path), "swf/asset.swf")
    assert resolved == os.path.realpath(str(tmp_path / "swf" / "asset.swf"))


@pytest.mark.parametrize("path", ["../evil.bin", "swf/../../evil.bin", ".."])
def test_safe_join_rejects_traversal(tmp_path, path):
    assert server._safe_join(str(tmp_path), path) is None


def test_asset_view_rejects_traversal_without_fetching(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "BASE_DIR", str(tmp_path))
    fetched = []
    monkeypatch.setattr(
        server, "_download_asset", lambda url, destination: fetched.append(destination) or True
    )

    with server.app.test_request_context("/"):
        assert server.static_assets_loader("../../evil.bin") == ("", 404)

    assert fetched == []


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_download_asset_creates_target_directory_idempotently(tmp_path, monkeypatch):
    """The mkdir must survive the directory already existing (the losing racer)."""
    import urllib.request

    monkeypatch.setattr(
        urllib.request, "urlopen", lambda *args, **kwargs: _FakeResponse(b"payload")
    )

    destination = tmp_path / "nested" / "asset.bin"
    destination.parent.mkdir()

    real_exists = os.path.exists

    def exists_always_false(path):
        if os.path.realpath(str(path)) == os.path.realpath(str(destination.parent)):
            return False
        return real_exists(path)

    monkeypatch.setattr(os.path, "exists", exists_always_false)

    assert server._download_asset("https://example.invalid/asset.bin", str(destination))
    assert destination.read_bytes() == b"payload"
