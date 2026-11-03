"""Homing's evaluation: fixed test sets graded by plain code, plus what our checks did on
real runs. Writes evals/REPORT.md.

Run from server/: python -m uv run python -m evals.run
1. Dates: real and post-style date phrases, each with the answer worked out by hand.
2. Search: questions about Isreal's pile and the saves that should come back.
3. Verification and cost on real runs: what the models proposed, what code kept, tokens.
"""

import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select

from app.db.models import Ask, Card, ModelCall
from app.db.session import session_factory
from app.search.hybrid import search
from app.verify.dates import parse_deadline

HERE = Path(__file__).parent
OWNER = "google:103295685264461966275"
LAGOS = "Africa/Lagos"


def _rows(name: str) -> list[dict]:
    return [
        json.loads(line) for line in (HERE / name).read_text(encoding="utf-8").splitlines() if line
    ]


def dates() -> list[str]:
    cases = _rows("dates.jsonl")
    right, misses = 0, []
    for c in cases:
        got = parse_deadline(c["text"], base=datetime.fromisoformat(c["written_at"]), user_tz=LAGOS)
        want = datetime.fromisoformat(c["expected_utc"]) if c["expected_utc"] else None
        ok = (got is None and want is None) or (
            got is not None and want is not None and got.at.replace(second=0) == want
        )
        right += ok
        if not ok:
            misses.append(
                f"| {c['text']} | {want:%Y-%m-%d %H:%M}Z |"
                if want
                else f"| {c['text']} | no date |"
            )
            misses[-1] += f" {got.at:%Y-%m-%d %H:%M}Z |" if got else " no date |"
    out = [
        "## 1. Reading dates",
        "",
        f"**{right} of {len(cases)} right** ({100 * right // len(cases)}%). Each phrase was read "
        "as of when it was written, in Lagos time; the right answer was worked out by hand. "
        "No model: dates are read by code.",
    ]
    if misses:
        out += ["", "| Phrase | Right answer | Homing read |", "|---|---|---|", *misses]
    return out


def searches() -> list[str]:
    cases = _rows("search.jsonl")
    hits, recall, lines = 0, 0.0, []
    with session_factory()() as db:
        for c in cases:
            found = [f.reading.title for f in search(db, OWNER, c["query"], limit=10)]
            want = {t.lower() for t in c["expect"]}
            top5 = {t.lower() for t in found[:5]}
            top10 = {t.lower() for t in found}
            hit = bool(want & top5)
            share = len(want & top10) / len(want)
            hits += hit
            recall += share
            lines.append(
                f"| {c['query']} | {'yes' if hit else 'no'} | {len(want & top10)} of {len(want)} |"
            )
    return [
        "## 2. Search by meaning",
        "",
        f"**{hits} of {len(cases)} questions** had a right save in the top 5; on average "
        f"**{100 * recall / len(cases):.0f}%** of the right saves were in the top 10. "
        f"Run on Isreal's real pile. The right saves for each question are in "
        "`evals/search.jsonl`; Isreal checks them (draft until then).",
        "",
        "| Question | Right save in top 5 | Right saves in top 10 |",
        "|---|---|---|",
        *lines,
    ]


def verification() -> list[str]:
    with session_factory()() as db:
        kept = dropped = considered = asks = 0
        for answer in db.scalars(select(Ask.answer).where(Ask.status == "done")):
            if not answer:
                continue
            asks += 1
            kept += len(answer.get("points", []))
            dropped += int(answer.get("dropped", 0))
            considered += int(answer.get("considered", 0))
        p_kept = p_dropped = sheets = 0
        for payload in db.scalars(select(Card.payload).where(Card.kind == "prep")):
            sheet = (payload or {}).get("sheet") or {}
            if sheet.get("status") != "ready":
                continue
            sheets += 1
            p_kept += sum(len(v.get("points", [])) for v in sheet.get("videos", {}).values())
            p_dropped += int(sheet.get("dropped_points", 0))
        usage = db.execute(
            select(
                ModelCall.purpose,
                func.count(),
                func.coalesce(func.sum(ModelCall.tokens_in), 0),
                func.coalesce(func.sum(ModelCall.tokens_out), 0),
            )
            .where(ModelCall.status == "ok")
            .group_by(ModelCall.purpose)
            .order_by(func.count().desc())
        ).all()
    calls = sum(n for _, n, _, _ in usage)
    tokens = sum(i + o for _, _, i, o in usage)
    out = [
        "## 3. What the checks did on real runs",
        "",
        f"- **Ask:** {asks} answers. The model proposed {kept + dropped} points from "
        f"{considered} candidate saves; code found {kept} quotes word for word in the cited "
        f"save and dropped {dropped}.",
        f"- **Prep sheets:** {sheets} {'sheet' if sheets == 1 else 'sheets'}. "
        f"Of {p_kept + p_dropped} points taken from videos, "
        f"{p_kept} were found in the captions at the stated second and {p_dropped} "
        f"{'was' if p_dropped == 1 else 'were'} dropped.",
        "",
        f"**Model use so far:** {calls} calls, {tokens:,} tokens in all.",
        "",
        "| Purpose | Calls | Tokens per call |",
        "|---|---|---|",
    ]
    for purpose, n, t_in, t_out in usage:
        per = (t_in + t_out) // n if (t_in + t_out) else 0
        out.append(
            f"| {purpose} | {n} | {per:,} |" if per else f"| {purpose} | {n} | not reported |"
        )
    return out


def main() -> None:
    sections = [dates(), searches(), verification()]
    report = [
        "# Homing evaluation",
        "",
        f"_Run {datetime.now():%d %b %Y, %H:%M}. Every number below is computed by "
        "`evals/run.py` from fixed test sets or the stored record of real runs._",
    ]
    for s in sections:
        report += ["", *s]
    text = "\n".join(report) + "\n"
    (HERE / "REPORT.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
