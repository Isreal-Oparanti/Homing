"""What is it?, when the first read comes back thin: Muse Wonder digs for what the save points to.

Most saves are read in one pass. A post that only says "this 👇", a page that loads blank or
won't open, a link with a line of text and nothing behind it: there one read can only guess,
so Wonder works on it. It follows the save's links or searches, opens pages, and either picks
the page the save points to or decides the save says enough on its own. Code is the gate on
its pick: a page it opened, with real text, reached from the save's own links or naming what
the save names, word for word. That page joins the save's copy and Muse Spark reads it as
usual. Bounded by MAX_TURNS and the web budgets; None means the one-pass read goes ahead.
"""

import json
import time
from typing import Any

from app.agents.web_tools import OPEN_TOOL, SEARCH_TOOL, Web, host_of, plain, trim_context
from app.db.models import Save
from app.events.emitter import emit
from app.ingest.gather import SnapshotIn
from app.ingest.urls import find_urls
from app.jobs.runner import JobContext
from app.verify.quotes import match_quote

THIN_WORDS = 40  # fewer words than this, from the person and the page together: a thin read
WALL_WORDS = 150  # a page this short that reads like a wall is a wall
WALL_SIGNS = (
    "sign in to",
    "log in to",
    "login to continue",
    "enable javascript",
    "javascript is disabled",
    "accept cookies",
    "verify you are human",
    "are you a robot",
    "access denied",
    "subscribe to continue",
    "create an account to",
)
MAX_TURNS = 6
RUN_SECONDS = 120  # then the one-pass read goes ahead on what there is
MAX_LINKS_FROM_SAVE = 4
FOUND_BY = "read_agent"  # marks the page Wonder found, so a re-read doesn't dig again

READ_THIS_TOOL = {
    "type": "function",
    "function": {
        "name": "read_this",
        "description": "The page the save points to: one you opened (P1, P2, …). Code checks it.",
        "parameters": {
            "type": "object",
            "properties": {
                "page": {"type": "string"},
                "about_quote": {
                    "type": "string",
                    "description": "Words on that page naming what the save is about, copied "
                    "exactly (3-20 words). If you didn't reach the page from the save's own "
                    "links, these words must be in the save too.",
                },
            },
            "required": ["page", "about_quote"],
        },
    },
}
ENOUGH_TOOL = {
    "type": "function",
    "function": {
        "name": "enough",
        "description": "Stop: the save says enough on its own, or nothing more can be found. "
        "Say which, in one sentence.",
        "parameters": {
            "type": "object",
            "properties": {"why": {"type": "string"}},
            "required": ["why"],
        },
    },
}
TOOLS = [SEARCH_TOOL, OPEN_TOOL, READ_THIS_TOOL, ENOUGH_TOOL]


def own_words(save: Save) -> str:
    return " ".join(x for x in (save.label, save.text) if x)


def is_thin(save: Save, copies: list[str]) -> bool:
    """A link save (or a note with a link) whose words, the person's and the page's together,
    are too few to say what it is. Imports never dig: hundreds at a time, read for the gist."""
    if save.import_id or save.kind not in ("link", "note"):
        return False
    words = own_words(save)
    if not save.url and not find_urls(words):
        return False  # a plain note is the person's own words: nothing to follow
    for url in find_urls(words):
        words = words.replace(url, " ")
    if len(" ".join([words, *copies]).split()) < THIN_WORDS:
        return True
    # Words, but only a wall's: a sign-in, cookie or "enable JavaScript" page, not the thing.
    page = " ".join(copies)
    return len(page.split()) < WALL_WORDS and any(w in page.lower() for w in WALL_SIGNS)


def dig(
    ctx: JobContext, save: Save, copies: list[str], *, gateway: Any, web: Web
) -> SnapshotIn | None:
    def step(action: str, summary: str, **extra: Any) -> None:
        emit(
            ctx.db,
            user_id=save.user_id,
            agent="what",
            action=action,
            summary=summary,
            save_id=save.id,
            **extra,
        )
        ctx.db.commit()  # each step shows in Your agents as it happens

    words = own_words(save)
    urls = list(dict.fromkeys(([save.url] if save.url else []) + find_urls(words)))
    leads = web.add_leads(urls[:MAX_LINKS_FROM_SAVE])
    followed = {lead["ref"] for lead in leads}  # refs that come from the save's own links
    tied: set[str] = set()  # pages reached by following them
    brief = {
        "what_the_person_saved": words or None,
        "links_in_the_save": leads,
        "what_the_first_read_got": [c[:1500] for c in copies if c.strip()] or None,
    }
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": gateway.prompt("read.agent")},
        {"role": "user", "content": "SAVE: " + json.dumps(brief, ensure_ascii=False)},
    ]
    step("dig_started", "The first read came back thin, so Muse Wonder is looking for more.")
    ends = time.monotonic() + RUN_SECONDS
    for turn in range(MAX_TURNS):
        if time.monotonic() > ends:
            return None
        trim_context(messages)
        if turn == MAX_TURNS - 1:
            # Muse Wonder only takes tool_choice="auto": the last turn is asked for in words.
            messages.append({"role": "user", "content": "Last turn: call read_this or enough."})
        message = gateway.chat_tools(
            "read.agent",
            user_id=save.user_id,
            messages=messages,
            tools=TOOLS,
            save_ids=[save.id],
        )
        messages.append(message.model_dump(mode="json", exclude_none=True))
        calls = message.tool_calls or []
        if not calls:
            messages.append({"role": "user", "content": "Call a tool."})
            continue
        for call in calls:
            try:
                args = json.loads(call.function.arguments or "{}")
            except ValueError:
                args = {}
            name = call.function.name
            if name == "web_search":
                result: Any = web.run_search(args.get("query", ""))
                if "leads" in result:
                    step(
                        "dig_searched",
                        f"Searched the web for “{result['query']}”: {len(result['leads'])} leads.",
                    )
            elif name == "open_page":
                ref = str(args.get("ref", "")).strip().upper()
                result = web.open(ref)
                if "text" in result:
                    page = web.pages[result["page"]]
                    if ref in followed:
                        tied.add(page.ref)
                        followed.update(link["ref"] for link in result.get("links", []))
                    step(
                        "dig_opened",
                        f"Opened {result['site']}: “{result['title'][:90]}”.",
                        evidence=[{"label": result["site"], "url": page.url}],
                    )
            elif name == "read_this":
                page = web.pages.get(str(args.get("page", "")).strip().upper())
                quote = str(args.get("about_quote", ""))
                problem = None
                if page is None:
                    problem = "Pick a page you opened (P1, P2, …)."
                elif not match_quote(quote, page.text):
                    problem = f"Those words aren't on {page.ref} word for word."
                elif page.ref not in tied and not match_quote(quote, words):
                    problem = (
                        f"You didn't reach {page.ref} from the save's links, and those words "
                        "aren't in the save. Show it's what the save points to."
                    )
                if problem is None and page is not None:
                    step(
                        "dig_found",
                        f"Found what the save points to on {host_of(page.url)}. Reading it.",
                        evidence=[{"label": host_of(page.url), "url": page.url}],
                    )
                    meta = {"title": page.title, "found_by": FOUND_BY}
                    return SnapshotIn("page_text", page.text, page.url, meta)
                step("dig_refused", f"Homing refused that page: {plain(problem, web)}", models=[])
                result = {"accepted": False, "problem": problem}
            elif name == "enough":
                why = " ".join(str(args.get("why", "")).split())[:200]
                step("dig_done", f"Stopped looking: {plain(why, web) or 'nothing more to find.'}")
                return None
            else:
                result = {"error": f"No tool named {name}."}
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)[:12_000]}
            )
    return None
