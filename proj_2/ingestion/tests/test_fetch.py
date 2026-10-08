"""Fetch-stage tests with a mock transport: no network, no real sleeping."""

import httpx2
import pytest

from ingestion import fetch


@pytest.fixture
def sleeps(monkeypatch):
    calls = []
    monkeypatch.setattr(fetch.time, "sleep", calls.append)
    return calls


def client_for(handler, cls=fetch.NetNutritionClient):
    return cls(delay=1.0, http=httpx2.Client(transport=httpx2.MockTransport(handler)))


def responder(*responses):
    queue = list(responses)
    seen = []

    def handler(request):
        seen.append(request)
        return queue.pop(0)
    handler.seen = seen
    return handler


def test_retries_server_errors_with_backoff(sleeps):
    handler = responder(httpx2.Response(503), httpx2.Response(502), httpx2.Response(200, text="ok"))
    client = client_for(handler)
    assert client.request("GET", "https://example.test/").text == "ok"
    assert client.request_count == 3
    assert [s for s in sleeps if s >= 2] == [2.0, 4.0]  # delay * 2**attempt


def test_honors_retry_after(sleeps):
    handler = responder(httpx2.Response(429, headers={"Retry-After": "7"}), httpx2.Response(200))
    client_for(handler).request("GET", "https://example.test/")
    assert 7.0 in sleeps


def test_does_not_retry_not_found(sleeps):
    handler = responder(httpx2.Response(404))
    client = client_for(handler)
    with pytest.raises(fetch.FetchError, match="HTTP 404"):
        client.request("GET", "https://example.test/")
    assert client.request_count == 1


def test_gives_up_after_three_attempts(sleeps):
    handler = responder(*[httpx2.Response(500)] * 3)
    with pytest.raises(fetch.FetchError, match="gave up after 3 attempts"):
        client_for(handler).request("GET", "https://example.test/")


def test_delay_has_a_floor():
    assert fetch.NetNutritionClient(delay=0.0, http=httpx2.Client()).delay == fetch.MIN_DELAY_SECONDS


def test_panels_are_keyed_by_id_and_form_is_posted(sleeps):
    payload = {"success": True, "panels": [{"id": "menuPanel", "html": "<p>menus</p>"}, {"id": "x", "html": ""}]}
    handler = responder(httpx2.Response(200, json=payload))
    assert client_for(handler).select_unit(1) == {"menuPanel": "<p>menus</p>"}
    request = handler.seen[0]
    assert request.method == "POST"
    assert request.url.path.endswith("/Unit/SelectUnitFromUnitsList")
    assert request.content == b"unitOid=1"


def test_success_false_means_session_gone(sleeps):
    handler = responder(httpx2.Response(200, json={"success": False}))
    with pytest.raises(fetch.FetchError, match="success=false"):
        client_for(handler).select_menu(5)


def test_non_json_panel_response_is_a_fetch_error(sleeps):
    handler = responder(httpx2.Response(200, text="<html>error</html>"))
    with pytest.raises(fetch.FetchError, match="not JSON"):
        client_for(handler).select_menu(5)


def test_sends_identifying_user_agent():
    client = fetch.DiningSiteClient()
    assert client.http.headers["User-Agent"].startswith("PackPlate/")
    client.close()
