"""/freshness and /health against the test database."""

from datetime import datetime, timezone

from app.services.freshness import STALE_AFTER_HOURS

FINISHED = datetime(2026, 10, 6, 8, 0, tzinfo=timezone.utc)   # 4am campus time


def test_no_runs_is_stale(client, seed):
    body = client.get("/freshness").json()
    assert body == {"last_run_finished_at": None, "last_run_status": None,
                    "stale": True, "stale_after_hours": STALE_AFTER_HOURS}


def test_latest_completed_run_decides_freshness(client, seed):
    seed.run("ok", FINISHED)
    seed.run("partial", datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc))
    seed.run("failed", datetime(2026, 10, 8, 8, 0, tzinfo=timezone.utc))   # ignored
    body = client.get("/freshness", params={"at": "2026-10-07T12:00:00-04:00"}).json()
    assert body["last_run_status"] == "partial"
    assert body["last_run_finished_at"] == "2026-10-07T08:00:00Z"
    assert body["stale"] is False


def test_old_run_is_stale(client, seed):
    seed.run("ok", FINISHED)
    assert client.get("/freshness", params={"at": "2026-10-08T12:00:00-04:00"}).json()["stale"] is True


def test_health_reports_current_schema(client, pg_engine, monkeypatch):
    monkeypatch.setattr("app.main.get_engine", lambda: pg_engine)
    assert client.get("/health").json() == {"status": "ok", "db": "ok", "schema": "current"}
