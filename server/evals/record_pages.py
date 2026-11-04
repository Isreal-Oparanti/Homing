"""Record real web pages for the finds-gate eval: our copy of each page's text, kept in
evals/finds_pages.jsonl so the eval runs the same way every time, offline.

Run from server/: python -m uv run python -m evals.record_pages
Labels (`expect`, `why`, `name`) are written by hand in PAGES below, from reading each page.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from app.ingest.fetch import FetchError, SafeFetcher
from app.ingest.gather import gather_web

HERE = Path(__file__).parent

# (url, the opportunity's name, what a careful person would do, why)
PAGES: list[tuple[str, str, str, str]] = [
    (
        "https://www.ycombinator.com/apply",
        "Y Combinator",
        "keep",
        "still accepting applications for the Winter 2027 batch",
    ),
    (
        "https://onevectasummit.com/execute-africa/",
        "Execute Africa AI Challenge",
        "keep",
        "a 2026 challenge asking teams to apply, with no closing date given",
    ),
    (
        "https://anzisha.org/apply/",
        "Anzisha Fellowship",
        "keep",
        "applications for the 2027 intake opened on 29 September 2026",
    ),
    (
        "https://www.opportunitiesforafricans.com/social-shifters-global-innovation-challenge-2026/",
        "Social Shifters Global Innovation Challenge",
        "refuse",
        "an opportunity blog, not the organisation's own site",
    ),
    (
        "https://www.socialshifters.co/global-innovation-challenge/",
        "Global Innovation Challenge",
        "refuse",
        "says its 2026 submissions are now closed",
    ),
    (
        "https://startup.google.com/programs/accelerator/africa/",
        "Google for Startups Accelerator",
        "refuse",
        "the 2026 programme already ran (April to June 2026)",
    ),
    (
        "https://menterprise.africa/october-2026-opportunities-for-africans/",
        "Build 2026 Innovation Expo",
        "refuse",
        "a list of 14 opportunities, not one of them",
    ),
    (
        "https://www.africabusinessheroes.org/",
        "Africa's Business Heroes",
        "refuse",
        "a home page with no date or sign that a call is open now",
    ),
    (
        "https://www.tonyelumelufoundation.org/tef-entrepreneurship-programme",
        "TEF Entrepreneurship Programme",
        "refuse",
        "describes the programme but gives no date or sign it's open now",
    ),
    (
        "https://acceler8.africa/",
        "Accelerate Africa",
        "refuse",
        "describes the programme but gives no date or sign it's open now",
    ),
    (
        "https://www.fatefoundation.org/",
        "FATE Foundation",
        "refuse",
        "an organisation's home page: news from April 2026, no open call",
    ),
    (
        "https://aueuyouth.com/",
        "AU-EU Youth Action Lab",
        "refuse",
        "a newsletter sign-up page with no call on it",
    ),
]


def main() -> None:
    fetcher = SafeFetcher()
    out = []
    for url, name, expect, why in PAGES:
        try:
            got = gather_web(url, fetcher)
        except FetchError as exc:
            print("SKIP", url, exc)
            continue
        if not got.snapshots:
            print("SKIP", url, got.notes)
            continue
        snap = got.snapshots[0]
        out.append(
            {
                "url": snap.source_url or url,
                "name": name,
                "expect": expect,
                "why": why,
                "recorded": datetime.now(UTC).date().isoformat(),
                "text": snap.text,
            }
        )
        print("OK", url, len(snap.text))
    (HERE / "finds_pages.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
