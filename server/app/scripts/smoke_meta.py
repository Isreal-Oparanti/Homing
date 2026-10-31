"""S0 model check: what can Meta's models read, and in which request shape?

Results (30 Oct 2026, muse-spark-1.3), recorded in docs/06-models.md:
- JSON schema output: works.
- Images: base64 data URL (JPEG, PNG, GIF, WebP). Remote URLs fail if the host blocks Meta's downloader.
- PDF: {"type": "file", "file": {"filename", "file_data": "data:application/pdf;base64,..."}} works; file URLs don't.
- Video: {"type": "video_url"} with an MP4 URL works, with timestamps. YouTube page links are rejected.
- reasoning_effort="low" roughly halves latency on simple extraction.

Run: python -m uv run python -m app.scripts.smoke_meta
One-off script, not a test. Results go into docs/06-models.md.
"""

import json
import time

from openai import OpenAI

from app.core.config import get_settings

YOUTUBE = "https://www.youtube.com/watch?v=5azEvwamu2Y"  # "debate preambles" Short, a saved demo video
IMAGE = "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3f/Fronalpstock_big.jpg/640px-Fronalpstock_big.jpg"
PDF = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"

settings = get_settings()
client = OpenAI(base_url=settings.meta_api_base, api_key=settings.meta_api_key, timeout=120)


def ask(label: str, model: str, content: object, **extra: object) -> None:
    started = time.perf_counter()
    try:
        r = client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": content}], **extra
        )
        text = (r.choices[0].message.content or "").strip().replace("\n", " ")
        usage = r.usage.model_dump() if r.usage else {}
        print(f"OK   {label} [{model}] {time.perf_counter() - started:.1f}s {usage}\n     {text[:300]}")
    except Exception as exc:  # report and move on: this script maps what works
        print(f"FAIL {label} [{model}] {type(exc).__name__}: {str(exc)[:300]}")


def main() -> None:
    m = settings.meta_spark_model
    schema = {
        "type": "json_schema",
        "json_schema": {
            "name": "reading",
            "schema": {
                "type": "object",
                "properties": {"title": {"type": "string"}, "deadline": {"type": "string"}},
                "required": ["title", "deadline"],
                "additionalProperties": False,
            },
        },
    }
    post = "Afreximbank Internship Programme closes TOMORROW! Deadline: 31 October 2026."
    ask("text + json_schema", m, f"Extract title and deadline: {post}", response_format=schema)
    ask("text + json_object", m, f"Return JSON with title and deadline: {post}",
        response_format={"type": "json_object"})
    ask("image_url", m, [
        {"type": "text", "text": "Describe this image in one sentence."},
        {"type": "image_url", "image_url": {"url": IMAGE}},
    ])
    for label, part in [
        ("pdf as file url", {"type": "file", "file": {"file_url": PDF}}),
        ("pdf as image_url", {"type": "image_url", "image_url": {"url": PDF}}),
    ]:
        ask(label, m, [{"type": "text", "text": "What does this PDF say?"}, part])
    for label, part in [
        ("youtube as video_url", {"type": "video_url", "video_url": {"url": YOUTUBE}}),
        ("youtube as file url", {"type": "file", "file": {"file_url": YOUTUBE}}),
        ("youtube in text", {"type": "text", "text": f"Video: {YOUTUBE}"}),
    ]:
        ask(label, m, [
            {"type": "text", "text": "Watch this video. Give 2 points it makes, each with a timestamp."},
            part,
        ])
    ask("text, muse-wonder", "muse-wonder-1.0", f"Extract title and deadline as JSON: {post}")
    print(json.dumps({"spark_model": m}))


if __name__ == "__main__":
    main()
