"""The model gateway: the only way to call Meta's models (docs/adr/0006-model-gateway.md).

Every call names a purpose, which fixes the model, the versioned prompt and the output schema.
The gateway refuses private saves, masks phone numbers, caches by input hash, asks for exact
JSON, validates it with one repair attempt, and records every call in model_calls.
"""

import base64
import hashlib
import json
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, TypeVar

import httpx
import openai
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import ModelCall, Save, User
from app.jobs.errors import DeferredError, PermanentError, RetryableError
from app.llm import credits
from app.schemas.agents import (
    AskAnswer,
    AskPick,
    BatchReadings,
    FileReading,
    MomentMatch,
    Placement,
    PrepSheet,
    ProposedCheck,
    Reading,
    Rebuild,
    Transcript,
    VideoPoints,
)
from app.verify.secrets import mask_phones

T = TypeVar("T", bound=BaseModel)
PROMPTS = Path(__file__).parent / "prompts"


@dataclass(frozen=True)
class Attachment:
    """A file sent with the call: an image inline, or a PDF as file data (docs/06, S0)."""

    data: bytes
    mime: str
    name: str = "file"

    def part(self) -> dict[str, Any]:
        url = f"data:{self.mime};base64,{base64.b64encode(self.data).decode()}"
        if self.mime == "application/pdf":
            return {"type": "file", "file": {"filename": self.name, "file_data": url}}
        return {"type": "image_url", "image_url": {"url": url}}


@dataclass(frozen=True)
class VideoLink:
    """A video Spark fetches itself, from a short-lived link to our private bucket (docs/06)."""

    url: str
    sha256: str  # the file's own, so the cache doesn't depend on the link

    def part(self) -> dict[str, Any]:
        return {"type": "video_url", "video_url": {"url": self.url}}


@dataclass(frozen=True)
class Purpose:
    name: str
    prompt: str  # file in llm/prompts, versioned in its name
    output: type[BaseModel]
    timeout_s: float
    reasoning_effort: str | None = None
    model: str | None = None  # None: Muse Spark, the default


# Not a chat purpose: Muse Voice Transcribe has its own endpoint (ModelGateway.transcribe).
TRANSCRIBE = Purpose("transcribe.voice", "none", Transcript, 180)

PURPOSES: dict[str, Purpose] = {
    "read.text": Purpose("read.text", "read_text.v3.md", Reading, 90, "low"),
    # Up to 20 small saves from an import at once: the instructions are sent once, not 20 times.
    "read.batch": Purpose("read.batch", "read_batch.v1.md", BatchReadings, 150, "low"),
    "read.file": Purpose("read.file", "read_file.v1.md", FileReading, 120, "low"),
    # A video with little or no speech: Spark watches it from a short-lived private link.
    "read.video": Purpose("read.video", "read_video.v1.md", Reading, 180, "low"),
    # Comparing with a source is the hardest call, so it keeps the default reasoning effort.
    "check.compare": Purpose("check.compare", "check_compare.v2.md", ProposedCheck, 120),
    "place.assign": Purpose("place.assign", "place_assign.v1.md", Placement, 45, "low"),
    # When will you need it? (S11): which goals a moment the person typed needs.
    "when.match_moment": Purpose("when.match_moment", "match_moment.v1.md", MomentMatch, 45, "low"),
    # Ask (S10): pick the saves that help, then answer from them with quotes code verifies.
    "ask.select": Purpose("ask.select", "ask_select.v1.md", AskPick, 60, "low"),
    "ask.answer": Purpose("ask.answer", "ask_answer.v1.md", AskAnswer, 120),
    # Muse Wonder runs Ask as an agent: it picks its own tools; code is the gate (search/ask_agent).
    "ask.agent": Purpose(
        "ask.agent", "ask_agent.v1.md", AskAnswer, 120, "low", model="muse-wonder-1.0"
    ),
    # Is it true? finds the source with Wonder; code checks the page it chooses (source_agent).
    "check.agent": Purpose(
        "check.agent", "check_source.v1.md", AskAnswer, 120, "low", model="muse-wonder-1.0"
    ),
    # What's it for? finds more: Wonder goes on the web for a goal; code is the gate (finds_more).
    "find.agent": Purpose(
        "find.agent", "find_more.v1.md", AskAnswer, 120, "low", model="muse-wonder-1.0"
    ),
    # The whole pile in one long-context call: it sees every save, so it groups them well.
    "place.rebuild": Purpose("place.rebuild", "place_rebuild.v1.md", Rebuild, 300),
    "video.points": Purpose("video.points", "video_points.v1.md", VideoPoints, 120, "low"),
    "prep.sheet": Purpose("prep.sheet", "prep_sheet.v3.md", PrepSheet, 120),
}


OUTPUT_TOKENS_ESTIMATE = 1500
VIDEO_TOKENS_ESTIMATE = 20_000  # a 5 MB video was 15,530 tokens in (1 Nov)
TRANSCRIBE_MAX_CONCURRENCY = 2


class BudgetExceeded(DeferredError):
    """Today's token budget (all users, or this user) is used up. Runs again tomorrow."""


@lru_cache
def _semaphore(limit: int) -> threading.BoundedSemaphore:
    return threading.BoundedSemaphore(limit)


def inline_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema with $refs inlined and closed objects, which strict JSON modes expect."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].split("/")[-1]])
            # Drop schema annotations, but never entries of `properties` (a field may be
            # called "title").
            out = {
                k: ({name: walk(sub) for name, sub in v.items()} if k == "properties" else walk(v))
                for k, v in node.items()
                if k not in ("title", "default")
            }
            if out.get("type") == "object":
                out["additionalProperties"] = False
                out["required"] = list(out.get("properties", {}).keys())
            return out
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(schema)


def render_blocks(inputs: dict[str, Any]) -> str:
    """Inputs as labelled blocks: <<NAME>> … <</NAME>>."""
    parts = []
    for name, value in inputs.items():
        body = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=1)
        parts.append(f"<<{name.upper()}>>\n{body}\n<</{name.upper()}>>")
    return mask_phones("\n\n".join(parts))


class ModelGateway:
    def __init__(self, db: Session, settings: Settings | None = None):
        self._db = db
        self._settings = settings or get_settings()
        self._client = openai.OpenAI(
            base_url=self._settings.meta_api_base,
            api_key=self._settings.meta_api_key,
            max_retries=2,  # 429/5xx with backoff, inside the call
        )

    def _refuse_private(self, save_ids: list[str]) -> None:
        if not save_ids:
            return
        private = self._db.scalar(
            select(Save.id).where(Save.id.in_(save_ids), Save.visibility == "private").limit(1)
        )
        if private:
            raise PermanentError("This save is private, so it's never sent to a model.")

    def _check_budget(self, user_id: str | None, input_estimate: int) -> None:
        """Tokens used today, by everyone and by this user, plus this call must fit."""
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        used = func.coalesce(ModelCall.tokens_in, 0) + func.coalesce(ModelCall.tokens_out, 0)
        total, mine = self._db.execute(
            select(
                func.coalesce(func.sum(used), 0),
                func.coalesce(func.sum(used).filter(ModelCall.user_id == user_id), 0),
            ).where(ModelCall.created_at >= today)
        ).one()
        estimate = input_estimate + OUTPUT_TOKENS_ESTIMATE
        user_limit = self._settings.model_user_daily_token_budget
        if user_id and self._db.scalar(select(User.is_demo).where(User.id == user_id)):
            user_limit = self._settings.model_demo_daily_token_budget  # shared by all visitors
        over_total = total + estimate > self._settings.model_daily_token_budget
        over_user = bool(user_id) and mine + estimate > user_limit
        if over_total or over_user:
            raise BudgetExceeded(
                "Today's model budget is used up.", until=today + timedelta(days=1, minutes=5)
            )

    def run(
        self,
        purpose: str,
        *,
        user_id: str | None,
        inputs: dict[str, Any],
        save_ids: list[str],
        attachments: list[Attachment | VideoLink] | None = None,
    ) -> Any:
        p = PURPOSES[purpose]
        self._refuse_private(save_ids)
        model = p.model or self._settings.meta_spark_model
        credits.note(model, save_ids)
        instructions = (PROMPTS / p.prompt).read_text(encoding="utf-8")
        version = p.prompt.removesuffix(".md")
        user_text = render_blocks(inputs)
        files = "".join(
            a.sha256 if isinstance(a, VideoLink) else hashlib.sha256(a.data).hexdigest()
            for a in attachments or []
        )
        key = f"{model}\n{version}\n{user_text}\n{files}"
        input_hash = hashlib.sha256(key.encode()).hexdigest()

        cached = self._db.scalar(
            select(ModelCall.output)
            .where(ModelCall.input_hash == input_hash, ModelCall.status == "ok")
            .limit(1)
        )
        if cached is not None:
            return p.output.model_validate(cached)

        # Characters / 4 is a rough token count; good enough for a daily guard. Files are counted
        # as one token per 3 bytes, capped per file (images cost far less than that).
        file_tokens = sum(
            VIDEO_TOKENS_ESTIMATE if isinstance(a, VideoLink) else min(len(a.data) // 3, 20_000)
            for a in attachments or []
        )
        self._check_budget(user_id, (len(instructions) + len(user_text)) // 4 + file_tokens)

        schema = inline_schema(p.output)
        content: Any = user_text
        if attachments:
            content = [{"type": "text", "text": user_text}, *(a.part() for a in attachments)]
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": instructions},
            {"role": "user", "content": content},
        ]
        started = time.perf_counter()
        usage: dict[str, int] = {"in": 0, "out": 0}
        try:
            raw = self._complete(p, model, messages, schema, usage)
            try:
                result = p.output.model_validate_json(raw)
            except ValidationError as err:
                messages += [
                    {"role": "assistant", "content": raw},
                    {
                        "role": "user",
                        "content": f"That JSON didn't match the schema: {err.errors()[:5]}. "
                        "Return corrected JSON only.",
                    },
                ]
                raw = self._complete(p, model, messages, schema, usage)
                result = p.output.model_validate_json(raw)
        except ValidationError as err:
            self._record(
                p,
                version,
                model,
                user_id,
                input_hash,
                "invalid_output",
                usage,
                started,
                error=str(err)[:2000],
            )
            raise RetryableError(f"{purpose}: model output didn't match the schema") from err
        except openai.APIStatusError as err:
            self._record(
                p,
                version,
                model,
                user_id,
                input_hash,
                "error",
                usage,
                started,
                error=f"{err.status_code}: {err.message}"[:2000],
            )
            if err.status_code in (400, 401, 403, 404, 422):
                raise PermanentError(
                    f"The model rejected this request ({err.status_code})."
                ) from err
            raise RetryableError(f"{purpose}: model error {err.status_code}") from err
        except openai.APIConnectionError as err:
            self._record(
                p,
                version,
                model,
                user_id,
                input_hash,
                "error",
                usage,
                started,
                error=str(err)[:2000],
            )
            raise RetryableError(f"{purpose}: couldn't reach the model") from err

        self._record(
            p,
            version,
            model,
            user_id,
            input_hash,
            "ok",
            usage,
            started,
            output=result.model_dump(mode="json"),
        )
        return result

    def prompt(self, purpose: str) -> str:
        return (PROMPTS / PURPOSES[purpose].prompt).read_text(encoding="utf-8")

    def chat_tools(
        self,
        purpose: str,
        *,
        user_id: str | None,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        save_ids: list[str],
        tool_choice: Any = "auto",
    ) -> Any:
        """One turn of an agent that picks its own tools (Muse Wonder). Returns the assistant
        message (text and tool calls). Budgeted, recorded and credited like every call; not
        cached, because a turn depends on everything before it."""
        p = PURPOSES[purpose]
        self._refuse_private(save_ids)
        model = p.model or self._settings.meta_spark_model
        credits.note(model, save_ids)
        version = p.prompt.removesuffix(".md")
        sent = json.dumps(messages, default=str)
        self._check_budget(user_id, len(sent) // 4)
        input_hash = hashlib.sha256(f"{model}\n{version}\n{sent}".encode()).hexdigest()
        started = time.perf_counter()
        usage = {"in": 0, "out": 0}
        extra: dict[str, Any] = {}
        if p.reasoning_effort:
            extra["reasoning_effort"] = p.reasoning_effort
        try:
            with _semaphore(self._settings.spark_max_concurrency):
                response = self._client.chat.completions.create(
                    model=model,
                    messages=messages,  # type: ignore[arg-type]
                    tools=tools,  # type: ignore[arg-type]
                    tool_choice=tool_choice,
                    max_tokens=4000,
                    timeout=p.timeout_s,
                    extra_body=extra or None,
                )
        except openai.APIStatusError as err:
            self._record(
                p,
                version,
                model,
                user_id,
                input_hash,
                "error",
                usage,
                started,
                error=f"{err.status_code}: {err.message}"[:2000],
            )
            if err.status_code in (400, 401, 403, 404, 422):
                raise PermanentError(
                    f"The model rejected this request ({err.status_code})."
                ) from err
            raise RetryableError(f"{purpose}: model error {err.status_code}") from err
        except openai.APIConnectionError as err:
            self._record(
                p,
                version,
                model,
                user_id,
                input_hash,
                "error",
                usage,
                started,
                error=str(err)[:2000],
            )
            raise RetryableError(f"{purpose}: couldn't reach the model") from err
        if response.usage:
            usage = {"in": response.usage.prompt_tokens, "out": response.usage.completion_tokens}
        message = response.choices[0].message
        self._record(
            p,
            version,
            model,
            user_id,
            input_hash,
            "ok",
            usage,
            started,
            output=message.model_dump(mode="json", exclude_none=True),
        )
        return message

    def transcribe(self, wav: bytes, *, user_id: str | None, save_ids: list[str]) -> Transcript:
        """Muse Voice Transcribe: 16 kHz mono WAV in (10 minutes at most), the words out. Cached
        by the sound itself and recorded in model_calls like every other call."""
        self._refuse_private(save_ids)
        model = self._settings.meta_transcribe_model
        credits.note(model, save_ids)
        input_hash = hashlib.sha256(f"{model}\nasr\n".encode() + hashlib.sha256(wav).digest())
        input_hash_hex = input_hash.hexdigest()
        cached = self._db.scalar(
            select(ModelCall.output)
            .where(ModelCall.input_hash == input_hash_hex, ModelCall.status == "ok")
            .limit(1)
        )
        if cached is not None:
            return Transcript.model_validate(cached)
        started = time.perf_counter()
        usage = {"in": 0, "out": 0}  # billed by sound, not tokens
        request = {"model": model, "audioEncoding": "WAV", "mode": "PUSH_TO_TALK"}
        try:
            with _semaphore(TRANSCRIBE_MAX_CONCURRENCY):
                res = httpx.post(
                    f"{self._settings.meta_api_base}/asr/transcribe",
                    headers={
                        "Authorization": f"Bearer {self._settings.meta_api_key}",
                        "Accept": "application/json",
                    },
                    files={
                        "request": (None, json.dumps(request), "application/json"),
                        "audio": ("sound.wav", wav, "audio/wav"),
                    },
                    timeout=TRANSCRIBE.timeout_s,
                )
        except httpx.HTTPError as err:
            self._record(
                TRANSCRIBE,
                "asr",
                model,
                user_id,
                input_hash_hex,
                "error",
                usage,
                started,
                error=type(err).__name__,
            )
            raise RetryableError("transcribe: couldn't reach the model") from err
        if res.status_code >= 400:
            self._record(
                TRANSCRIBE,
                "asr",
                model,
                user_id,
                input_hash_hex,
                "error",
                usage,
                started,
                error=f"{res.status_code}: {res.text[:500]}",
            )
            if res.status_code in (400, 401, 403, 404, 413, 415, 422):
                raise PermanentError(f"The model rejected this sound ({res.status_code}).")
            raise RetryableError(f"transcribe: model error {res.status_code}")
        body = res.json()
        result = Transcript(
            text=" ".join(str(body.get("transcript") or "").split()),
            duration_ms=int(body.get("audioDurationMs") or 0),
        )
        self._record(
            TRANSCRIBE,
            "asr",
            model,
            user_id,
            input_hash_hex,
            "ok",
            usage,
            started,
            output=result.model_dump(mode="json"),
        )
        return result

    def _complete(
        self,
        p: Purpose,
        model: str,
        messages: list[dict[str, Any]],
        schema: dict[str, Any],
        usage: dict[str, int],
    ) -> str:
        extra: dict[str, Any] = {}
        if p.reasoning_effort:
            extra["reasoning_effort"] = p.reasoning_effort
        with _semaphore(self._settings.spark_max_concurrency):
            response = self._client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore[arg-type]
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": p.name.replace(".", "_"), "schema": schema},
                },  # type: ignore[arg-type]
                timeout=p.timeout_s,
                **extra,
            )
        if response.usage:
            usage["in"] += response.usage.prompt_tokens or 0
            usage["out"] += response.usage.completion_tokens or 0
        return response.choices[0].message.content or "{}"

    def _record(
        self,
        p: Purpose,
        version: str,
        model: str,
        user_id: str | None,
        input_hash: str,
        status: str,
        usage: dict[str, int],
        started: float,
        *,
        output: Any = None,
        error: str | None = None,
    ) -> None:
        self._db.add(
            ModelCall(
                user_id=user_id,
                purpose=p.name,
                model=model,
                prompt_version=version,
                input_hash=input_hash,
                status=status,
                tokens_in=usage["in"] or None,
                tokens_out=usage["out"] or None,
                latency_ms=round((time.perf_counter() - started) * 1000),
                output=output,
                error=error,
            )
        )
        self._db.flush()
