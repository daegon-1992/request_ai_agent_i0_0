"""Optional local embedding runtime for Chroma vector reranking."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import importlib.util
import math
import os
from pathlib import Path
import struct
import threading
from typing import Any, Sequence

from .config import env_flag, repo_root


TOKENIZER_FILES = (
    "tokenizer.json",
    "sentencepiece.bpe.model",
    "tokenizer.model",
    "vocab.json",
)
_MODEL_LOAD_LOCK = threading.Lock()


def _clean(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def _has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (repo_root() / path).resolve()


def _resolve_bundle_relative(value: str | Path, bundle_root: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    bundle_candidate = (bundle_root / path).resolve()
    repo_candidate = (repo_root() / path).resolve()
    return bundle_candidate if bundle_candidate.exists() else repo_candidate


def vector_bundle_root() -> Path:
    configured = _clean(os.getenv("REQUEST_AGENT_VECTOR_BUNDLE_ROOT"))
    if configured:
        return _resolve_path(configured)
    return repo_root() / "VectorDB+EmbedModels"


def default_vector_db_root() -> Path:
    configured = _clean(os.getenv("DEFAULT_DB_ROOT_PATH") or os.getenv("REQUEST_AGENT_VECTOR_DB_ROOT"))
    if configured:
        return _resolve_bundle_relative(configured, vector_bundle_root())
    return (vector_bundle_root() / "data").resolve()


def default_text_model_path() -> Path:
    configured = _clean(
        os.getenv("TEXT_MODEL_PATH")
        or os.getenv("REQUEST_AGENT_TEXT_MODEL_PATH")
        or os.getenv("REQUEST_AGENT_TEXT_EMBEDDING_MODEL_PATH")
    )
    if configured:
        return _resolve_bundle_relative(configured, vector_bundle_root())
    return (vector_bundle_root() / "models" / "multilingual-e5-large").resolve()


def default_clip_model_path() -> Path:
    configured = _clean(os.getenv("CLIP_MODEL_PATH") or os.getenv("REQUEST_AGENT_CLIP_MODEL_PATH"))
    if configured:
        return _resolve_bundle_relative(configured, vector_bundle_root())
    return (vector_bundle_root() / "models" / "clip-vit-base-patch32").resolve()


@dataclass(frozen=True)
class EmbeddingSettings:
    enabled: bool
    backend: str
    vector_search_enabled: bool
    vector_bundle_root: Path
    db_root_path: Path
    text_model_path: Path
    clip_model_path: Path


def embedding_settings() -> EmbeddingSettings:
    return EmbeddingSettings(
        enabled=env_flag("REQUEST_AGENT_EMBEDDING_ENABLED", default=True),
        backend=_clean(os.getenv("REQUEST_AGENT_EMBEDDING_BACKEND")) or "local_e5",
        vector_search_enabled=env_flag("REQUEST_AGENT_VECTOR_SEARCH_ENABLED", default=True),
        vector_bundle_root=vector_bundle_root(),
        db_root_path=default_vector_db_root(),
        text_model_path=default_text_model_path(),
        clip_model_path=default_clip_model_path(),
    )


def _tokenizer_files_present(model_path: Path) -> list[str]:
    return [name for name in TOKENIZER_FILES if (model_path / name).exists()]


def embedding_status() -> dict[str, Any]:
    settings = embedding_settings()
    deps = {
        "chromadb": _has_module("chromadb"),
        "sentence_transformers": _has_module("sentence_transformers"),
        "transformers": _has_module("transformers"),
        "torch": _has_module("torch"),
        "safetensors": _has_module("safetensors"),
        "tokenizers": _has_module("tokenizers"),
    }
    tokenizer_files = _tokenizer_files_present(settings.text_model_path)
    model_files = {
        "config_json": (settings.text_model_path / "config.json").exists(),
        "model_safetensors": (settings.text_model_path / "model.safetensors").exists(),
        "tokenizer_files": tokenizer_files,
    }
    local_loader_ready = (
        settings.enabled
        and settings.backend == "local_e5"
        and settings.text_model_path.exists()
        and bool(tokenizer_files)
        and (
            deps["sentence_transformers"]
            or (deps["transformers"] and deps["torch"] and deps["safetensors"])
        )
    )
    return {
        "enabled": settings.enabled,
        "backend": settings.backend,
        "vector_search_enabled": settings.vector_search_enabled,
        "vector_bundle_root": str(settings.vector_bundle_root),
        "db_root_path": str(settings.db_root_path),
        "text_model_path": str(settings.text_model_path),
        "clip_model_path": str(settings.clip_model_path),
        "paths": {
            "vector_bundle_root_exists": settings.vector_bundle_root.exists(),
            "db_root_path_exists": settings.db_root_path.exists(),
            "text_model_path_exists": settings.text_model_path.exists(),
            "clip_model_path_exists": settings.clip_model_path.exists(),
        },
        "dependencies": deps,
        "model_files": model_files,
        "query_embedding_ready": local_loader_ready,
        "runtime_mode": "local_e5_vector_rerank" if local_loader_ready else "metadata_keyword_fallback",
        "limitations": []
        if local_loader_ready
        else [
            "Local E5 query embedding requires tokenizer files and sentence_transformers or transformers+torch+safetensors.",
            "Until then, Chroma document metadata/keyword search remains active as a fallback.",
        ],
    }


def _prefix_e5_query(text: str) -> str:
    clean = " ".join(_clean(text).split())
    return f"query: {clean}" if clean and not clean.lower().startswith("query:") else clean


@lru_cache(maxsize=1)
def _sentence_transformer_model(model_path: str) -> Any:
    from sentence_transformers import SentenceTransformer  # type: ignore

    return SentenceTransformer(model_path)


@lru_cache(maxsize=1)
def _transformer_model(model_path: str) -> tuple[Any, Any, Any]:
    import torch  # type: ignore
    from transformers import AutoModel, AutoTokenizer  # type: ignore

    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model = AutoModel.from_pretrained(model_path)
    model.eval()
    return tokenizer, model, torch


def _average_pool(last_hidden_states: Any, attention_mask: Any, torch: Any) -> Any:
    mask = attention_mask.unsqueeze(-1).expand(last_hidden_states.size()).float()
    masked = last_hidden_states * mask
    return masked.sum(1) / torch.clamp(mask.sum(1), min=1e-9)


def embed_query(text: str) -> dict[str, Any]:
    """Return a local E5 query embedding or a structured disabled payload."""

    settings = embedding_settings()
    if not settings.enabled or not settings.vector_search_enabled:
        return {"ok": False, "reason": "embedding_disabled", "vector": []}
    if settings.backend != "local_e5":
        return {"ok": False, "reason": f"unsupported_backend:{settings.backend}", "vector": []}
    if not settings.text_model_path.exists():
        return {"ok": False, "reason": "text_model_path_missing", "vector": []}
    if not _tokenizer_files_present(settings.text_model_path):
        return {"ok": False, "reason": "tokenizer_files_missing", "vector": []}

    query = _prefix_e5_query(text)
    model_path = str(settings.text_model_path)
    try:
        if _has_module("sentence_transformers"):
            with _MODEL_LOAD_LOCK:
                model = _sentence_transformer_model(model_path)
            vector = model.encode([query], normalize_embeddings=True)[0]
            return {
                "ok": True,
                "backend": "sentence_transformers",
                "model": model_path,
                "vector": [float(item) for item in vector],
            }
        if _has_module("transformers") and _has_module("torch") and _has_module("safetensors"):
            with _MODEL_LOAD_LOCK:
                tokenizer, model, torch = _transformer_model(model_path)
            encoded = tokenizer([query], padding=True, truncation=True, return_tensors="pt")
            with torch.no_grad():
                output = model(**encoded)
                pooled = _average_pool(output.last_hidden_state, encoded["attention_mask"], torch)
                normalized = torch.nn.functional.normalize(pooled, p=2, dim=1)
            return {
                "ok": True,
                "backend": "transformers",
                "model": model_path,
                "vector": [float(item) for item in normalized[0].tolist()],
            }
        return {"ok": False, "reason": "embedding_dependencies_missing", "vector": []}
    except Exception as exc:  # pragma: no cover - optional local runtime dependent
        return {"ok": False, "reason": f"embedding_load_failed:{exc}", "vector": []}


def decode_float32_vector(blob: bytes | bytearray | memoryview | None) -> list[float]:
    if not blob:
        return []
    raw = bytes(blob)
    if len(raw) % 4:
        return []
    count = len(raw) // 4
    try:
        return [float(item) for item in struct.unpack(f"<{count}f", raw)]
    except struct.error:
        return []


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float | None:
    if not left or not right or len(left) != len(right):
        return None
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for a, b in zip(left, right):
        dot += a * b
        left_norm += a * a
        right_norm += b * b
    if left_norm <= 0 or right_norm <= 0:
        return None
    return dot / (math.sqrt(left_norm) * math.sqrt(right_norm))
