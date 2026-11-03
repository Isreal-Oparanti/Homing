"""Calendar files (RFC 5545): one save's date, or the person's whole feed (docs/07-api.md).

Text is escaped and long lines are folded at 75 bytes, as calendar apps expect.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

STAMP = "%Y%m%dT%H%M%SZ"


def ics_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line: str) -> str:
    """Lines longer than 75 bytes continue on the next line after a space."""
    out, current = [], ""
    for ch in line:
        limit = 75 if not out else 74  # continuation lines start with a space
        if len((current + ch).encode()) > limit:
            out.append(current)
            current = ch
        else:
            current += ch
    out.append(current)
    return "\r\n ".join(out)


@dataclass
class Event:
    uid: str
    start: datetime
    summary: str
    description: str
    url: str | None = None
    minutes: int = 30
    # Reminders: "-P1D" before the start, or an exact time.
    alarms: list[str | datetime] = field(default_factory=list)

    def lines(self, now: datetime) -> list[str]:
        start = self.start.astimezone(UTC)
        out = [
            "BEGIN:VEVENT",
            f"UID:{self.uid}",
            f"DTSTAMP:{now.astimezone(UTC):{STAMP}}",
            f"DTSTART:{start:{STAMP}}",
            f"DTEND:{start + timedelta(minutes=self.minutes):{STAMP}}",
            f"SUMMARY:{ics_text(self.summary)}",
            f"DESCRIPTION:{ics_text(self.description)}",
        ]
        if self.url:
            out.append(f"URL:{self.url}")
        for alarm in self.alarms:
            trigger = (
                f"TRIGGER;VALUE=DATE-TIME:{alarm.astimezone(UTC):{STAMP}}"
                if isinstance(alarm, datetime)
                else f"TRIGGER:{alarm}"
            )
            out += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{ics_text(self.summary)}"]
            out += [trigger, "END:VALARM"]
        out.append("END:VEVENT")
        return out


def calendar(events: list[Event], *, name: str | None = None, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Homing//Homing//EN", "CALSCALE:GREGORIAN"]
    if name:
        # A feed: its name in the calendar app, and how often to ask for changes.
        lines += [
            f"X-WR-CALNAME:{ics_text(name)}",
            "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
            "X-PUBLISHED-TTL:PT1H",
        ]
    for e in events:
        lines += e.lines(now)
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(line) for line in lines) + "\r\n"
