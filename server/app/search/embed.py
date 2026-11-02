"""Embeddings for search by meaning (ADR 0003): multilingual-e5-small, run here with ONNX.

Meta's API has no embedding model (checked 2 Nov: Spark, Wonder, Voice Transcribe, an image
model and SAM), so a small open one runs in our own processes: the API embeds questions, the
worker embeds saves. The quantized model is about 120 MB, downloaded once into EMBED_DIR and
loaded on first use. Nothing leaves our servers to be indexed.
"""

import threading
from pathlib import Path

import httpx
import numpy as np
import onnxruntime
from tokenizers import Tokenizer

from app.core.config import get_settings

REPO = "https://huggingface.co/Xenova/multilingual-e5-small/resolve/main"
FILES = {"model.onnx": "onnx/model_quantized.onnx", "tokenizer.json": "tokenizer.json"}
DIM = 384
MAX_TOKENS = 256  # a reading's title, what and facts fit; more adds little


def _download(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name, remote in FILES.items():
        target = folder / name
        if target.exists():
            continue
        part = target.with_suffix(target.suffix + ".part")
        with httpx.stream("GET", f"{REPO}/{remote}", follow_redirects=True, timeout=300) as res:
            res.raise_for_status()
            with part.open("wb") as out:
                for chunk in res.iter_bytes(1 << 20):
                    out.write(chunk)
        part.replace(target)


class Embedder:
    def __init__(self, folder: Path):
        _download(folder)
        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = 2  # a small server shares its cores with everything else
        self.session = onnxruntime.InferenceSession(
            str(folder / "model.onnx"), options, providers=["CPUExecutionProvider"]
        )
        self.inputs = {i.name for i in self.session.get_inputs()}
        self.tokenizer = Tokenizer.from_file(str(folder / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=MAX_TOKENS)
        pad = self.tokenizer.token_to_id("<pad>")
        self.tokenizer.enable_padding(pad_id=pad if pad is not None else 1, pad_token="<pad>")

    def embed(self, texts: list[str], kind: str) -> list[list[float]]:
        """Unit vectors, so cosine similarity is a dot product. e5 wants "query: " before a
        question and "passage: " before what it's matched against."""
        prefix = "query: " if kind == "query" else "passage: "
        encoded = self.tokenizer.encode_batch([prefix + " ".join(t.split()) for t in texts])
        ids = np.array([e.ids for e in encoded], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
        feeds = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self.inputs:
            feeds["token_type_ids"] = np.zeros_like(ids)
        hidden = self.session.run(None, feeds)[0]
        weights = mask[..., None].astype(np.float32)
        pooled = (hidden * weights).sum(axis=1) / np.clip(weights.sum(axis=1), 1e-9, None)
        pooled /= np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-9, None)
        return pooled.tolist()


_lock = threading.Lock()
_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    global _embedder
    with _lock:
        if _embedder is None:
            _embedder = Embedder(Path(get_settings().embed_dir))
        return _embedder
