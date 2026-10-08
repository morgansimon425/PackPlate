"""services/hours.py: no database."""

from dataclasses import dataclass
from datetime import date, datetime, timezone

from app.services.hours import CAMPUS_TZ, campus_time, open_state, periods

MON, TUE = date(2026, 10, 5), date(2026, 10, 6)


@dataclass
class Row:
    date: date
    status: str
    windows: list


def at(day, hour, minute=0):
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=CAMPUS_TZ)


def test_periods_are_campus_datetimes():
    assert periods(TUE, [[420, 1260]]) == [(at(TUE, 7), at(TUE, 21))]


def test_close_past_midnight_lands_on_next_day():
    [(_, closes)] = periods(MON, [[420, 1500]])
    assert closes == at(TUE, 1)


def test_open_inside_a_window():
    state = open_state(at(TUE, 12), Row(TUE, "open", [[420, 600], [660, 810]]), None)
    assert state.is_open is True
    assert state.closes_at == at(TUE, 13, 30)


def test_between_windows_reports_next_opening():
    state = open_state(at(TUE, 10, 30), Row(TUE, "open", [[420, 600], [660, 810]]), None)
    assert state.is_open is False
    assert state.opens_next_at == at(TUE, 11)


def test_after_last_window_has_no_next_opening_today():
    state = open_state(at(TUE, 22), Row(TUE, "open", [[420, 1260]]), None)
    assert (state.is_open, state.opens_next_at) == (False, None)


def test_closing_time_itself_is_closed():
    assert open_state(at(TUE, 21), Row(TUE, "open", [[420, 1260]]), None).is_open is False


def test_closed_all_day():
    assert open_state(at(TUE, 12), Row(TUE, "closed", []), None).is_open is False


def test_unknown_or_missing_hours_are_unknown_not_closed():
    assert open_state(at(TUE, 12), Row(TUE, "unknown", []), None).is_open is None
    assert open_state(at(TUE, 12), None, None).is_open is None


def test_after_midnight_uses_yesterdays_late_window():
    # Monday 7am - Tuesday 1am; Tuesday itself is closed all day.
    state = open_state(at(TUE, 0, 30), Row(TUE, "closed", []), Row(MON, "open", [[420, 1500]]))
    assert state.is_open is True
    assert state.closes_at == at(TUE, 1)
    assert open_state(at(TUE, 1, 30), Row(TUE, "closed", []), Row(MON, "open", [[420, 1500]])).is_open is False


def test_campus_time_handles_naive_and_utc():
    assert campus_time(datetime(2026, 10, 6, 12)) == at(TUE, 12)
    assert campus_time(datetime(2026, 10, 6, 16, tzinfo=timezone.utc)) == at(TUE, 12)
