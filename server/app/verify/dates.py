"""Dates and time zones, parsed by code from the source's own words (docs/05).

Pure functions. The model may propose a date; only this module turns words into a time.
"""

import re
from dataclasses import dataclass, replace
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
_LETTER_HYPHEN = re.compile(r"(?<=[A-Za-z])-(?=[A-Za-z])")
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
    # Some words throw the search off, so also try what follows a label ("Date limite :")
    # and the text with hyphens between letters as spaces ("apply on-time is November 2 at
    # 8pm" finds only "8pm").
    candidates = (text, text.rsplit(":", 1)[-1], _LETTER_HYPHEN.sub(" ", text))
    for candidate in dict.fromkeys(candidates):
        found = search_dates(candidate, languages=["en", "fr"], settings=settings) or []
        for words, parsed in found:
            if _is_a_date(words):
                return words, parsed
    return None


_YEAR = re.compile(r"\b(?:19|20)\d{2}\b|\b\d{1,2}[/.]\d{1,2}[/.]\d{2,4}\b")
JUST_PAST = timedelta(days=60)


def _this_year_if_just_past(words: str, parsed: datetime, local_base: datetime) -> datetime:
    """A date with no year is read as the next one to come, so "Oct 25" seen on 2 Nov became
    next October. If the same day this year passed less than two months ago, it means that day:
    a page that just closed, not one opening in eleven months."""
    if _YEAR.search(words) or _RELATIVE.search(words):
        return parsed
    try:
        earlier = parsed.replace(year=parsed.year - 1)
    except ValueError:  # 29 February
        return parsed
    return earlier if local_base - JUST_PAST <= earlier < local_base else parsed


_MONTH_WORD = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DAY_NUM = r"\d{1,2}(?:st|nd|rd|th)?"
_DATE_WORDS = (
    rf"(?:{_DAY_NUM}\s+(?:of\s+)?{_MONTH_WORD}|{_MONTH_WORD}\s+{_DAY_NUM})"
    r"(?:,?\s+(?:19|20)\d{2})?"
)
# "open 1 September – 18 November 2026", "from 1 Sept to 18 Nov", "between 3 March and 30 April
# 2027": a call's window. Its deadline is where the window ends.
_RANGE = re.compile(
    rf"({_DATE_WORDS})\s*(?:–|—|-|to|until|till|through|and)\s*({_DATE_WORDS})", re.IGNORECASE
)


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
    if window := _RANGE.search(text):
        text = text[window.start(2) :]  # the end of the window, and any time given after it
    zone = stated_zone or source_tz_hint or user_tz
    tz = ZoneInfo(zone)
    hit = _find(text, base.astimezone(tz).replace(tzinfo=None))
    weekday = _WEEKDAY.search(text) if hit is None else None
    if weekday and re.search(r"\bblack\s+friday\b", text, re.I):
        weekday = None  # a sale, not a day to act by
    if hit is None and weekday is None:
        return None
    if hit is None:
        # "Apply by Friday": the next Friday after it was written (that day, if it's Friday).
        assert weekday is not None
        local = base.astimezone(tz).replace(tzinfo=None)
        ahead = (_WEEKDAYS.index(weekday.group(1).lower()) - local.weekday()) % 7
        hit = (weekday.group(0), datetime.combine(local.date() + timedelta(days=ahead), time(0)))
    words, parsed = hit
    parsed = _this_year_if_just_past(words, parsed, base.astimezone(tz).replace(tzinfo=None))
    time_stated = bool(_TIME.search(words))
    # "Nov 4: Project submissions due by 9:00 PM ET": the time is a few words after the date.
    # Taken only when the text gives exactly one time; two would be a guess.
    clocks = list(_CLOCK.finditer(text))
    if not time_stated and len(clocks) == 1 and (said := _clock(text)) is not None:
        parsed, time_stated = datetime.combine(parsed.date(), said), True
    if not time_stated:
        parsed = datetime.combine(parsed.date(), END_OF_DAY)
    return Deadline(
        at=parsed.replace(tzinfo=tz).astimezone(UTC),
        source_text=source_text.strip(),
        tz=zone,
        tz_stated=stated_zone is not None,
        time_stated=time_stated,
        relative=bool(_RELATIVE.search(words)) or weekday is not None,
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


# Moments: things the person says are coming up ("recording my demo on Tuesday evening").
# Unlike a deadline in a post, a weekday here is the person's own next one, so it's allowed.
_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_WEEKDAY = re.compile(r"\b(?:on |this |next |coming )?(" + "|".join(_WEEKDAYS) + r")\b", re.I)
_PART_OF_DAY = {
    "morning": time(9, 0),
    "afternoon": time(14, 0),
    "evening": time(18, 0),
    "night": time(20, 0),
    "tonight": time(20, 0),
}
_PART = re.compile(r"\b(" + "|".join(_PART_OF_DAY) + r")\b", re.I)
_CLOCK = re.compile(
    r"\b(\d{1,2})(?:[:.h](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)|\b(\d{1,2})[:h](\d{2})\b", re.I
)
MOMENT_TIME = time(9, 0)  # no time said: the morning


def _clock(text: str) -> time | None:
    m = _CLOCK.search(text)
    if m is None:
        return None
    if m.group(1):
        hour, minute = int(m.group(1)) % 12, int(m.group(2) or 0)
        if m.group(3).lower().startswith("p"):
            hour += 12
    else:
        hour, minute = int(m.group(4)), int(m.group(5))
    return time(hour, minute) if hour < 24 and minute < 60 else None


def parse_moment(text: str, *, now: datetime, user_tz: str) -> Deadline | None:
    """When something the person typed happens: a date (as parse_deadline reads it), or a
    weekday, meaning the next one to come. The time is a clock time if given, else a part of
    the day ("evening" is 18:00), else 09:00. None when it names no day."""
    part = _PART.search(text)
    said = _clock(text)
    if said is None and part is not None:
        said = _PART_OF_DAY[part.group(1).lower()]
    found = parse_deadline(text, base=now, user_tz=user_tz)
    if found is not None:
        if found.time_stated:
            return found
        tz = ZoneInfo(found.tz)
        day = found.at.astimezone(tz).date()
        at = datetime.combine(day, said or MOMENT_TIME, tzinfo=tz).astimezone(UTC)
        return replace(found, at=at, time_stated=said is not None)
    tz = ZoneInfo(user_tz)
    today = now.astimezone(tz).date()
    m = _WEEKDAY.search(text)
    if m is not None:
        ahead = (_WEEKDAYS.index(m.group(1).lower()) - today.weekday()) % 7 or 7
        day, source_text = today + timedelta(days=ahead), m.group(0).strip()
    elif part is not None and part.group(1).lower() == "tonight":  # the day is today
        day, source_text = today, part.group(0)
    else:
        return None
    at = datetime.combine(day, said or MOMENT_TIME, tzinfo=tz).astimezone(UTC)
    return Deadline(
        at=at,
        source_text=source_text,
        tz=user_tz,
        tz_stated=False,
        time_stated=said is not None,
        relative=True,
    )
