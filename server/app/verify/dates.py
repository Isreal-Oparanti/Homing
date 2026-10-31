"""Dates and time zones, parsed by code from the source's own words (docs/05).

Pure functions. The model may propose a date; only this module turns words into a time.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from dateparser.search import search_dates

# Zone words people write, mapped to IANA zones (daylight saving comes from the zone).
ZONES = {
    "et": "America/New_York",
    "est": "America/New_York",
    "edt": "America/New_York",
    "ct": "America/Chicago",
    "cst": "America/Chicago",
    "cdt": "America/Chicago",
    "pt": "America/Los_Angeles",
    "pst": "America/Los_Angeles",
    "pdt": "America/Los_Angeles",
    "gmt": "UTC",
    "utc": "UTC",
    "wat": "Africa/Lagos",
    "cat": "Africa/Maputo",
    "eat": "Africa/Nairobi",
    "bst": "Europe/London",
    "cet": "Europe/Paris",
    "cest": "Europe/Paris",
}
_ZONE_WORD = re.compile(r"\b(" + "|".join(ZONES) + r")\b", re.I)
# "GMT+1", "UTC-5" or "+02:00". A bare "+1" isn't a zone.
_OFFSET = re.compile(r"\b(?:utc|gmt)\s*([+-]\d{1,2})(?::?(\d{2}))?\b|([+-]\d{2}):(\d{2})\b", re.I)
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2}))?")
_TIME = re.compile(
    r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)|\b\d{1,2}[:h]\d{2}\b|\bnoon\b|\bmidnight\b",
    re.I,
)
_RELATIVE = re.compile(r"\b(today|tonight|tomorrow|demain|aujourd'hui)\b", re.I)
_MONTH = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|janv|f[ée]v|mars|avr|mai|juin|juil"
    r"|ao[uû]t|d[ée]c)[a-zéû]*\.?(?![a-z])",
    re.I,
)
_NUMERIC_DATE = re.compile(r"\b\d{1,2}[/.]\d{1,2}[/.]\d{2,4}\b")
END_OF_DAY = time(23, 59)


@dataclass(frozen=True)
class Deadline:
    at: datetime  # aware, in UTC
    source_text: str  # the exact words it came from
    tz: str  # the zone the words are in
    tz_stated: bool  # False: we assumed the zone, and the UI says so
    time_stated: bool  # False: no time given, so 23:59
    relative: bool  # "tomorrow", worked out from when the message was written


def _zone(text: str) -> tuple[str | None, str]:
    """The stated zone, if any, and the text without it (so the date parser ignores it)."""
    if m := _OFFSET.search(text):
        hours = int(m.group(1) or m.group(3))
        minutes = int(m.group(2) or m.group(4) or 0)
        # Etc/GMT zones have inverted signs (UTC+1 is Etc/GMT-1) and whole hours only.
        if minutes == 0 and abs(hours) <= 14:
            name = "UTC" if hours == 0 else f"Etc/GMT{-hours:+d}"
            return name, text[: m.start()] + " " + text[m.end() :]
    if m := _ZONE_WORD.search(text):
        return ZONES[m.group(1).lower()], text[: m.start()] + " " + text[m.end() :]
    return None, text


def _is_a_date(words: str) -> bool:
    """A day you could act on: a month with a day, a full numeric date, or "tomorrow"."""
    has_day = re.search(r"\d", words) is not None
    return bool(
        (_MONTH.search(words) and has_day) or _NUMERIC_DATE.search(words) or _RELATIVE.search(words)
    )


def _find(text: str, local_base: datetime) -> tuple[str, datetime] | None:
    if m := _ISO.search(text):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hh, mm = (int(m.group(4)), int(m.group(5))) if m.group(4) else (0, 0)
        try:
            return m.group(0), datetime(y, mo, d, hh, mm)
        except ValueError:
            return None
    settings = {
        "RELATIVE_BASE": local_base,
        "PREFER_DATES_FROM": "future",
        "DATE_ORDER": "DMY",
        "RETURN_AS_TIMEZONE_AWARE": False,
    }
    # Labels like "Date limite :" can throw the search off, so also try what follows them.
    for candidate in (text, text.rsplit(":", 1)[-1]):
        found = search_dates(candidate, languages=["en", "fr"], settings=settings) or []
        for words, parsed in found:
            if _is_a_date(words):
                return words, parsed
    return None


def parse_deadline(
    source_text: str,
    *,
    base: datetime,
    user_tz: str,
    source_tz_hint: str | None = None,
) -> Deadline | None:
    """Turn the source's words into a time. `base` is when the text was written or fetched."""
    if not source_text or not source_text.strip():
        return None
    stated_zone, text = _zone(source_text)
    zone = stated_zone or source_tz_hint or user_tz
    tz = ZoneInfo(zone)
    hit = _find(text, base.astimezone(tz).replace(tzinfo=None))
    if hit is None:
        return None
    words, parsed = hit
    time_stated = bool(_TIME.search(words))
    if not time_stated:
        parsed = datetime.combine(parsed.date(), END_OF_DAY)
    return Deadline(
        at=parsed.replace(tzinfo=tz).astimezone(UTC),
        source_text=source_text.strip(),
        tz=zone,
        tz_stated=stated_zone is not None,
        time_stated=time_stated,
        relative=bool(_RELATIVE.search(words)),
    )


def city_of(zone: str) -> str:
    return zone.split("/")[-1].replace("_", " ")


def display(at: datetime, user_tz: str) -> str:
    """ "Sat 31 Oct, 23:59 Lagos time": always in the user's own zone."""
    local = at.astimezone(ZoneInfo(user_tz))
    return f"{local:%a} {local.day} {local:%b}, {local:%H:%M} {city_of(user_tz)} time"


def bring_back_at(due: datetime, *, now: datetime, user_tz: str) -> datetime | None:
    """When to bring a save back, by the lead-time rule in docs/03. None once it's past."""
    if due <= now:
        return None
    left = due - now
    if left < timedelta(hours=48):
        return now
    back = due - (timedelta(days=7) if left > timedelta(days=7) else timedelta(days=2))
    local = back.astimezone(ZoneInfo(user_tz))
    nine = local.replace(hour=9, minute=0, second=0, microsecond=0).astimezone(UTC)
    return max(nine, now)
