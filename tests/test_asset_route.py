"""The asset route: bundled files, CDN fallback, and its import cost.

``urllib.request`` costs ~132 ms of the server's ~663 ms startup and is only
needed when an asset is missing from the bundle, so it must not be imported at
module scope. The route's three branches are characterised here so the change
stays behaviour-preserving.
"""

import subprocess
import sys
import urllib.error
import urllib.request

import server


def test_importing_the_server_does_not_pull_in_urllib_request():
    """A fresh interpreter must start without the CDN download machinery."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, server; print('urllib.request' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr[-500:]
    # server.py prints progress while importing, so only the last line answers.
    assert result.stdout.strip().splitlines()[-1] == "False", (
        "urllib.request was imported at module scope: "
        f"last line={result.stdout.strip().splitlines()[-1]!r}"
    )


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def test_bundled_asset_is_served_without_touching_the_network(
    client, tmp_path, monkeypatch
):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "swf").mkdir()
    (assets / "swf" / "present.swf").write_bytes(b"BUNDLED")
    monkeypatch.setattr(server, "ASSETS_DIR", str(assets))
    monkeypatch.setattr(server, "BASE_DIR", str(tmp_path))

    def explode(*_args, **_kwargs):
        raise AssertionError("bundled assets must not be fetched from the CDN")

    monkeypatch.setattr(urllib.request, "urlopen", explode)

    response = client.get(
        "/default01.static.socialpointgames.com/static/socialempires/swf/present.swf"
    )

    assert response.status_code == 200
    assert response.get_data() == b"BUNDLED"


def test_missing_asset_is_downloaded_from_the_cdn(client, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "ASSETS_DIR", str(tmp_path / "empty-assets"))
    monkeypatch.setattr(server, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda url, timeout=None: FakeResponse(b"FROMCDN")
    )

    response = client.get(
        "/default01.static.socialpointgames.com/static/socialempires/units/missing.swf"
    )

    assert response.status_code == 200
    assert response.get_data() == b"FROMCDN"
    assert (tmp_path / "download_assets" / "assets" / "units" / "missing.swf").read_bytes() == b"FROMCDN"


def test_missing_asset_returns_404_when_the_cdn_fails(client, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "ASSETS_DIR", str(tmp_path / "empty-assets"))
    monkeypatch.setattr(server, "BASE_DIR", str(tmp_path))

    def offline(url, timeout=None):
        raise urllib.error.URLError("no network")

    monkeypatch.setattr(urllib.request, "urlopen", offline)

    response = client.get(
        "/default01.static.socialpointgames.com/static/socialempires/units/missing.swf"
    )

    assert response.status_code == 404


def test_cdn_http_errors_are_also_a_404(client, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "ASSETS_DIR", str(tmp_path / "empty-assets"))
    monkeypatch.setattr(server, "BASE_DIR", str(tmp_path))
    http_404 = urllib.error.HTTPError("u", 404, "nope", None, None)

    def http_error(url, timeout=None):
        raise http_404

    monkeypatch.setattr(urllib.request, "urlopen", http_error)

    response = client.get(
        "/default01.static.socialpointgames.com/static/socialempires/units/gone.swf"
    )

    assert response.status_code == 404


def test_a_failed_download_never_leaves_a_partial_asset_behind(
    client, tmp_path, monkeypatch
):
    """A half-written asset would later be served from cache as a corrupt file."""
    monkeypatch.setattr(server, "ASSETS_DIR", str(tmp_path / "empty-assets"))
    monkeypatch.setattr(server, "BASE_DIR", str(tmp_path))

    class BrokenResponse:
        def read(self):
            raise OSError("connection dropped mid-download")

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    monkeypatch.setattr(
        urllib.request, "urlopen", lambda url, timeout=None: BrokenResponse()
    )

    response = client.get(
        "/default01.static.socialpointgames.com/static/socialempires/units/broken.swf"
    )

    assert response.status_code == 404
    assert not (tmp_path / "download_assets" / "assets" / "units" / "broken.swf").exists()
