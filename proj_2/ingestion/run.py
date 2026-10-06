"""Run the ingestion job once: Fetch -> Parse -> Normalize + Label -> Write.

Usage (from proj_2/, with DATABASE_URL set and migrations applied):
    python -m ingestion.run                        all units, 7 days, with nutrition labels
    python -m ingestion.run --units 1 --days 1     Fountain, today only
    python -m ingestion.run --no-nutrition         menus + icon traits only (fast)

Every run leaves an ingest_runs row with its options, stats, and errors. A failure in
one unit or menu is recorded and the job moves on; a failure of the whole job is
recorded as status 'failed'. Only one run at a time (Postgres advisory lock).
"""

import argparse
import logging
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from db.migrate import check_current
from db.models import IngestRun, Nutrition
from db.session import make_engine, make_session_factory
from ingestion import parse, write
from ingestion.config import CAMPUS_TZ, DEFAULT_DAYS, LABEL_MAX_AGE_DAYS, MAX_DAYS
from ingestion.fetch import DiningSiteClient, FetchError, NetNutritionClient
from ingestion.normalize import UNIT_TO_DINING_SLUG, nutrition_key, same_dish

log = logging.getLogger("ingestion")

LOCK_KEY = 5102026  # Postgres advisory lock id meaning "an ingestion run is in progress"


class AlreadyRunning(Exception):
    pass


@dataclass
class Stats:
    units: int = 0
    units_without_menus: list = field(default_factory=list)
    hours_days: int = 0
    menus_listed: int = 0
    menus_scraped: int = 0
    menus_new: int = 0  # scraped for the first time
    menus_changed: int = 0  # items differ from the previous scrape
    menus_unchanged: int = 0
    menus_removed: int = 0  # no longer listed by the site
    items: int = 0
    labels_fetched: int = 0
    labels_reused: int = 0  # stored and younger than LABEL_MAX_AGE_DAYS
    labels_stale_reused: int = 0  # older, but this run couldn't fetch a new one
    label_mismatches: int = 0
    requests: int = 0


class LabelCache:
    """Labels already stored: key -> (fetched_at, "Contains:" list).

    Only updated after a commit, so a label whose transaction rolled back is never
    treated as stored.
    """

    def __init__(self, db: Session, location_ids: list[int], fresh_after: datetime):
        rows = db.execute(
            select(Nutrition.key, Nutrition.fetched_at, Nutrition.contains)
            .where(Nutrition.location_id.in_(location_ids))
        )
        self._rows = {key: (fetched_at, contains) for key, fetched_at, contains in rows}
        self._fresh_after = fresh_after

    def fresh(self, key: str) -> list[str] | None:
        hit = self._rows.get(key)
        return hit[1] if hit and hit[0] >= self._fresh_after else None

    def any_age(self, key: str) -> list[str] | None:
        hit = self._rows.get(key)
        return hit[1] if hit else None

    def add(self, stored: dict[str, list[str]]):
        t = write.now()
        self._rows.update({key: (t, contains) for key, contains in stored.items()})


class Job:
    def __init__(self, db: Session, nn, dining, *, unit_ids, days, nutrition, refresh_labels,
                 max_labels, today: date, started: datetime):
        self.db, self.nn, self.dining = db, nn, dining
        self.unit_ids, self.nutrition, self.max_labels = unit_ids, nutrition, max_labels
        self.days = [today + timedelta(days=i) for i in range(days)]
        # --refresh-labels: anything stored before this run counts as stale.
        self.fresh_after = started if refresh_labels else started - timedelta(days=LABEL_MAX_AGE_DAYS)
        self.stats = Stats()
        self.errors: list[str] = []
        self.labels: LabelCache | None = None

    def error(self, message: str):
        log.warning("! %s", message)
        self.errors.append(message)

    def execute(self):
        units = parse.parse_units(self.nn.start_session())
        if not units:
            raise FetchError("no units on the NetNutrition home page (layout changed?)")
        if self.unit_ids:
            for oid in sorted(set(self.unit_ids) - {u.oid for u in units}):
                self.error(f"unit {oid}: not listed on NetNutrition")
            units = [u for u in units if u.oid in self.unit_ids]
        for u in units:
            write.upsert_location(self.db, u)
        self.db.commit()

        self.ingest_hours(units)

        self.labels = LabelCache(self.db, [u.oid for u in units], self.fresh_after)
        for unit in units:
            self.stats.units += 1
            try:
                self.ingest_unit(unit)
            except Exception as e:
                self.db.rollback()
                self.error(f"unit {unit.oid} {unit.name}: {e}")
                try:
                    self.nn.start_session()
                except Exception as e2:
                    self.error(f"session reset failed: {e2}")

    # ---------- hours (dining.ncsu.edu) ----------

    def ingest_hours(self, units: list[parse.UnitRef]):
        for unit in units:
            try:
                hours = self.hours_for(unit)
            except Exception as e:
                self.db.rollback()
                self.error(f"hours {unit.name}: {e}")
                continue
            for day, entry in hours.items():
                write.upsert_hours(self.db, unit.oid, day, entry)
                self.stats.hours_days += 1
            self.db.commit()

    def hours_for(self, unit: parse.UnitRef) -> dict[date, parse.HoursEntry | None]:
        slug = UNIT_TO_DINING_SLUG.get(unit.oid)
        if slug is None:
            return {day: None for day in self.days}
        # One request covers today and tomorrow; later days need ?date= each.
        first = parse.parse_location_hours(self.dining.location_page(slug))
        if not first:
            raise ValueError(f"no hours boxes on /location/{slug}/ (blocked, or layout changed?)")
        out = {}
        for i, day in enumerate(self.days):
            if i < 2:
                entry = first.get("today" if i == 0 else "tomorrow")
            else:
                try:
                    entry = parse.parse_location_hours(self.dining.location_page(slug, day)).get("pick")
                except FetchError as e:
                    self.error(f"hours {unit.name} {day}: {e}")
                    entry = None
            if entry is not None and not parse.hours_label_matches(entry.date_label, day):
                self.error(f"hours {unit.name}: page showed {entry.date_label!r}, expected {day}")
                entry = None
            out[day] = entry
        return out

    # ---------- menus and labels (NetNutrition) ----------

    def ingest_unit(self, unit: parse.UnitRef):
        log.info("unit %s %s", unit.oid, unit.name)
        panels = self.nn.select_unit(unit.oid)
        if "menuPanel" not in panels:
            # e.g. Port City Java Talley jumps straight to a stale, empty item list
            self.stats.units_without_menus.append(unit.name)
            return
        menu_list = parse.parse_menu_list(panels["menuPanel"])
        if not menu_list.menus:
            if not menu_list.no_menus_notice:
                raise ValueError("menu list is empty but has no 'no menus' notice (layout changed?)")
            self.stats.units_without_menus.append(unit.name)
        write.upsert_location(self.db, unit, menu_list.description)
        write.upsert_menu_refs(self.db, unit.oid, menu_list.menus)
        self.stats.menus_removed += write.delete_unlisted_menus(self.db, unit.oid, menu_list.menus)
        self.db.commit()
        self.stats.menus_listed += len(menu_list.menus)

        for ref in (m for m in menu_list.menus if m.date in self.days):
            try:
                self.ingest_menu(unit, ref)
            except Exception as e:
                self.db.rollback()
                self.error(f"menu {unit.name} {ref.date} {ref.meal}: {e}")
                # The server-side selection is unknown now: start over and re-select the
                # unit. If that fails too, the unit-level handler records it.
                self.nn.start_session()
                self.nn.select_unit(unit.oid)

    def ingest_menu(self, unit: parse.UnitRef, ref: parse.MenuRef):
        panels = self.nn.select_menu(ref.oid)
        if "itemPanel" not in panels:
            raise FetchError("response had no itemPanel")
        rows = parse.parse_menu_items(panels["itemPanel"])

        contains_by_key: dict[str, list[str]] = {}
        stored_now: dict[str, list[str]] = {}
        for r in rows:
            key = nutrition_key(unit.oid, r.name, r.serving_size)
            if key in contains_by_key:
                continue
            fresh = self.labels.fresh(key)
            if fresh is not None:
                contains_by_key[key] = fresh
                self.stats.labels_reused += 1
                continue
            if self.can_fetch_label():
                label = parse.parse_label(self.nn.nutrition_label(r.detail_oid))
                self.stats.labels_fetched += 1
                # Server state can drift between requests: never attach another dish's label.
                if same_dish(label.name, r.name):
                    contains = write.upsert_nutrition(self.db, unit.oid, r.detail_oid, r, label)
                    contains_by_key[key] = stored_now[key] = contains
                    continue
                self.stats.label_mismatches += 1
                self.error(f"label mismatch at {unit.name}: asked for {r.name!r} "
                           f"(detail {r.detail_oid}), got {label.name!r}; not attached")
            older = self.labels.any_age(key)
            if older is not None:  # verified when it was stored; better than nothing
                contains_by_key[key] = older
                self.stats.labels_stale_reused += 1

        outcome = write.replace_menu_items(self.db, ref.oid, unit.oid, rows, contains_by_key)
        self.db.commit()
        self.labels.add(stored_now)

        self.stats.menus_scraped += 1
        self.stats.items += len(rows)
        if outcome == "new":
            self.stats.menus_new += 1
        elif outcome == "changed":
            self.stats.menus_changed += 1
        else:
            self.stats.menus_unchanged += 1
        log.info("  %s %-9s %3d items (%s)", ref.date, ref.meal, len(rows), outcome)

    def can_fetch_label(self) -> bool:
        return self.nutrition and (self.max_labels is None or self.stats.labels_fetched < self.max_labels)


def run(unit_ids: list[int] | None = None, days: int = DEFAULT_DAYS, nutrition: bool = True,
        refresh_labels: bool = False, max_labels: int | None = None, delay: float | None = None,
        *, engine: Engine | None = None, nn=None, dining=None, today: date | None = None) -> IngestRun:
    """Run once and return the ingest_runs row. engine/nn/dining/today are for tests."""
    if not 1 <= days <= MAX_DAYS:
        raise ValueError(f"days must be 1..{MAX_DAYS} (NetNutrition lists {MAX_DAYS} days)")
    engine = engine or make_engine()
    check_current(engine)
    with engine.connect() as lock:
        if not lock.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_KEY}):
            raise AlreadyRunning("another ingestion run is in progress")
        lock.commit()  # the lock is session-level: it outlives this transaction
        try:
            return _run_locked(engine, unit_ids, days, nutrition, refresh_labels, max_labels, delay,
                               nn, dining, today)
        finally:
            # Pooled connections stay open, so release explicitly.
            lock.scalar(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})
            lock.commit()


def _run_locked(engine, unit_ids, days, nutrition, refresh_labels, max_labels, delay,
                nn, dining, today) -> IngestRun:
    client_kw = {"delay": delay} if delay is not None else {}
    own_nn, own_dining = nn is None, dining is None
    nn = nn or NetNutritionClient(**client_kw)
    dining = dining or DiningSiteClient(**client_kw)
    db = make_session_factory(engine)()
    started = write.now()
    today = today or datetime.now(CAMPUS_TZ).date()

    record = IngestRun(started_at=started, status="running", stats={}, errors=[], options={
        "units": unit_ids, "days": days, "first_day": today.isoformat(), "nutrition": nutrition,
        "refresh_labels": refresh_labels, "max_labels": max_labels, "delay": delay,
    })
    db.add(record)
    db.commit()

    job = Job(db, nn, dining, unit_ids=unit_ids, days=days, nutrition=nutrition,
              refresh_labels=refresh_labels, max_labels=max_labels, today=today, started=started)
    try:
        job.execute()
        record.status = "partial" if job.errors else "ok"
    except Exception as e:
        db.rollback()
        job.errors.append(f"fatal: {e!r}")
        record.status = "failed"
        log.exception("ingestion failed")
    except BaseException:  # Ctrl+C etc.: still close out the run row
        db.rollback()
        job.errors.append("interrupted")
        record.status = "failed"
        raise
    finally:
        job.stats.requests = nn.request_count + dining.request_count
        record.stats, record.errors = asdict(job.stats), job.errors
        record.finished_at = write.now()
        db.commit()
        db.close()
        if own_nn:
            nn.close()
        if own_dining:
            dining.close()
    return record


def _unit_list(value: str) -> list[int]:
    try:
        return [int(x) for x in value.split(",") if x.strip()]
    except ValueError:
        raise argparse.ArgumentTypeError("expected comma-separated unit ids, e.g. 1,2,3") from None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Scrape NC State dining menus, nutrition, and hours into Postgres.")
    p.add_argument("--units", type=_unit_list, help="comma-separated NetNutrition unit ids (default: all)")
    p.add_argument("--days", type=int, default=DEFAULT_DAYS,
                   help=f"days starting today, America/New_York (default {DEFAULT_DAYS}, max {MAX_DAYS})")
    p.add_argument("--no-nutrition", action="store_true", help="skip fetching nutrition labels")
    p.add_argument("--refresh-labels", action="store_true", help="re-fetch labels even if recently stored")
    p.add_argument("--max-labels", type=int, help="cap label requests this run")
    p.add_argument("--delay", type=float, help="seconds between requests (default SCRAPE_DELAY or 1.0)")
    a = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    for noisy in ("httpx", "httpx2", "httpcore", "alembic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    try:
        record = run(unit_ids=a.units, days=a.days, nutrition=not a.no_nutrition,
                     refresh_labels=a.refresh_labels, max_labels=a.max_labels, delay=a.delay)
    except (AlreadyRunning, RuntimeError, ValueError) as e:
        print(f"not started: {e}", file=sys.stderr)
        return 2

    print(f"\nrun {record.id}: {record.status}")
    for k, v in record.stats.items():
        print(f"  {k}: {v}")
    for e in record.errors:
        print(f"  ! {e}")
    return 1 if record.status == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
