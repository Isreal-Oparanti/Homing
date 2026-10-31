"""The model gateway: the only way to call Meta's models (docs/adr/0006-model-gateway.md).

Every call names a purpose, which fixes the model, the versioned prompt and the output schema.
The gateway refuses private saves, masks phone numbers, caches by input hash, asks for exact
JSON, validates it with one repair attempt, and records every call in model_calls.
"""

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, TypeVar

import openai
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import ModelCall, Save
from app.jobs.errors import PermanentError, RetryableError
from app.schemas.agents import Reading
from app.verify.secrets import mask_phones

T = TypeVar("T", bound=BaseModel)
PROMPTS = Path(__file__).parent / "prompts"


@dataclass(frozen=True)
class Purpose:
    name: str
    prompt: str  # file in llm/prompts, versioned in its name
    output: type[BaseModel]
    timeout_s: float
    reasoning_effort: str | None = None


PURPOSES: dict[str, Purpose] = {
    "read.text": Purpose("read.text", "read_text.v1.md", Reading, 90, "low"),
}


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

    def run(
        self, purpose: str, *, user_id: str | None, inputs: dict[str, Any], save_ids: list[str]
    ) -> Any:
        p = PURPOSES[purpose]
        self._refuse_private(save_ids)
        model = self._settings.meta_spark_model
        instructions = (PROMPTS / p.prompt).read_text(encoding="utf-8")
        version = p.prompt.removesuffix(".md")
        user_text = render_blocks(inputs)
        input_hash = hashlib.sha256(f"{model}\n{version}\n{user_text}".encode()).hexdigest()

        cached = self._db.scalar(
            select(ModelCall.output)
            .where(ModelCall.input_hash == input_hash, ModelCall.status == "ok")
            .limit(1)
        )
        if cached is not None:
            return p.output.model_validate(cached)

        schema = inline_schema(p.output)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": instructions},
            {"role": "user", "content": user_text},
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
