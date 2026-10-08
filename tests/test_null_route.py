"""Regression tests for the flash-client recovery routes.

``/null`` is the endpoint the Flash client hits when it has already lost sync
(``flash_sync_error``, ``flash_reload_quest``, ``flash_reload_attack``), so it
must always answer with a usable redirect instead of an exception.
"""

REDIRECT_TARGET = "/play.html"


def test_null_route_redirects_for_known_sync_error(client):
    response = client.get("/null?sp_ref_cat=flash_sync_error")

    assert response.status_code == 302
    assert response.headers["Location"].endswith(REDIRECT_TARGET)


def test_null_route_redirects_for_unknown_ref_cat(client):
    response = client.get("/null?sp_ref_cat=not_a_known_category")

    assert response.status_code == 302
    assert response.headers["Location"].endswith(REDIRECT_TARGET)


def test_null_route_redirects_when_ref_cat_is_missing(client):
    response = client.get("/null")

    assert response.status_code == 302
    assert response.headers["Location"].endswith(REDIRECT_TARGET)
