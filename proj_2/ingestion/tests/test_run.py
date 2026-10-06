"""End-to-end job tests: fake clients serve the captured pages, the real job writes to
the test database. No network."""

from datetime import date
from html import escape

import pytest
from sqlalchemy import select, text

from db.models import HoursDay, IngestRun, Menu, MenuItem, Nutrition
from ingestion import run as job
from ingestion.fetch import FetchError
from ingestion.normalize import nutrition_key
from ingestion.parse import parse_menu_items

DAY = date(2026, 9, 28)  # the captured pages are from this Monday


class FakeNetNutrition:
    """Answers like NetNutrition: Fountain's menu list, the same item table for every
    menu, and a label for any item (the Pita label for Pita, a stub for the rest)."""

    def __init__(self, fixture_html, *, drift_name=None, fail_after=None, fail_start=False):
        self.home = fixture_html("nn_home.html")
        self.menu_list = fixture_html("nn_unit_menu_list.html")
        self.items = fixture_html("nn_menu_items.html")
        self.pita = fixture_html("nn_label_pita.html")
        self.names = {r.detail_oid: r.name for r in parse_menu_items(self.items)}
        self.drift_name = drift_name  # this item gets the wrong label (server state drift)
        self.fail_after = fail_after  # fail the label request right after this item's
        self.fail_start = fail_start
        self._fail_next = False
        self.request_count = 0

    def start_session(self):
        self.request_count += 1
        if self.fail_start:
            raise FetchError("site down")
        return self.home

    def select_unit(self, oid):
        self.request_count += 1
        return {"menuPanel": self.menu_list}

    def select_menu(self, oid):
        self.request_count += 1
        return {"itemPanel": self.items}

    def nutrition_label(self, detail_oid):
        self.request_count += 1
        if self._fail_next:
            self._fail_next = False
            raise FetchError("connection reset")
        name = self.names[detail_oid]
        if name == self.fail_after:
            self.fail_after, self._fail_next = None, True
        if name == "Pita" or name == self.drift_name:
            return self.pita
        return f"<table><tr><td class='cbo_nn_LabelHeader'>{escape(name)}</td></tr></table>"


class FakeDiningSite:
    def __init__(self, fixture_html):
        self.page = fixture_html("dining_location_case.html")  # "today" box says Monday, Sep. 28
        self.request_count = 0

    def location_page(self, slug, on=None):
        self.request_count += 1
        return self.page


@pytest.fixture
def run_job(pg_engine, fixture_html):
    def _run(nn=None, today=DAY, **kw):
        kw.setdefault("unit_ids", [1])
        kw.setdefault("days", 1)
        return job.run(engine=pg_engine, nn=nn or FakeNetNutrition(fixture_html),
                       dining=FakeDiningSite(fixture_html), today=today, **kw)
    return _run


def unique_label_keys(fixture_html):
    return {nutrition_key(1, r.name, r.serving_size) for r in parse_menu_items(fixture_html("nn_menu_items.html"))}


def test_full_run_writes_menus_items_labels_and_hours(db, run_job, fixture_html):
    record = run_job(nn=FakeNetNutrition(fixture_html, drift_name="Bananas"))
    stats = record.stats
    keys = unique_label_keys(fixture_html)

    assert record.status == "partial"  # the drifted label is an error
    assert stats["menus_listed"] == 28
    assert stats["menus_scraped"] == stats["menus_new"] == 4  # Monday: Breakfast/Lunch/Dinner/Daily
    assert stats["items"] == 4 * 89
    # Each label fetched once, except the drifted one, which is retried on every menu.
    assert stats["labels_fetched"] == len(keys) + 3
    assert stats["label_mismatches"] == 4
    assert all("label mismatch" in e and "'Bananas'" in e for e in record.errors)

    items = db.scalars(select(MenuItem)).all()
    assert all(i.nutrition_key is None for i in items if i.name == "Bananas")  # guard held
    pita = [i for i in items if i.name == "Pita"]
    assert pita and all(i.nutrition_key and "gluten" in i.allergens for i in pita)
    assert db.scalar(select(Nutrition.protein_g).where(Nutrition.key == pita[0].nutrition_key)) == 4.0

    hours = db.get(HoursDay, (1, DAY))
    assert hours.status == "open" and hours.windows == [[420, 600], [660, 810]]


def test_second_run_reuses_labels_and_detects_no_change(db, run_job, fixture_html):
    run_job()
    record = run_job()
    assert record.status == "ok"
    assert record.stats["labels_fetched"] == 0
    assert record.stats["menus_unchanged"] == 4
    assert record.stats["menus_new"] == record.stats["menus_changed"] == 0


def test_rolled_back_label_is_not_treated_as_stored(db, run_job, fixture_html):
    # The first menu stores Pita's label, then a later label request fails and the menu
    # rolls back. Later menus must fetch Pita again, not link to a label that was never saved.
    record = run_job(nn=FakeNetNutrition(fixture_html, fail_after="Pita"))
    assert record.status == "partial"
    assert any("connection reset" in e for e in record.errors)
    assert record.stats["menus_scraped"] == 3

    pita = [i for i in db.scalars(select(MenuItem)) if i.name == "Pita"]
    assert len(pita) == 3 and all(i.nutrition_key for i in pita)
    assert db.get(Nutrition, pita[0].nutrition_key) is not None
    assert db.scalars(select(Menu).where(Menu.fetched_at.is_(None), Menu.date == DAY)).all()  # the failed menu


def test_unknown_unit_and_wrong_hours_date_are_reported(db, run_job):
    # Tuesday: the hours page's "today" box still says Monday, so hours must be unknown.
    record = run_job(unit_ids=[1, 99], today=date(2026, 9, 29), nutrition=False)
    assert "unit 99: not listed on NetNutrition" in record.errors
    assert any("expected 2026-09-29" in e for e in record.errors)
    assert db.get(HoursDay, (1, date(2026, 9, 29))).status == "unknown"
    assert record.stats["labels_fetched"] == 0


def test_fatal_error_is_recorded_on_the_run(db, run_job, fixture_html):
    record = run_job(nn=FakeNetNutrition(fixture_html, fail_start=True))
    assert record.status == "failed"
    assert record.errors == ["fatal: FetchError('site down')"]
    assert db.get(IngestRun, record.id).finished_at is not None


def test_only_one_run_at_a_time(db, run_job, pg_engine):
    with pg_engine.connect() as other:
        other.execute(text("SELECT pg_advisory_lock(:k)"), {"k": job.LOCK_KEY})
        with pytest.raises(job.AlreadyRunning):
            run_job()
        other.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": job.LOCK_KEY})


def test_days_out_of_range_is_rejected(run_job):
    with pytest.raises(ValueError):
        run_job(days=8)
