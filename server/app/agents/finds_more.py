"""What's it for? finds more: Muse Wonder goes on the web for one of the person's goals.

Starting from what they saved for the goal, Wonder searches, opens pages, follows a blog's
links to the organisation's own page, and proposes what it found. Code is the gate (docs/05):

- the page was opened, and it's the organisation's own (never a blog, list or social post);
- the opportunity's name is on it word for word, and every number in the summary is too;
- it isn't closed, and its closing date, read by code from the page's own words, is ahead;
- who can apply, quoted from the page, is judged by code against the person's profile.
  Wonder never sees the profile: a find that isn't for the person is left out, quietly.

A refused proposal comes back with the problem named, and Wonder fixes it or moves on.
Bounded: MAX_TURNS turns, the web budgets in web_tools, MAX_FINDS finds a run. Every step is
written to Your agents as it happens.
"""

import json
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.agents import goal_memory
from app.agents.is_it_true import facts_for
from app.agents.web_tools import (
    OPEN_TOOL,
    SEARCH_TOOL,
    Page,
    Web,
    host_of,
    plain,
    trim_context,
)
from app.db.models import AgentEvent, Check, Find, Job, Reading, Save, Thread, ThreadSave, User
from app.events.emitter import emit
from app.ingest.fetch import SafeFetcher
from app.jobs import queue
from app.jobs.errors import PermanentError
from app.jobs.runner import JobContext
from app.llm.gateway import AgentShareUsed, ModelGateway
from app.llm.search import NOT_THE_ORGANISATION, get_search
from app.schemas.agents import ProposedCheck
from app.verify.dates import parse_deadline
from app.verify.eligibility import accept_rule, assess
from app.verify.quotes import match_quote
from app.verify.sources import NEVER_OFFICIAL
from app.verify.status import is_closed
from app.verify.timestamps import numbers_supported
from app.verify.verdict import decide

MAX_TURNS = 12
RUN_SECONDS = 360  # well under the queue's 15 minutes before it calls a job stuck
MAX_FINDS = 4
MAX_GOAL_SAVES = 8
SOURCE_CHARS_FOR_MODEL = 40_000
WONDER = "muse-wonder-1.0"
YEAR = re.compile(r"\b20\d\d\b")

# Tests swap these for fakes; agents never build clients themselves.
gateway_factory: Any = ModelGateway
fetcher_factory: Any = SafeFetcher
search_factory: Any = get_search

PROPOSE_TOOL = {
    "type": "function",
    "function": {
        "name": "propose_find",
        "description": "Propose one opportunity from a page you opened (P1, P2, …). Code checks "
        "it before the person sees it and names any problem.",
        "parameters": {
            "type": "object",
            "properties": {
                "page": {"type": "string", "description": "The organisation's own page, e.g. P4"},
                "name": {"type": "string", "description": "The opportunity's name"},
                "name_quote": {
                    "type": "string",
                    "description": "Words naming it, copied exactly from that page (3-20 words)",
                },
                "what": {
                    "type": "string",
                    "description": "One plain sentence: what it is and why it serves the goal. "
                    "Only numbers its quote states.",
                },
                "what_quote": {
                    "type": "string",
                    "description": "Words from that page backing the sentence, copied exactly "
                    "(5-40 words)",
                },
            },
            "required": ["page", "name", "name_quote", "what", "what_quote"],
        },
    },
}
PLAN_TOOL = {
    "type": "function",
    "function": {
        "name": "plan",
        "description": "First, before anything else: your plan for this run, from the goal, "
        "what they saved and what you know from before. The person sees it.",
        "parameters": {
            "type": "object",
            "properties": {
                "looking_for": {
                    "type": "string",
                    "description": "What kind of opportunity, for whom, where, e.g. 'equity-free "
                    "grants for early-stage founders in Nigeria'",
                },
                "rule_out": {
                    "type": "string",
                    "description": "What you'll skip and why, from what you know from before",
                },
                "first_searches": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Two or three specific searches to start with",
                },
            },
            "required": ["looking_for", "rule_out", "first_searches"],
        },
    },
}
FINISH_TOOL = {
    "type": "function",
    "function": {
        "name": "finish",
        "description": "Stop looking. Leave yourself one lesson for next time.",
        "parameters": {
            "type": "object",
            "properties": {
                "note": {"type": "string", "description": "What you looked for, in one line"},
                "lesson": {
                    "type": "string",
                    "description": "One line for your next run: what worked, or what to avoid",
                },
            },
            "required": ["note", "lesson"],
        },
    },
}
TOOLS = [PLAN_TOOL, SEARCH_TOOL, OPEN_TOOL, PROPOSE_TOOL, FINISH_TOOL]


def _key(url: str) -> str:
    """The same page, however it was linked: host and path, no query, no trailing slash."""
    parts = urlsplit(url)
    return f"{host_of(url)}{parts.path.rstrip('/')}".lower()


def _official_host(host: str) -> bool:
    blocked = NEVER_OFFICIAL + tuple(d for d in NOT_THE_ORGANISATION if "." in d)
    return bool(host) and not any(host == d or host.endswith("." + d) for d in blocked)


@dataclass
class Run:
    ctx: JobContext
    user: User
    thread: Thread
    web: Web
    known: set[str]  # pages already in their saves or found before
    save_ids: list[str]
    found: list[Find] = field(default_factory=list)
    refused: int = 0
    left_out: int = 0
    stopped: str | None = None
    refusals: list[dict[str, str]] = field(default_factory=list)  # site and why, for memory
    plan: dict[str, Any] | None = None
    lesson: str | None = None

    def step(self, action: str, summary: str, **extra: Any) -> None:
        emit(
            self.ctx.db,
            user_id=self.user.id,
            agent="for",
            action=action,
            summary=summary,
            thread_id=self.thread.id,
            **extra,
        )
        self.ctx.db.commit()  # each step shows in Your agents as it happens


def _goal_saves(ctx: JobContext, thread: Thread) -> list[tuple[Save, Reading]]:
    return list(
        ctx.db.execute(
            select(Save, Reading)
            .join(ThreadSave, ThreadSave.save_id == Save.id)
            .join(Reading, Reading.save_id == Save.id)
            .where(ThreadSave.thread_id == thread.id, Save.visibility != "private")
            .order_by(Save.saved_at.desc())
            .limit(MAX_GOAL_SAVES)
        ).all()
    )


def _known_pages(ctx: JobContext, user_id: str) -> set[str]:
    urls = list(
        ctx.db.scalars(select(Save.url).where(Save.user_id == user_id, Save.url.is_not(None)))
    )
    urls += list(
        ctx.db.scalars(
            select(Check.official_url)
            .join(Save, Save.id == Check.save_id)
            .where(Save.user_id == user_id, Check.official_url.is_not(None))
        )
    )
    urls += list(ctx.db.scalars(select(Find.url).where(Find.user_id == user_id)))
    return {_key(u) for u in urls if u}


def _gate(run: Run, args: dict[str, Any]) -> tuple[Find | None, str | None, bool]:
    """(the find, None, _) when it holds up; (None, the problem for Wonder, left_out) when not.
    `left_out` means it was fine but not for this person: Wonder is told only to move on."""
    page: Page | None = run.web.pages.get(str(args.get("page", "")).strip().upper())
    name = " ".join(str(args.get("name", "")).split())[:120]
    what = " ".join(str(args.get("what", "")).split())[:300]
    if page is None:
        return None, "Propose from a page you opened (P1, P2, …).", False
    host = host_of(page.url)
    if not _official_host(host):
        return None, f"{host} isn't the organisation's own site. Follow its links to it.", False
    if _key(page.url) in run.known:
        return None, "That one is already in their saves. Look for others.", False
    if not name or not match_quote(str(args.get("name_quote", "")), page.text):
        return None, f"The name quote isn't on {page.ref} word for word. Copy it exactly.", False
    backing = match_quote(str(args.get("what_quote", "")), page.text)
    if backing is None:
        return (
            None,
            f"The summary's quote isn't on {page.ref} word for word. Copy it exactly.",
            False,
        )
    backed = page.text[backing.start : backing.end]
    if not what or not numbers_supported(what, backed):
        return None, "The summary uses a number its quote doesn't state. Drop it.", False
    if closed := is_closed(page.text):
        return None, f"The page says it's closed (“{closed.quote}”). Look for others.", False

    proposed: ProposedCheck = gateway_factory(run.ctx.db).run(
        "find.compare",
        user_id=run.user.id,
        inputs={
            "save": {"text": f"{name}: {what}", "what": what, "key_facts": {}},
            "source": {"url": page.url, "text": page.text[:SOURCE_CHARS_FOR_MODEL]},
        },
        save_ids=[],
    )
    if not proposed.is_same_opportunity:
        return None, f"{page.ref} isn't a page for that one opportunity. Find its own page.", False
    now = datetime.now(UTC)
    deadline = None
    if proposed.deadline_quote and (m := match_quote(proposed.deadline_quote, page.text)):
        said = page.text[m.start : m.end]
        if YEAR.search(said):  # without a year, an old page's date would look like next year's
            deadline = parse_deadline(said, base=now, user_tz=run.user.tz)
    if deadline is not None and deadline.at < now:
        return None, f"It closed ({deadline.source_text}). Look for others.", False
    if deadline is None and not open_this_year(page.text, now):
        return None, "The page gives no sign it's open this year. Look for others.", False

    rules = [r for p in proposed.rules if (r := accept_rule(p.model_dump(), page.text))]
    judged = assess(rules, facts_for(run.ctx.db, run.user.id, None), ref_year=now.year).rules
    verdict = decide(closed=False, past_deadline=False, source_opened=True, rules=judged)
    if not judged:
        verdict = "checked"  # the page doesn't say who can apply: never "fits you" on nothing
    if verdict == "not_for_you":
        return None, "Code left that one out: it isn't for this person. Look for others.", True

    name_said = match_quote(str(args.get("name_quote", "")), page.text)
    quotes = [
        {"label": "Named on the page", "quote": page.text[name_said.start : name_said.end]},
        {"label": "What the page says", "quote": backed},
    ]
    if deadline is not None:
        quotes.append({"label": "Closing date", "quote": deadline.source_text})
    return (
        Find(
            user_id=run.user.id,
            thread_id=run.thread.id,
            from_save_ids=run.save_ids,
            name=name,
            what=what,
            url=page.url,
            deadline_at=deadline.at if deadline else None,
            deadline_text=deadline.source_text if deadline else None,
            verdict=verdict,
            rules=judged,
            quotes=quotes,
        ),
        None,
        False,
    )


FIT_WORDS = {
    "fits_you": "fits you",
    "needs_your_answer": "one thing to check to see if it fits you",
    "checked": "open to apply; the page doesn't say who can",
}
APPLY_WORDS = ("appl", "deadline", "cohort", "call for", "intake", "submission", "register", "open")
FOOTER_WORDS = ("©", "copyright", "rights reserved")


def open_this_year(text: str, now: datetime) -> bool:
    """With no closing date: the page names this year or next beside words about applying.
    A year in a copyright footer says nothing about whether a call is open."""
    for m in re.finditer(rf"\b(?:{now.year}|{now.year + 1})\b", text):
        near = text[max(0, m.start() - 120) : m.end() + 120].lower()
        if any(w in near for w in FOOTER_WORDS):
            continue
        if any(w in near for w in APPLY_WORDS):
            return True
    return False


def _instructions(run: Run, saves: list[tuple[Save, Reading]]) -> str:
    lines = [
        f"- {r.title}: {r.what}"
        + (
            f" (organisations: {', '.join(r.key_facts['organisations'][:3])})"
            if (r.key_facts or {}).get("organisations")
            else ""
        )
        for _, r in saves
    ]
    return (
        f"GOAL: {run.thread.title}\n\nWHAT THEY SAVED FOR IT:\n"
        + "\n".join(lines)
        + "\n\n"
        + goal_memory.brief(goal_memory.load(run.ctx.db, run.user.id, run.thread.id))
    )


def find_more(ctx: JobContext, payload: dict[str, Any]) -> None:
    if ctx.user_id is None:
        raise PermanentError("goal.find needs a user.")
    thread = ctx.db.get(Thread, str(payload.get("thread_id")))
    user = ctx.db.get(User, ctx.user_id)
    if thread is None or user is None or thread.user_id != ctx.user_id or thread.archived_at:
        return
    since = datetime.now(UTC) - timedelta(hours=20)
    looked = ctx.db.scalar(
        select(AgentEvent.id).where(
            AgentEvent.thread_id == thread.id,
            AgentEvent.action == "find_started",
            AgentEvent.created_at > since,
        )
    )
    if looked is not None and not payload.get("asked"):
        return  # once a day on its own; a tap on Find more always runs
    saves = _goal_saves(ctx, thread)
    if not any(r.is_opportunity for _, r in saves):
        return  # finding more means more opportunities: nothing to start from here
    run = Run(
        ctx,
        user,
        thread,
        Web(search_factory(), fetcher_factory()),
        _known_pages(ctx, user.id),
        [s.id for s, _ in saves],
    )
    gateway = gateway_factory(ctx.db)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": gateway.prompt("find.agent")},
        {"role": "user", "content": _instructions(run, saves)},
    ]
    run.step("find_started", f"Looking on the web for more for '{thread.title}'.")
    try:
        _loop(run, gateway, messages)
    except AgentShareUsed:
        ctx.db.rollback()
        run.stopped = "today's share of the budget for web agents is used up"
    _wrap_up(run)


def _loop(run: Run, gateway: Any, messages: list[dict[str, Any]]) -> None:
    ctx, user, thread = run.ctx, run.user, run.thread
    ends = time.monotonic() + RUN_SECONDS
    for turn in range(MAX_TURNS):
        if time.monotonic() > ends:
            run.stopped = "it reached its time limit"
            return
        last = turn == MAX_TURNS - 1
        trim_context(messages)
        if last:
            # Muse Wonder only takes tool_choice="auto": the last turn is asked for in words.
            messages.append(
                {"role": "user", "content": "Last turn: call finish now, with your lesson."}
            )
        # Plan first, with more thought (code holds every other step until there's a plan);
        # then act quickly.
        message = gateway.chat_tools(
            "find.agent",
            user_id=user.id,
            messages=messages,
            tools=TOOLS,
            save_ids=run.save_ids,
            effort="medium" if run.plan is None else None,
        )
        messages.append(message.model_dump(mode="json", exclude_none=True))
        calls = message.tool_calls or []
        if not calls:
            messages.append({"role": "user", "content": "Call a tool."})
            continue
        done = False
        planning = any(c.function.name == "plan" for c in calls)
        for call in sorted(calls, key=lambda c: c.function.name != "plan"):  # a plan goes first
            try:
                args = json.loads(call.function.arguments or "{}")
            except ValueError:
                args = {}
            name = call.function.name
            if run.plan is None and not planning:
                result: Any = {"error": "Plan first: call plan before anything else."}
            elif name == "plan":
                run.plan = args
                looking = " ".join(str(args.get("looking_for", "")).split())[:200]
                skip = " ".join(str(args.get("rule_out", "")).split())[:200]
                run.step(
                    "find_planned",
                    f"Plan: looking for {looking}." + (f" Ruling out: {skip}." if skip else ""),
                )
                result = {"ok": True, "next": "Run your first searches now."}
            elif name == "web_search":
                result = run.web.run_search(args.get("query", thread.title))
                if "leads" in result:
                    run.step(
                        "find_searched",
                        f"Searched the web for “{result['query']}”: {len(result['leads'])} leads.",
                    )
            elif name == "open_page":
                result = run.web.open(args.get("ref", ""))
                if "page" in result and "text" in result:
                    run.step(
                        "find_opened",
                        f"Opened {result['site']}: “{result['title'][:90]}”.",
                        evidence=[
                            {"label": result["site"], "url": run.web.pages[result["page"]].url}
                        ],
                    )
            elif name == "propose_find":
                find, problem, left_out = _gate(run, args)
                label = " ".join(str(args.get("name", "a page")).split())[:90]
                if find is not None and not _keep(ctx, find):
                    find, problem = None, "Already found before. Look for others."
                if find is not None:
                    run.found.append(find)
                    run.known.add(_key(find.url))
                    closes = ""
                    if find.deadline_at is not None:
                        day = find.deadline_at.astimezone(ZoneInfo(user.tz))
                        closes = f", closes {day.day} {day:%b}"
                    run.step(
                        "found",
                        f"Found for '{thread.title}': {find.name} ({host_of(find.url)}){closes}. "
                        f"Checked on its own page; {FIT_WORDS.get(find.verdict, 'open')}.",
                        evidence=[{"label": host_of(find.url), "url": find.url}]
                        + [
                            {"label": q["label"], "url": find.url, "quote": q["quote"]}
                            for q in find.quotes
                        ],
                    )
                    result = {"accepted": True, "found": len(run.found), "max": MAX_FINDS}
                    if len(run.found) >= MAX_FINDS:
                        done = True
                elif left_out:
                    run.left_out += 1
                    run.step("find_left_out", f"Left out {label}: it isn't for you.", models=[])
                    result = {"accepted": False, "problem": problem}
                else:
                    assert problem is not None
                    run.refused += 1
                    seen = run.web.pages.get(str(args.get("page", "")).strip().upper())
                    run.refusals.append(
                        {
                            "site": host_of(seen.url) if seen else label,
                            "why": problem.split(". ")[0],
                        }
                    )
                    run.step(
                        "find_refused",
                        f"Homing refused {label}: {plain(problem.split('. ')[0], run.web)}.",
                        models=[],
                    )
                    result = {"accepted": False, "problem": problem}
            elif name == "finish":
                done = True
                run.lesson = " ".join(str(args.get("lesson", "")).split())[:200] or None
                result = {"ok": True}
            else:
                result = {"error": f"No tool named {name}."}
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)[:12_000]}
            )
        if done:
            return


def _keep(ctx: JobContext, find: Find) -> bool:
    """Store a find once: two runs for one goal can't both keep the same page."""
    try:
        with ctx.db.begin_nested():
            ctx.db.add(find)
        return True
    except IntegrityError:
        return False


def _wrap_up(run: Run) -> None:
    n = len(run.found)
    said = (
        f"Looked for more for '{run.thread.title}': searched {len(run.web.queries)} ways, "
        f"opened {len(run.web.pages)} pages, found {n}"
    )
    if run.refused or run.left_out:
        said += f" ({run.refused} refused by Homing, {run.left_out} not for you)"
    if run.stopped:
        said += f". Stopped early: {run.stopped}"
    if run.lesson:
        said += f". Next time: {run.lesson.rstrip('.')}"
    # What this run teaches the next one.
    found_by: dict[str, int] = {}
    for find in run.found:
        page = next((p for p in run.web.pages.values() if p.url == find.url), None)
        if page is not None and page.query:
            found_by[page.query] = found_by.get(page.query, 0) + 1
    goal_memory.remember(
        run.ctx.db,
        run.user.id,
        run.thread.id,
        searched=[{"query": q, "found": found_by.get(q, 0)} for q in run.web.queries],
        refused=run.refusals,
        lessons=[run.lesson] if run.lesson else [],
    )
    run.step("find_done", said + ".")


def queue_find(
    db: Any, user_id: str, thread_id: str, *, priority: int, asked: bool = False
) -> None:
    """One live run per goal. On its own (a new save, Keep watching) a goal is looked at once a
    day; a tap always runs, and turns a run already waiting into an asked one."""
    key = f"find:{thread_id}"
    queued = queue.enqueue(
        db,
        "goal.find",
        {"thread_id": thread_id, "asked": asked},
        user_id=user_id,
        priority=priority,
        dedupe_key=key,
        max_attempts=1,
    )
    if queued is None and asked:
        db.execute(
            update(Job)
            .where(Job.dedupe_key == key, Job.status == "queued")
            .values(payload={"thread_id": thread_id, "asked": True}, priority=priority)
        )
