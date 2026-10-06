"""Fetch: the only code that talks to the network.

Polite by design: one request at a time, at least REQUEST_DELAY_SECONDS apart,
an identifying User-Agent, and backed-off retries only for errors worth retrying.

NetNutrition is stateful. The first GET sets an ASP.NET session cookie, and every
click after that is a POST to <page>/<Controller>/<Action> (see the site's own
Scripts/cbord_nn_ui_repsonsive.js) answering
    {"success": true, "panels": [{"id": "menuPanel", "html": "..."}, ...]}
The server remembers the selected unit and menu, so calls must run in order:
select unit -> select menu -> labels for that menu. Never parallelize a session.
"""

import time
from datetime import date

import httpx2

from ingestion.config import (
    DINING_SITE_BASE,
    MAX_RETRY_AFTER_SECONDS,
    MIN_DELAY_SECONDS,
    NETNUTRITION_BASE,
    REQUEST_ATTEMPTS,
    REQUEST_DELAY_SECONDS,
    USER_AGENT,
)

RETRY_STATUSES = {429, 500, 502, 503, 504}


class FetchError(Exception):
    pass


def _retry_after(response: httpx2.Response) -> float | None:
    value = response.headers.get("Retry-After", "")
    return min(float(value), MAX_RETRY_AFTER_SECONDS) if value.isdigit() else None


class _PoliteClient:
    def __init__(self, delay: float = REQUEST_DELAY_SECONDS, attempts: int = REQUEST_ATTEMPTS,
                 http: httpx2.Client | None = None):
        self.delay = max(delay, MIN_DELAY_SECONDS)
        self.attempts = attempts
        self.http = http or httpx2.Client(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=30,
            default_encoding="utf-8",  # names contain curly quotes and dashes
        )
        self._last = 0.0
        self.request_count = 0

    def _wait(self):
        gap = time.monotonic() - self._last
        if gap < self.delay:
            time.sleep(self.delay - gap)
        self._last = time.monotonic()
        self.request_count += 1

    def request(self, method: str, url: str, **kw) -> httpx2.Response:
        """Send one request; retry timeouts, connection errors, 429 and 5xx with backoff."""
        for attempt in range(1, self.attempts + 1):
            self._wait()
            retry_after = None
            try:
                response = self.http.request(method, url, **kw)
            except httpx2.TransportError as e:
                problem = f"{type(e).__name__}: {e}"
            else:
                if response.status_code < 400:
                    return response
                problem = f"HTTP {response.status_code}"
                if response.status_code not in RETRY_STATUSES:
                    raise FetchError(f"{method} {url}: {problem}")
                retry_after = _retry_after(response)
            if attempt == self.attempts:
                raise FetchError(f"{method} {url}: {problem} (gave up after {attempt} attempts)")
            time.sleep(retry_after if retry_after is not None else self.delay * 2 ** attempt)
        raise AssertionError("unreachable")

    def close(self):
        self.http.close()


class NetNutritionClient(_PoliteClient):
    base = NETNUTRITION_BASE

    def start_session(self) -> str:
        """Start a fresh server session; returns the home page HTML (lists every unit)."""
        self.http.cookies.clear()
        return self.request("GET", self.base).text

    def _action(self, controller: str, action: str, data: dict) -> httpx2.Response:
        return self.request("POST", f"{self.base}/{controller}/{action}", data=data)

    def _panels(self, controller: str, action: str, data: dict) -> dict[str, str]:
        response = self._action(controller, action, data)
        try:
            payload = response.json()
        except ValueError as e:
            raise FetchError(f"{controller}/{action} {data}: response was not JSON") from e
        if not payload.get("success"):
            # The site's own JS reloads the page here; for us the session is gone.
            raise FetchError(f"{controller}/{action} {data}: success=false (session expired?)")
        return {p["id"]: p["html"] for p in payload.get("panels", []) if p.get("html")}

    def select_unit(self, unit_oid: int) -> dict[str, str]:
        return self._panels("Unit", "SelectUnitFromUnitsList", {"unitOid": unit_oid})

    def select_menu(self, menu_oid: int) -> dict[str, str]:
        return self._panels("Menu", "SelectMenu", {"menuOid": menu_oid})

    def nutrition_label(self, detail_oid: int) -> str:
        return self._action("NutritionDetail", "ShowItemNutritionLabel", {"detailOid": detail_oid}).text


class DiningSiteClient(_PoliteClient):
    def location_page(self, slug: str, on: date | None = None) -> str:
        """A dining.ncsu.edu location page; ?date= fills its "pick a date" hours box."""
        params = {"date": on.isoformat()} if on else None
        return self.request("GET", f"{DINING_SITE_BASE}/location/{slug}/", params=params).text
