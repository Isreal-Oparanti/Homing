"""WhatsApp chat exports, read by code (docs/04-ingestion.md · WhatsApp export).

Pure functions: the export's text in, messages out, then messages into planned saves.
Android and iOS formats, day-first and month-first dates, 12- and 24-hour times,
multi-line messages, edits, system lines, and media attached or left out.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.ingest.urls import find_urls

# Invisible direction marks WhatsApp puts around names and attachment lines.
_MARKS = dict.fromkeys(map(ord, "‎‏‪‫‬﻿"), None)
# Newer exports put a narrow no-break space before "pm".
_ODD_SPACES = re.compile(r"[  ]")
_DATE_TIME = (
    r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4}),?\s+(\d{1,2})[:.](\d{2})(?:[:.](\d{2}))?"
    r"\s*([ap]\.?\s?m\.?)?"
)
_ANDROID = re.compile(rf"^{_DATE_TIME}\s+-\s+(.*)$", re.I)
_IOS = re.compile(rf"^\[{_DATE_TIME}\]\s+(.*)$", re.I)
_SENDER = re.compile(r"^([^:\n]{1,80}?): ?(.*)$", re.S)

_EDITED = re.compile(r"\s*<This message was edited>\s*$")
_DELETED = {"This message was deleted", "You deleted this message"}
_ANDROID_FILE = re.compile(r"^(.+?) \(file attached\)\s*(?:\n(.*))?$", re.S)
_IOS_FILE = re.compile(r"^<attached: (.+?)>\s*(.*)$", re.S)
_OMITTED = re.compile(
    r"^(?:<Media omitted>|(?:.+ • )?(?:image|video|audio|sticker|GIF|document|Contact card)"
    r" omitted)$",
    re.I,
)

LABEL_WINDOW = timedelta(seconds=180)
LABEL_CHARS = 60


@dataclass(frozen=True)
class Message:
    at: datetime  # as written; the export carries no time zone
    sender: str
    text: str  # without attachment markers or the edit note
    attachment: str | None = None  # the attached file's name, when media was exported
    media_omitted: bool = False  # there was media, but the export left it out


@dataclass(frozen=True)
class Chat:
    messages: list[Message]
    day_first: bool
    order_ambiguous: bool  # no date showed the order; day-first was assumed
    system_lines: int  # encryption notices, deleted messages, lines we couldn't date


@dataclass
class Planned:
    """One save to make, before it touches the database."""

    at: datetime
    text: str  # the message, or a file's caption
    attachment: str | None = None
    label: str | None = None  # a short message sent just after a link, naming it


def _header(line: str) -> tuple[tuple[str, ...], str] | None:
    m = _IOS.match(line) or _ANDROID.match(line)
    return (m.groups()[:7], m.group(8)) if m else None


def _datetime(fields: tuple[str, ...], day_first: bool) -> datetime:
    a, b, year, hour, minute, second, ampm = fields
    day, month = (int(a), int(b)) if day_first else (int(b), int(a))
    h = int(hour)
    if ampm:
        pm = ampm.lower().startswith("p")
        h = (h % 12) + (12 if pm else 0)
    y = int(year)
    return datetime(y + 2000 if y < 100 else y, month, day, h, int(minute), int(second or 0))


def parse(text: str, *, day_first_guess: bool = True) -> Chat:
    """Messages in order. `day_first_guess` decides dates like 03/04 when no date in the whole
    file shows the order (day-first suits Nigeria)."""
    text = _ODD_SPACES.sub(" ", text.translate(_MARKS)).replace("\r\n", "\n")
    raw: list[tuple[tuple[str, ...], list[str]]] = []
    for line in text.split("\n"):
        head = _header(line)
        if head is not None:
            raw.append((head[0], [head[1]]))
        elif raw:  # a line without a timestamp continues the message above
            raw[-1][1].append(line)

    firsts = [int(f[0]) for f, _ in raw]
    seconds = [int(f[1]) for f, _ in raw]
    if any(x > 12 for x in firsts):
        day_first, ambiguous = True, False
    elif any(x > 12 for x in seconds):
        day_first, ambiguous = False, False
    else:
        day_first, ambiguous = day_first_guess, bool(raw)

    messages: list[Message] = []
    system = 0
    for fields, lines in raw:
        try:
            at = _datetime(fields, day_first)
        except ValueError:
            system += 1
            continue
        m = _SENDER.match("\n".join(lines))
        if m is None:  # "Messages and calls are end-to-end encrypted", group notices
            system += 1
            continue
        sender, body = m.group(1).strip(), _EDITED.sub("", m.group(2)).strip()
        if body in _DELETED:
            system += 1
            continue
        if _OMITTED.match(body):
            messages.append(Message(at, sender, "", media_omitted=True))
        elif f := (_ANDROID_FILE.match(body) or _IOS_FILE.match(body)):
            caption = (f.group(2) or "").strip()
            messages.append(Message(at, sender, caption, attachment=f.group(1).strip()))
        else:
            messages.append(Message(at, sender, body))
    return Chat(messages, day_first, ambiguous, system)


def plan(messages: list[Message]) -> tuple[list[Planned], int]:
    """Messages into saves (docs/04 · From messages to saves). Returns the saves and how many
    messages made none: media the export left out, and empty or punctuation-only messages."""
    planned: list[Planned] = []
    skipped = 0
    last_link: Planned | None = None  # a one-link save that could still take a label
    for msg in messages:
        if msg.media_omitted:
            skipped += 1
            continue
        if msg.attachment:
            planned.append(Planned(msg.at, msg.text, attachment=msg.attachment))
            last_link = None
            continue
        if not re.search(r"\w", msg.text):
            skipped += 1
            continue
        urls = find_urls(msg.text)
        if (
            not urls
            and last_link is not None
            and len(msg.text) <= LABEL_CHARS
            and timedelta(0) <= msg.at - last_link.at <= LABEL_WINDOW
        ):
            last_link.label = msg.text  # names the link above; not a save of its own
            last_link = None
            continue
        save = Planned(msg.at, msg.text)
        planned.append(save)
        own_words = msg.text.replace(urls[0], "").strip() if len(urls) == 1 else "x"
        last_link = save if len(urls) == 1 and not own_words else None
    return planned, skipped
