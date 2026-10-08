"""Parse: raw HTML in, plain dataclasses out. No network, no database.

Page shapes (found by reading NetNutrition's HTML and its own JS,
Scripts/cbord_nn_ui_repsonsive.js, and dining.ncsu.edu's HTML):
  NetNutrition home        <a onclick="...unitsSelectUnit(<unitOid>)">Name</a>
  unit menu list           date cards; <a onclick="...menuListSelectMenu(<menuOid>)">Meal</a>
  menu item table          course header rows + item rows with trait icons (<img title="Vegan">)
  nutrition label          nutrient rows, "Ingredients:" and "Contains:" sections
  dining.ncsu.edu location "Hours for <Weekday>, <Mon>. <d>" boxes with time ranges
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from bs4 import BeautifulSoup

_ONCLICK_OID = re.compile(r"\((\d+)\)")
NO_MENUS_NOTICE = "no menus available"


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


# ---------- NetNutrition: units ----------

@dataclass
class UnitRef:
    oid: int
    name: str


def parse_units(home_html: str) -> list[UnitRef]:
    units = []
    for a in _soup(home_html).select("a[onclick*='unitsSelectUnit(']"):
        m = _ONCLICK_OID.search(a["onclick"])
        if m:
            units.append(UnitRef(int(m.group(1)), _clean(a.get_text())))
    return units


# ---------- NetNutrition: a unit's menu list ----------

@dataclass
class MenuRef:
    oid: int
    date: date
    meal: str


@dataclass
class MenuList:
    description: str | None
    menus: list[MenuRef]
    no_menus_notice: bool = False  # the site said "There are no menus available..."


def parse_menu_list(html: str) -> MenuList:
    """Raises ValueError if a day header isn't a date like 'Monday, September 28, 2026'."""
    soup = _soup(html)
    desc_el = soup.select_one("#cbo_nn_unitDescriptionDiv")
    menus = []
    for card in soup.select("section.card"):
        header = card.select_one("header")
        if not header:
            continue
        text = _clean(header.get_text())
        try:
            day = datetime.strptime(text, "%A, %B %d, %Y").date()
        except ValueError:
            raise ValueError(f"unexpected menu date header {text!r}") from None
        for a in card.select("a.cbo_nn_menuLink"):
            m = _ONCLICK_OID.search(a.get("onclick", ""))
            if m:
                menus.append(MenuRef(int(m.group(1)), day, _clean(a.get_text())))
    return MenuList(
        description=_clean(desc_el.get_text()) if desc_el else None,
        menus=menus,
        no_menus_notice=NO_MENUS_NOTICE in soup.get_text(" ").lower(),
    )


# ---------- NetNutrition: items on one menu ----------

@dataclass
class ItemRow:
    detail_oid: int
    name: str
    course: str | None
    serving_size: str | None
    traits: list[str] = field(default_factory=list)


def parse_menu_items(html: str) -> list[ItemRow]:
    items = []
    course = None
    for tr in _soup(html).select("table tr"):
        if "cbo_nn_itemGroupRow" in (tr.get("class") or []):
            course = _clean(tr.get_text())
            continue
        # Item rows alternate cbo_nn_itemPrimaryRow / cbo_nn_itemAlternateRow; the
        # nutrition link is the reliable marker for both.
        link = tr.select_one("a[id^='showNutrition_']")
        if not link:
            continue
        # The item name is the link's own text; trait icons sit inside it as <img title=...>.
        name = _clean("".join(link.find_all(string=True, recursive=False)))
        traits = [img["title"] for img in link.select("img[title]")]
        cells = tr.find_all("td", recursive=False)
        serving = _clean(cells[2].get_text()) if len(cells) > 2 else None
        items.append(ItemRow(
            detail_oid=int(link["id"].split("_", 1)[1]),
            name=name,
            course=course,
            serving_size=serving or None,
            traits=traits,
        ))
    return items


# ---------- NetNutrition: nutrition label ----------

@dataclass
class Label:
    name: str | None
    serving_size: str | None
    nutrients: dict[str, str]  # "Protein" -> "4g", "Cholesterol" -> "NA"
    ingredients: str | None
    contains: list[str]
    incomplete: list[str] = field(default_factory=list)  # nutrients the site flags as missing


def parse_label(html: str) -> Label:
    soup = _soup(html)
    name_el = soup.select_one(".cbo_nn_LabelHeader")
    serving_el = soup.select_one(".cbo_nn_LabelBottomBorderLabel")
    serving = None
    if serving_el:
        serving = _clean(serving_el.get_text()).removeprefix("Serving Size:").strip() or None

    nutrients: dict[str, str] = {}
    incomplete: list[str] = []
    # Macro rows: a name <span style="font-weight:...">, then the value in the next <span>
    # of the same row. Missing values read "NA" and carry a class ending in "Incomplete".
    for name_span in soup.find_all("span", style=re.compile("font-weight")):
        key = _clean(name_span.get_text())
        row = name_span.find_parent("tr")
        value_el = name_span.find_next("span")
        if not key or key in nutrients or value_el is None or value_el.find_parent("tr") is not row:
            continue
        nutrients[key] = _clean(value_el.get_text())
        if any(c.endswith("Incomplete") for c in value_el.get("class") or []):
            incomplete.append(key)
    # Vitamin and mineral rows use a label cell + value cell instead.
    for label_el in soup.select("td.cbo_nn_SecondaryNutrientLabel"):
        value_el = label_el.find_next_sibling("td")
        nutrients.setdefault(_clean(label_el.get_text()), _clean(value_el.get_text()) if value_el else "")

    ingredients_el = soup.select_one(".cbo_nn_LabelIngredients")
    contains_el = soup.select_one(".cbo_nn_LabelAllergens")
    contains = []
    if contains_el:
        contains = [c.strip() for c in _clean(contains_el.get_text()).split(",") if c.strip()]
    return Label(
        name=_clean(name_el.get_text()) if name_el else None,
        serving_size=serving,
        nutrients=nutrients,
        ingredients=_clean(ingredients_el.get_text()) if ingredients_el else None,
        contains=contains,
        incomplete=incomplete,
    )


# ---------- dining.ncsu.edu: hours ----------

@dataclass
class HoursEntry:
    date_label: str  # "Monday, Sep. 28" (the page shows no year)
    raw_text: str  # "7:00am - 10:00am | 11:00am - 1:30pm" or "Closed all day"
    windows: list[tuple[int, int]]  # minutes after midnight
    closed: bool


_RANGE = re.compile(r"(\d{1,2}(?::\d{2})?\s*[ap]m)\s*-\s*(\d{1,2}(?::\d{2})?\s*[ap]m)", re.I)


def _to_minutes(t: str) -> int:
    t = t.lower().replace(" ", "")
    parsed = datetime.strptime(t, "%I:%M%p" if ":" in t else "%I%p")
    return parsed.hour * 60 + parsed.minute


def parse_time_ranges(text: str) -> list[tuple[int, int]]:
    windows = []
    for start, end in _RANGE.findall(text):
        s, e = _to_minutes(start), _to_minutes(end)
        if e <= s:  # "8:00am - 12:00am" closes at (or after) midnight
            e += 24 * 60
        windows.append((s, e))
    return windows


def parse_location_hours(html: str) -> dict[str, HoursEntry]:
    """Returns {'today': ..., 'tomorrow': ..., 'pick': ...} from a location page;
    'pick' is the day ?date=YYYY-MM-DD asked for. Empty if the page has no hours boxes."""
    soup = _soup(html)
    out = {}
    for key in ("today", "tomorrow", "pick"):
        pane = soup.select_one(f"#hours-{key}")
        if not pane:
            continue
        h3 = pane.find("h3")
        info = pane.select_one(".sidebar__box__info")
        raw = _clean(info.get_text(" ")) if info else ""
        windows = parse_time_ranges(raw)
        out[key] = HoursEntry(
            date_label=_clean(h3.get_text()).removeprefix("Hours for").strip() if h3 else "",
            raw_text=raw,
            windows=windows,
            closed=("closed" in raw.lower() and not windows),
        )
    return out


_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def hours_label_matches(label: str, day: date) -> bool:
    """The hours box says 'Monday, Sep. 28' with no year; check weekday and day of month."""
    m = re.match(r"^(\w+),.*?(\d{1,2})$", label)
    return bool(m) and m.group(1) == _WEEKDAYS[day.weekday()] and int(m.group(2)) == day.day
