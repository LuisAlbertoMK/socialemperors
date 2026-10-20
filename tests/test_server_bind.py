"""Bind address contract: loopback by default, LAN only on explicit opt-in.

``command.php`` authenticates by the ``USERID`` in the request, so binding
``0.0.0.0`` by default would expose every save to every device on the network.
The documented way to play is ``http://127.0.0.1:5050/``; LAN play is an
explicit decision.
"""

import server


def test_bind_host_defaults_to_loopback(monkeypatch):
    monkeypatch.delenv("SE_HOST", raising=False)
    assert server._bind_host() == "127.0.0.1"


def test_bind_host_can_opt_into_lan(monkeypatch):
    monkeypatch.setenv("SE_HOST", "0.0.0.0")
    assert server._bind_host() == "0.0.0.0"
