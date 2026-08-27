"""Bridge helpers for read-only RAG context packages."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .rag_qa import run_rag_qa
from .rag_search import (
    SOURCE_TYPE_NXI,
    SOURCE_TYPE_PRODUCT_INFORMATION,
    SOURCE_TYPE_SIMILAR_REPORT,
    SOURCE_TYPE_SOP,
    SOURCE_TYPE_THEORY,
    render_hits_as_context,
    search_rag_documents,
)


RAG_OPTIONS = {
    "policy": {
        "source_types": [SOURCE_TYPE_SOP, SOURCE_TYPE_NXI, SOURCE_TYPE_PRODUCT_INFORMATION, SOURCE_TYPE_THEORY],
        "modality": "text",
    },
    "similar_case": {
        "source_types": [SOURCE_TYPE_SIMILAR_REPORT, SOURCE_TYPE_SOP, SOURCE_TYPE_NXI, SOURCE_TYPE_THEORY],
        "modality": "text",
    },
    "technical_basis": {
        "source_types": [SOURCE_TYPE_THEORY, SOURCE_TYPE_SOP, SOURCE_TYPE_NXI, SOURCE_TYPE_PRODUCT_INFORMATION],
        "modality": "text",
    },
}


def build_rag_context(
    query: str,
    *,
    top_k: int = 5,
    source_types: Sequence[str] | None = None,
    search_roots: Sequence[str] | None = None,
    db_root_path: str | None = None,
    modality: str = "text",
) -> dict[str, Any]:
    hits = search_rag_documents(
        query=query,
        top_k=top_k,
        source_types=source_types,
        search_roots=search_roots,
        db_root_path=db_root_path,
        modality=modality,
    )
    return {
        "enabled": bool(hits),
        "query": query,
        "source_types": list(source_types or []),
        "modality": modality,
        "hits": hits,
        "context_text": render_hits_as_context(hits),
        "read_only": True,
        "state_changed": False,
    }


def build_request_rag_package(
    state: Mapping[str, Any],
    *,
    question: str = "",
    top_k: int = 5,
    search_roots: Sequence[str] | None = None,
    db_root_path: str | None = None,
) -> dict[str, Any]:
    """Build a read-only package future draft stages may use as evidence."""

    package: dict[str, Any] = {
        "enabled": True,
        "read_only": True,
        "state_changed": False,
        "options": RAG_OPTIONS,
        "qa": None,
        "contexts": {},
    }
    if question:
        package["qa"] = run_rag_qa(
            question,
            state=state,
            top_k=top_k,
            search_roots=search_roots,
            db_root_path=db_root_path,
        )
    for name, config in RAG_OPTIONS.items():
        package["contexts"][name] = build_rag_context(
            question or name,
            top_k=top_k,
            source_types=config["source_types"],
            modality=config["modality"],
            search_roots=search_roots,
            db_root_path=db_root_path,
        )
    return package
