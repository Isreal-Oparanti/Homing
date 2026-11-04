"""Ask, run by Muse Wonder as an agent (docs/03 · Ask; the Agents 101 loop, the Agents 102 gate).

Wonder picks its own steps with three tools: search the person's saves, open one, submit the
answer. Submitting is the gate it can't skip: code checks that every point's save was opened,
that its quote is in that save's text word for word, and that its numbers are in its quote. A
refused answer comes back with the problems named, and Wonder fixes them. Bounded: at most
MAX_TURNS model turns and MAX_REFUSALS refusals; after that only verified points are kept.
Wonder sees short ids (S1, S2…), never database ids, and only saves a search returned.
"""

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Ask, Reading, Save
from app.events.emitter import emit
from app.jobs.runner import JobContext
from app.llm.gateway import ModelGateway
from app.search.ask import THIN_CHARS, _source_text
from app.search.hybrid import search
from app.verify.quotes import match_quote
from app.verify.timestamps import numbers_supported

MAX_TURNS = 10
MAX_REFUSALS = 3
FOUND_PER_SEARCH = 8
MAX_POINTS = 6
WONDER = "muse-wonder-1.0"

# Tests swap this for a fake; agents never build clients themselves.
gateway_factory: Any = ModelGateway

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_saves",
            "description": "Search the person's saves by meaning. Returns save ids (S1, S2, …) "
            "with title, what it is, and when it was saved.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_save",
            "description": "Read one save's own text, by an id a search returned.",
            "parameters": {
                "type": "object",
                "properties": {"save": {"type": "string", "description": "e.g. S3"}},
                "required": ["save"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_answer",
            "description": "Submit the answer. Code checks every quote before the person sees it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "points": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "point": {"type": "string"},
                                "save": {"type": "string"},
                                "quote": {"type": "string"},
                            },
                            "required": ["point", "save", "quote"],
                        },
                    },
                    "not_covered": {"type": "array", "items": {"type": "string"}},
                    "also": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["points", "not_covered"],
            },
        },
    },
]


@dataclass
class Seen:
    """What the agent has seen: ids it may use, and the text it may quote."""

    db: Session
    user_id: str
    refs: dict[str, tuple[Save, Reading]] = field(default_factory=dict)
    by_save: dict[str, str] = field(default_factory=dict)
    opened: dict[str, str] = field(default_factory=dict)  # ref -> text
    searches: list[str] = field(default_factory=list)
    refusals: int = 0
    dropped: int = 0
    steps: list[dict[str, str]] = field(default_factory=list)  # shown live on the answer page

    def ref(self, save: Save, reading: Reading) -> str:
        if save.id not in self.by_save:
            r = f"S{len(self.refs) + 1}"
            self.refs[r] = (save, reading)
            self.by_save[save.id] = r
        return self.by_save[save.id]


def _search(s: Seen, query: str) -> list[dict[str, str]]:
    query = " ".join(str(query).split())[:200]
    s.searches.append(query)
    found = search(s.db, s.user_id, query, limit=FOUND_PER_SEARCH)
    return [
        {
            "save": s.ref(f.save, f.reading),
            "title": f.reading.title,
            "what": (f.reading.what or "")[:200],
            "saved": f"{f.save.saved_at:%d %b %Y}",
        }
        for f in found
    ]


def _open(s: Seen, ref: str) -> dict[str, Any]:
    if ref not in s.refs:
        return {"error": f"{ref} isn't a save a search returned. Search first."}
    save, reading = s.refs[ref]
    text = _source_text(s.db, save)
    if len(text) < THIN_CHARS:
        return {
            "save": ref,
            "title": reading.title,
            "text": text,
            "note": "Only a title or a few words: list it in `also`, don't quote it.",
        }
    s.opened[ref] = text
    return {"save": ref, "title": reading.title, "saved": f"{save.saved_at:%d %b %Y}", "text": text}


def _check(s: Seen, args: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """The gate: the points that hold up, a named problem for Wonder for each one that doesn't,
    and the same problems in the person's words (save titles, never Wonder's short ids)."""
    kept, problems, plain = [], [], []
    for n, p in enumerate(args.get("points") or [], 1):
        ref = str(p.get("save", "")).strip()
        point, quote = str(p.get("point", "")).strip(), str(p.get("quote", ""))
        text = s.opened.get(ref)
        if text is None:
            problems.append(f"Point {n}: {ref or 'no save'} wasn't opened. Open it, then quote it.")
            plain.append("it quoted a save it hadn't opened")
            continue
        title = s.refs[ref][1].title
        found = match_quote(quote, text)
        if found is None:
            problems.append(f"Point {n}: that quote isn't in {ref}'s text word for word.")
            plain.append(f"a quote wasn't word for word in “{title}”")
            continue
        exact = text[found.start : found.end]
        if not numbers_supported(point, exact):
            problems.append(f"Point {n}: it uses a number its quote from {ref} doesn't say.")
            plain.append(f"a number wasn't in its quote from “{title}”")
            continue
        save, reading = s.refs[ref]
        kept.append(
            {
                "point": point,
                "quote": exact,
                "save_id": save.id,
                "title": reading.title,
                "saved_at": save.saved_at.isoformat(),
            }
        )
    return kept[:MAX_POINTS], problems, plain


def _step(ctx: JobContext, ask: Ask, s: Seen, kind: str, text: str) -> None:
    """One step, written onto the question as it happens: the answer page shows it live."""
    s.steps.append({"kind": kind, "text": text})
    ask.answer = {"steps": list(s.steps)}
    ctx.db.commit()


def run_agent(ctx: JobContext, ask: Ask) -> dict[str, Any] | None:
    """The answer, or None when Wonder didn't get to one (the caller falls back)."""
    s = Seen(ctx.db, ask.user_id)
    gateway = gateway_factory(ctx.db)
    instructions = gateway.prompt("ask.agent")
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": instructions},
        {"role": "user", "content": f"QUESTION: {ask.question}"},
    ]
    for turn in range(MAX_TURNS):
        last = turn == MAX_TURNS - 1
        if last:
            # Muse Wonder only takes tool_choice="auto": the last turn is asked for in words.
            messages.append(
                {
                    "role": "user",
                    "content": "Last turn: call submit_answer now, with the points that hold up.",
                }
            )
        message = gateway.chat_tools(
            "ask.agent",
            user_id=ask.user_id,
            messages=messages,
            tools=TOOLS,
            save_ids=[sv.id for sv, _ in s.refs.values()],
        )
        messages.append(message.model_dump(mode="json", exclude_none=True))
        calls = message.tool_calls or []
        if not calls:
            messages.append({"role": "user", "content": "Call a tool."})
            continue
        for call in calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except ValueError:
                args = {}
            if name == "search_saves":
                result: Any = _search(s, args.get("query", ask.question))
                said = f"Searched your saves for “{s.searches[-1]}”: {len(result)} found."
                emit(
                    ctx.db, user_id=ask.user_id, agent="system", action="ask_searched", summary=said
                )
                _step(ctx, ask, s, "search", said)
            elif name == "open_save":
                result = _open(s, str(args.get("save", "")))
                if "error" not in result:
                    save, reading = s.refs[result["save"]]
                    said = f"Opened “{reading.title}” to read it for your question."
                    emit(
                        ctx.db,
                        user_id=ask.user_id,
                        agent="system",
                        action="ask_opened",
                        summary=said,
                        save_id=save.id,
                    )
                    _step(ctx, ask, s, "open", said)
            elif name == "submit_answer":
                kept, problems, plain = _check(s, args)
                if problems and s.refusals < MAX_REFUSALS and not last:
                    s.refusals += 1
                    said = (
                        f"Homing refused the answer: {len(problems)} of "
                        f"{len(args.get('points') or [])} points didn't hold up "
                        f"({plain[0]}). Sent back to Muse Wonder to fix."
                    )
                    emit(
                        ctx.db,
                        user_id=ask.user_id,
                        agent="system",
                        action="ask_refused",
                        summary=said,
                        models=[],  # code did this, not a model
                    )
                    _step(ctx, ask, s, "refused", said)
                    result = {"refused": True, "problems": problems}
                else:
                    s.dropped = len(problems)
                    s.steps.append(
                        {
                            "kind": "accepted",
                            "text": f"Homing found every quote word for word: {len(kept)} "
                            f"{'point holds' if len(kept) == 1 else 'points hold'} up"
                            + (f", {s.dropped} left out." if s.dropped else "."),
                        }
                    )
                    also = []
                    for ref in args.get("also") or []:
                        if ref in s.refs and ref not in s.opened:
                            save, reading = s.refs[ref]
                            also.append({"save_id": save.id, "title": reading.title})
                    ctx.db.commit()
                    return {
                        "points": kept,
                        "also": also,
                        "not_covered": [str(x) for x in args.get("not_covered") or []][:5],
                        "considered": len(s.refs),
                        "read": len(s.opened),
                        "dropped": s.dropped,
                        "steps": s.steps,
                        "agent": {
                            "model": WONDER,
                            "turns": turn + 1,
                            "searches": s.searches,
                            "opened": len(s.opened),
                            "refusals": s.refusals,
                        },
                    }
            else:
                result = {"error": f"No tool named {name}."}
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)[:12_000]}
            )
        ctx.db.commit()  # each step shows in Your agents as it happens
    return None
