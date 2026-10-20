"""Crowd report route, and crowd levels in /locations, against the test database."""

from datetime import datetime, timedelta

from sqlalchemy import inspect, select

from app.services.hours import CAMPUS_TZ, campus_time
from db.models import CrowdReport

NOON = datetime(2026, 10, 6, 12, 0, tzinfo=CAMPUS_TZ)


def test_report_is_stored_and_counted(client, seed, db):
    seed.location(1)
    response = client.post("/crowd/1", json={"level": "crowded"})
    assert response.status_code == 201
    body = response.json()
    assert (body["level"], body["report_count"]) == ("crowded", 1)
    assert abs(
        datetime.fromisoformat(body["last_reported_at"]) - campus_time()
    ) < timedelta(minutes=1)

    [row] = db.scalars(select(CrowdReport)).all()
    assert (row.location_id, row.level) == (1, "crowded")
    # Nothing about the reporter is kept.
    assert {c.name for c in inspect(CrowdReport).columns} == {
        "id",
        "location_id",
        "level",
        "created_at",
    }


def test_bad_level_and_unknown_location(client, seed):
    seed.location(1)
    assert client.post("/crowd/1", json={"level": "packed"}).status_code == 422
    assert client.post("/crowd/1", json={}).status_code == 422
    assert (
        client.post(
            "/crowd/1", json={"level": "crowded", "at": "2020-01-01"}
        ).status_code
        == 422
    )
    assert client.post("/crowd/99", json={"level": "crowded"}).status_code == 404


def test_one_report_per_client_and_location_per_minute(client, seed):
    seed.location(1)
    seed.location(2, "Case Dining Hall", "case")
    assert client.post("/crowd/1", json={"level": "crowded"}).status_code == 201
    again = client.post("/crowd/1", json={"level": "not_busy"})
    assert again.status_code == 429
    assert 0 < int(again.headers["Retry-After"]) <= 60
    assert client.post("/crowd/2", json={"level": "moderate"}).status_code == 201


def test_locations_show_recent_crowd_level(client, seed):
    seed.location(1)
    seed.location(2, "Case Dining Hall", "case")
    for location_id, menu_id in ((1, 31), (2, 32)):  # listed: has menu data
        seed.menu(menu_id, location_id, NOON.date(), "Lunch")
        seed.item(menu_id, "Soup")
    seed.crowd(1, "crowded", NOON - timedelta(minutes=10))
    seed.crowd(1, "crowded", NOON - timedelta(minutes=3))
    seed.crowd(2, "crowded", NOON - timedelta(hours=2))  # too old

    by_id = {
        loc["id"]: loc
        for loc in client.get("/locations", params={"at": NOON.isoformat()}).json()
    }
    assert by_id[1]["crowd"] == {
        "level": "crowded",
        "report_count": 2,
        "last_reported_at": "2026-10-06T15:57:00Z",
    }
    assert by_id[2]["crowd"] == {
        "level": None,
        "report_count": 0,
        "last_reported_at": None,
    }

    detail = client.get("/locations/1", params={"at": NOON.isoformat()}).json()
    assert detail["crowd"]["report_count"] == 2
