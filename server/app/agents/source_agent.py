"""Is it true?, finding the source: Muse Wonder looks for the page a save should be checked against.

It starts from the links in the save, searches when they don't lead anywhere, and follows a
blog's or post's links to the organisation's own page. Code is the gate on its choice: a page
it opened, the organisation's own site (never a blog, list or social post), with real text,
naming what the save is about word for word. After that, is_it_true compares and verifies as
always. Bounded by MAX_TURNS and the web budgets; None means the fixed path takes over.
"""

import json
from typing import Any

from app.agents.web_tools import OPEN_TOOL, SEARCH_TOOL, Web, host_of
from app.db.models import Reading, Save
from app.events.emitter import emit
from app.ingest.gather import SnapshotIn
from app.ingest.urls import find_urls
from app.jobs.runner import JobContext
from app.llm.search import NOT_THE_ORGANISATION
from app.verify.quotes import match_quote
from app.verify.sources import NEVER_OFFICIAL

MAX_TURNS = 8
MAX_LINKS_FROM_SAVE = 6

CHOOSE_TOOL = {
    "type": "function",
    "function": {
        "name": "choose_source",
        "description": "The page to check the save against: one you opened (P1, P2, …), on the "
        "organisation's own site. Code checks it.",
        "parameters": {
            "type": "object",
            "properties": {
                "page": {"type": "string"},
                "name_quote": {
                    "type": "string",
                    "description": "Words on that page naming what the save is about, copied "
                    "exactly (3-20 words)",
                },
            },
            "required": ["page", "name_quote"],
        },
    },
}
GIVE_UP_TOOL = {
    "type": "function",
    "function": {
        "name": "give_up",
        "description": "No page on the organisation's own site could be found. Say why.",
        "parameters": {
            "type": "object",
            "properties": {"why": {"type": "string"}},
            "required": ["why"],
        },
    },
}
TOOLS = [SEARCH_TOOL, OPEN_TOOL, CHOOSE_TOOL, GIVE_UP_TOOL]


def official_host(host: str) -> bool:
    blocked = NEVER_OFFICIAL + tuple(d for d in NOT_THE_ORGANISATION if "." in d)
    return bool(host) and not any(host == d or host.endswith("." + d) for d in blocked)


def find_source(
    ctx: JobContext,
    save: Save,
    reading: Reading,
    words: str,
    *,
    gateway: Any,
    web: Web,
) -> tuple[str, SnapshotIn] | None:
    def step(action: str, summary: str, **extra: Any) -> None:
        emit(
            ctx.db,
            user_id=save.user_id,
            agent="true",
            action=action,
            summary=summary,
            save_id=save.id,
            **extra,
        )
        ctx.db.commit()  # each step shows in Your agents as it happens

    urls = find_urls(words) + ([save.url] if save.url else [])
    leads = web.add_leads(urls[:MAX_LINKS_FROM_SAVE])
    facts = reading.key_facts or {}
    brief = {
        "title": reading.title,
        "what": reading.what,
        "organisations": facts.get("organisations", [])[:3],
        "links_in_the_save": leads,
    }
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": gateway.prompt("check.agent")},
        {"role": "user", "content": "SAVE: " + json.dumps(brief, ensure_ascii=False)},
    ]
    for turn in range(MAX_TURNS):
        last = turn == MAX_TURNS - 1
        message = gateway.chat_tools(
            "check.agent",
            user_id=save.user_id,
            messages=messages,
            tools=TOOLS,
            save_ids=[save.id],
            tool_choice={"type": "function", "function": {"name": "give_up"}} if last else "auto",
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
                result: Any = web.run_search(args.get("query", reading.title))
                if "leads" in result:
                    step(
                        "source_searched",
                        f"Searched the web for “{result['query']}”: {len(result['leads'])} leads.",
                    )
            elif name == "open_page":
                result = web.open(args.get("ref", ""))
                if "text" in result:
                    page = web.pages[result["page"]]
                    step(
                        "source_opened",
                        f"Opened {result['site']}: “{result['title'][:90]}”.",
                        evidence=[{"label": result["site"], "url": page.url}],
                    )
            elif name == "choose_source":
                page = web.pages.get(str(args.get("page", "")).strip().upper())
                quote = str(args.get("name_quote", ""))
                problem = None
                if page is None:
                    problem = "Choose a page you opened (P1, P2, …)."
                elif not official_host(host_of(page.url)):
                    problem = f"{host_of(page.url)} isn't the organisation's own site."
                elif not match_quote(quote, page.text):
                    problem = f"Those words aren't on {page.ref} word for word."
                if problem is None and page is not None:
                    step(
                        "source_chosen",
                        f"Chose {host_of(page.url)} as the source to check against.",
                        evidence=[{"label": host_of(page.url), "url": page.url}],
                    )
                    return page.url, SnapshotIn(
                        "page_text", page.text, page.url, {"title": page.title}
                    )
                step("source_refused", f"Homing refused that source: {problem}", models=[])
                result = {"accepted": False, "problem": problem}
            elif name == "give_up":
                return None
            else:
                result = {"error": f"No tool named {name}."}
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)[:12_000]}
            )
    return None
