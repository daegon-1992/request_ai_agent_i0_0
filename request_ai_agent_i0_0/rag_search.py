"""Read-only lightweight RAG search utilities for the request assistant."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterable, Mapping, Sequence

from .embedding_runtime import (
    cosine_similarity,
    decode_float32_vector,
    embed_query,
)


SOURCE_TYPE_SOP = "sop"
SOURCE_TYPE_NXI = "nxi"
SOURCE_TYPE_SIMILAR_REPORT = "similar_report"
SOURCE_TYPE_THEORY = "theory_basis"
SOURCE_TYPE_PRODUCT_INFORMATION = "product_information"

SOURCE_TYPE_LABELS = {
    SOURCE_TYPE_SOP: "SOP",
    SOURCE_TYPE_NXI: "NXI",
    SOURCE_TYPE_SIMILAR_REPORT: "유사보고서",
    SOURCE_TYPE_THEORY: "이론",
    SOURCE_TYPE_PRODUCT_INFORMATION: "제품정보",
}

SOURCE_TYPE_ALIASES = {
    "sop": SOURCE_TYPE_SOP,
    "standard": SOURCE_TYPE_NXI,
    "nxi": SOURCE_TYPE_NXI,
    "report": SOURCE_TYPE_SIMILAR_REPORT,
    "similar_report": SOURCE_TYPE_SIMILAR_REPORT,
    "similar report": SOURCE_TYPE_SIMILAR_REPORT,
    "유사보고서": SOURCE_TYPE_SIMILAR_REPORT,
    "유사 보고서": SOURCE_TYPE_SIMILAR_REPORT,
    "theory": SOURCE_TYPE_THEORY,
    "theory_basis": SOURCE_TYPE_THEORY,
    "이론": SOURCE_TYPE_THEORY,
    "이론근거": SOURCE_TYPE_THEORY,
    "product": SOURCE_TYPE_PRODUCT_INFORMATION,
    "information": SOURCE_TYPE_PRODUCT_INFORMATION,
    "product_information": SOURCE_TYPE_PRODUCT_INFORMATION,
    "제품정보": SOURCE_TYPE_PRODUCT_INFORMATION,
    "제품 정보": SOURCE_TYPE_PRODUCT_INFORMATION,
}

SEARCH_SUFFIXES = {".txt", ".md", ".py", ".json", ".csv"}
MAX_FILE_BYTES = 1_200_000
DEFAULT_MAX_CHARS = 900


@dataclass(frozen=True)
class SearchDocument:
    path: Path
    source_type: str
    text: str


@dataclass(frozen=True)
class ChromaDocument:
    db_path: Path
    embedding_id: int
    source_type: str
    text: str
    source: str
    file_path: str
    location: str
    collection: str
    categories: str
    doc_type: str


def _clean(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def _normalize_space(value: Any) -> str:
    return " ".join(_clean(value).split())


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _normalize_source_type(value: Any) -> str:
    token = _normalize_space(value).lower()
    return SOURCE_TYPE_ALIASES.get(token, token)


def normalize_source_types(source_types: Sequence[str] | None) -> list[str]:
    if not source_types:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in source_types:
        normalized = _normalize_source_type(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _infer_source_type(path: Path) -> str:
    token = str(path).lower()
    name = path.name.lower()
    if any(part in token for part in ("sop", "operating procedure", "기준서", "절차", "사용자기준흐름")):
        return SOURCE_TYPE_SOP
    if any(part in token for part in ("nxi", "standard", "표준")):
        return SOURCE_TYPE_NXI
    if any(part in token for part in ("report", "보고서", "case study", "유사")):
        return SOURCE_TYPE_SIMILAR_REPORT
    if any(part in token for part in ("product", "products", "제품정보", "제품 정보", "information")):
        return SOURCE_TYPE_PRODUCT_INFORMATION
    if any(part in name for part in ("theory", "이론", "fluentdocs", "userguide")):
        return SOURCE_TYPE_THEORY
    return SOURCE_TYPE_THEORY


def _infer_source_type_from_metadata(*values: Any) -> str:
    token = " ".join(_normalize_space(value).lower() for value in values if _normalize_space(value))
    if any(part in token for part in ("sop", "operating procedure", "절차")):
        return SOURCE_TYPE_SOP
    if any(part in token for part in ("nxi", "standard", "표준")):
        return SOURCE_TYPE_NXI
    if any(part in token for part in ("report", "보고서", "similar")):
        return SOURCE_TYPE_SIMILAR_REPORT
    if any(part in token for part in ("product", "products", "information", "제품")):
        return SOURCE_TYPE_PRODUCT_INFORMATION
    if any(part in token for part in ("theory", "userguide", "fluent", "이론")):
        return SOURCE_TYPE_THEORY
    return SOURCE_TYPE_THEORY


def _candidate_roots(search_roots: Sequence[str | Path] | None = None, db_root_path: str | None = None) -> list[Path]:
    raw_roots: list[str | Path] = []
    if search_roots:
        raw_roots.extend(search_roots)
    explicit_roots = bool(raw_roots)
    env_roots = _clean(os.getenv("REQUEST_RAG_ROOTS"))
    if env_roots and not explicit_roots:
        raw_roots.extend(part for part in env_roots.split(os.pathsep) if _clean(part))
    if db_root_path:
        raw_roots.append(db_root_path)
    env_db_root = _clean(os.getenv("DEFAULT_DB_ROOT_PATH"))
    if env_db_root and not explicit_roots:
        raw_roots.append(env_db_root)
    if not raw_roots:
        vector_data_root = _repo_root() / "VectorDB+EmbedModels" / "data"
        data_root = _repo_root() / "data"
        if vector_data_root.exists():
            raw_roots.append(vector_data_root)
        elif data_root.exists():
            raw_roots.append(data_root)
        else:
            raw_roots.append(_repo_root() / "Reference")

    roots: list[Path] = []
    seen: set[str] = set()
    for raw in raw_roots:
        path = Path(raw)
        if not path.is_absolute():
            bundle_candidate = (_repo_root() / "VectorDB+EmbedModels" / path).resolve()
            repo_candidate = (_repo_root() / path).resolve()
            path = bundle_candidate if bundle_candidate.exists() else repo_candidate
        else:
            path = path.resolve()
        key = str(path).lower()
        if key in seen or not path.exists():
            continue
        seen.add(key)
        roots.append(path)
    return roots


def _read_text(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return ""
    except OSError:
        return ""
    for encoding in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return path.read_text(encoding=encoding, errors="strict")
        except UnicodeDecodeError:
            continue
        except OSError:
            return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def iter_search_documents(
    *,
    search_roots: Sequence[str | Path] | None = None,
    db_root_path: str | None = None,
    source_types: Sequence[str] | None = None,
) -> list[SearchDocument]:
    wanted = set(normalize_source_types(source_types))
    documents: list[SearchDocument] = []
    for root in _candidate_roots(search_roots, db_root_path):
        paths = [root] if root.is_file() else [path for path in root.rglob("*") if path.is_file()]
        for path in paths:
            if path.suffix.lower() not in SEARCH_SUFFIXES:
                continue
            source_type = _infer_source_type(path)
            if wanted and source_type not in wanted:
                continue
            text = _read_text(path)
            if not _normalize_space(text):
                continue
            documents.append(SearchDocument(path=path, source_type=source_type, text=text))
    return documents


def _chroma_enabled() -> bool:
    return _normalize_space(os.getenv("REQUEST_AGENT_CHROMA_ENABLED", "1")).lower() not in {"0", "false", "no", "off"}


def _chroma_db_paths(search_roots: Sequence[str | Path] | None = None, db_root_path: str | None = None) -> list[Path]:
    paths: list[Path] = []
    seen: set[str] = set()
    for root in _candidate_roots(search_roots, db_root_path):
        candidates = [root] if root.is_file() else list(root.rglob("chroma.sqlite3"))
        for path in candidates:
            if path.name.lower() != "chroma.sqlite3":
                continue
            key = str(path.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            paths.append(path.resolve())
    return paths


def _sqlite_tables(connection: sqlite3.Connection) -> set[str]:
    try:
        rows = connection.execute("select name from sqlite_master where type='table'").fetchall()
    except sqlite3.Error:
        return set()
    return {_normalize_space(row[0]) for row in rows}


def _iter_chroma_db_documents(db_path: Path, *, source_types: Sequence[str] | None = None) -> list[ChromaDocument]:
    wanted = set(normalize_source_types(source_types))
    try:
        try:
            connection = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
        except sqlite3.OperationalError:
            # SQLite URI read-only mode is not portable for Windows UNC paths.
            # This fallback still performs only SELECT statements.
            connection = sqlite3.connect(str(db_path))
    except sqlite3.Error:
        return []
    try:
        tables = _sqlite_tables(connection)
        if "embedding_metadata" not in tables:
            return []
        has_embeddings = "embeddings" in tables
        has_segments = "segments" in tables
        has_collections = "collections" in tables
        if has_embeddings and has_segments and has_collections:
            query = """
                select
                    doc.id,
                    doc.string_value as document,
                    coalesce(src.string_value, '') as source,
                    coalesce(fp.string_value, '') as file_path,
                    coalesce(loc.string_value, '') as location,
                    coalesce(cat.string_value, '') as categories,
                    coalesce(dt.string_value, '') as doc_type,
                    coalesce(chunk.string_value, '') as chunk_id,
                    coalesce(c.name, '') as collection
                from embedding_metadata doc
                left join embedding_metadata src on src.id = doc.id and src.key = 'source'
                left join embedding_metadata fp on fp.id = doc.id and fp.key = 'file_path'
                left join embedding_metadata loc on loc.id = doc.id and loc.key = 'location'
                left join embedding_metadata cat on cat.id = doc.id and cat.key = 'categories'
                left join embedding_metadata dt on dt.id = doc.id and dt.key = 'doc_type'
                left join embedding_metadata chunk on chunk.id = doc.id and chunk.key = 'chunk_id'
                left join embeddings e on e.id = doc.id
                left join segments s on s.id = e.segment_id
                left join collections c on c.id = s.collection
                where doc.key = 'chroma:document' and doc.string_value is not null
            """
        else:
            query = """
                select
                    doc.id,
                    doc.string_value as document,
                    coalesce(src.string_value, '') as source,
                    coalesce(fp.string_value, '') as file_path,
                    coalesce(loc.string_value, '') as location,
                    coalesce(cat.string_value, '') as categories,
                    coalesce(dt.string_value, '') as doc_type,
                    coalesce(chunk.string_value, '') as chunk_id,
                    '' as collection
                from embedding_metadata doc
                left join embedding_metadata src on src.id = doc.id and src.key = 'source'
                left join embedding_metadata fp on fp.id = doc.id and fp.key = 'file_path'
                left join embedding_metadata loc on loc.id = doc.id and loc.key = 'location'
                left join embedding_metadata cat on cat.id = doc.id and cat.key = 'categories'
                left join embedding_metadata dt on dt.id = doc.id and dt.key = 'doc_type'
                left join embedding_metadata chunk on chunk.id = doc.id and chunk.key = 'chunk_id'
                where doc.key = 'chroma:document' and doc.string_value is not null
            """
        documents: list[ChromaDocument] = []
        for row in connection.execute(query):
            embedding_id, text, source, file_path, location, categories, doc_type, chunk_id, collection = row
            content = _normalize_space(text)
            if not content:
                continue
            source_type = _infer_source_type_from_metadata(
                categories,
                doc_type,
                collection,
                source,
                file_path,
                db_path.parent.name,
            )
            if wanted and source_type not in wanted:
                continue
            loc = _normalize_space(location) or _normalize_space(chunk_id) or f"embedding:{embedding_id}"
            source_name = _normalize_space(source) or _normalize_space(file_path) or db_path.parent.name
            documents.append(
                ChromaDocument(
                    db_path=db_path,
                    embedding_id=int(embedding_id),
                    source_type=source_type,
                    text=content,
                    source=source_name,
                    file_path=_normalize_space(file_path) or str(db_path),
                    location=loc,
                    collection=_normalize_space(collection),
                    categories=_normalize_space(categories),
                    doc_type=_normalize_space(doc_type),
                )
            )
        return documents
    except sqlite3.Error:
        return []
    finally:
        connection.close()


def _chroma_connection(db_path: Path) -> sqlite3.Connection | None:
    try:
        try:
            return sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
        except sqlite3.OperationalError:
            # SQLite URI read-only mode is not portable for Windows UNC paths.
            # This fallback still performs only SELECT statements.
            return sqlite3.connect(str(db_path))
    except sqlite3.Error:
        return None


def iter_chroma_documents(
    *,
    search_roots: Sequence[str | Path] | None = None,
    db_root_path: str | None = None,
    source_types: Sequence[str] | None = None,
) -> list[ChromaDocument]:
    if not _chroma_enabled():
        return []
    documents: list[ChromaDocument] = []
    for db_path in _chroma_db_paths(search_roots, db_root_path):
        documents.extend(_iter_chroma_db_documents(db_path, source_types=source_types))
    return documents


def _candidate_chroma_ids(
    connection: sqlite3.Connection,
    tokens: Sequence[str],
    *,
    per_token_limit: int,
) -> list[int]:
    tables = _sqlite_tables(connection)
    ids: list[int] = []
    seen: set[int] = set()
    search_terms = [token for token in tokens if len(token) >= 2][:18]
    if not search_terms:
        return ids
    use_fts = "embedding_fulltext_search" in tables
    for token in search_terms:
        like = f"%{token}%"
        query = (
            "select rowid from embedding_fulltext_search where string_value like ? limit ?"
            if use_fts
            else "select id from embedding_metadata where key = 'chroma:document' and string_value like ? limit ?"
        )
        try:
            rows = connection.execute(query, (like, per_token_limit)).fetchall()
        except sqlite3.Error:
            continue
        for row in rows:
            try:
                embedding_id = int(row[0])
            except (TypeError, ValueError):
                continue
            if embedding_id in seen:
                continue
            seen.add(embedding_id)
            ids.append(embedding_id)
    return ids


def _chroma_documents_by_ids(
    connection: sqlite3.Connection,
    db_path: Path,
    embedding_ids: Sequence[int],
    *,
    source_types: Sequence[str] | None = None,
) -> list[ChromaDocument]:
    ids = [int(item) for item in embedding_ids if str(item).strip()]
    if not ids:
        return []
    wanted = set(normalize_source_types(source_types))
    placeholders = ",".join("?" for _ in ids)
    tables = _sqlite_tables(connection)
    has_embeddings = "embeddings" in tables
    has_segments = "segments" in tables
    has_collections = "collections" in tables
    collection_select = "coalesce(c.name, '') as collection" if has_embeddings and has_segments and has_collections else "'' as collection"
    collection_join = (
        """
        left join embeddings e on e.id = doc.id
        left join segments s on s.id = e.segment_id
        left join collections c on c.id = s.collection
        """
        if has_embeddings and has_segments and has_collections
        else ""
    )
    query = f"""
        select
            doc.id,
            doc.string_value as document,
            coalesce(src.string_value, '') as source,
            coalesce(fp.string_value, '') as file_path,
            coalesce(loc.string_value, '') as location,
            coalesce(cat.string_value, '') as categories,
            coalesce(dt.string_value, '') as doc_type,
            coalesce(chunk.string_value, '') as chunk_id,
            {collection_select}
        from embedding_metadata doc
        left join embedding_metadata src on src.id = doc.id and src.key = 'source'
        left join embedding_metadata fp on fp.id = doc.id and fp.key = 'file_path'
        left join embedding_metadata loc on loc.id = doc.id and loc.key = 'location'
        left join embedding_metadata cat on cat.id = doc.id and cat.key = 'categories'
        left join embedding_metadata dt on dt.id = doc.id and dt.key = 'doc_type'
        left join embedding_metadata chunk on chunk.id = doc.id and chunk.key = 'chunk_id'
        {collection_join}
        where doc.key = 'chroma:document' and doc.id in ({placeholders})
    """
    documents: list[ChromaDocument] = []
    try:
        rows = connection.execute(query, ids).fetchall()
    except sqlite3.Error:
        return documents
    for row in rows:
        embedding_id, text, source, file_path, location, categories, doc_type, chunk_id, collection = row
        content = _normalize_space(text)
        if not content:
            continue
        source_type = _infer_source_type_from_metadata(
            categories,
            doc_type,
            collection,
            source,
            file_path,
            db_path.parent.name,
        )
        if wanted and source_type not in wanted:
            continue
        loc = _normalize_space(location) or _normalize_space(chunk_id) or f"embedding:{embedding_id}"
        source_name = _normalize_space(source) or _normalize_space(file_path) or db_path.parent.name
        documents.append(
            ChromaDocument(
                db_path=db_path,
                embedding_id=int(embedding_id),
                source_type=source_type,
                text=content,
                source=source_name,
                file_path=_normalize_space(file_path) or str(db_path),
                location=loc,
                collection=_normalize_space(collection),
                categories=_normalize_space(categories),
                doc_type=_normalize_space(doc_type),
            )
        )
    return documents


def _chroma_vectors_by_ids(connection: sqlite3.Connection, embedding_ids: Sequence[int]) -> dict[int, list[float]]:
    tables = _sqlite_tables(connection)
    if "embeddings" not in tables or "embeddings_queue" not in tables:
        return {}
    ids = [int(item) for item in embedding_ids if str(item).strip()]
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    query = f"""
        select e.id, q.vector
        from embeddings e
        join embeddings_queue q on q.id = e.embedding_id
        where e.id in ({placeholders}) and q.vector is not null
    """
    vectors: dict[int, list[float]] = {}
    try:
        rows = connection.execute(query, ids).fetchall()
    except sqlite3.Error:
        return vectors
    for embedding_id, blob in rows:
        vector = decode_float32_vector(blob)
        if vector:
            vectors[int(embedding_id)] = vector
    return vectors


def _queue_vector_documents(
    connection: sqlite3.Connection,
    db_path: Path,
    query_vector: Sequence[float],
    *,
    source_types: Sequence[str] | None = None,
    max_rows: int = 5000,
) -> list[tuple[float, ChromaDocument]]:
    tables = _sqlite_tables(connection)
    if "embeddings_queue" not in tables or not query_vector:
        return []
    wanted = set(normalize_source_types(source_types))
    scored: list[tuple[float, ChromaDocument]] = []
    try:
        rows = connection.execute(
            """
            select seq_id, vector, metadata
            from embeddings_queue
            where vector is not null and metadata is not null
            limit ?
            """,
            (max_rows,),
        ).fetchall()
    except sqlite3.Error:
        return scored
    for seq_id, blob, metadata_raw in rows:
        vector = decode_float32_vector(blob)
        if len(vector) != len(query_vector):
            continue
        vector_score = cosine_similarity(query_vector, vector)
        if vector_score is None:
            continue
        try:
            metadata = json.loads(metadata_raw) if isinstance(metadata_raw, str) else {}
        except json.JSONDecodeError:
            metadata = {}
        text = _normalize_space(metadata.get("chroma:document") or metadata.get("caption") or metadata.get("document"))
        if not text:
            continue
        source = _normalize_space(metadata.get("source") or db_path.parent.name)
        file_path = _normalize_space(metadata.get("file_path") or source or str(db_path))
        location = _normalize_space(metadata.get("location") or f"queue:{seq_id}")
        categories = _normalize_space(metadata.get("categories"))
        doc_type = _normalize_space(metadata.get("doc_type"))
        source_type = _infer_source_type_from_metadata(
            categories,
            doc_type,
            source,
            file_path,
            db_path.parent.name,
        )
        if wanted and source_type not in wanted:
            continue
        scored.append(
            (
                float(vector_score),
                ChromaDocument(
                    db_path=db_path,
                    embedding_id=int(seq_id),
                    source_type=source_type,
                    text=text,
                    source=source,
                    file_path=file_path,
                    location=location,
                    collection=_normalize_space(metadata.get("collection")),
                    categories=categories,
                    doc_type=doc_type,
                ),
            )
        )
    return scored


def search_chroma_documents(
    query: str,
    top_k: int = 5,
    *,
    source_types: Sequence[str] | None = None,
    search_roots: Sequence[str | Path] | None = None,
    db_root_path: str | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
    query_tokens: Sequence[str] | None = None,
    use_vector: bool = True,
    vector_only: bool = False,
) -> list[dict[str, Any]]:
    if not _chroma_enabled():
        return []
    q = _normalize_space(query)
    if not q:
        return []
    tokens = list(query_tokens or _expanded_tokens(q))
    db_paths = _chroma_db_paths(search_roots, db_root_path)
    if not db_paths:
        return []
    query_embedding = (
        embed_query(q)
        if use_vector
        else {"ok": False, "reason": "vector_disabled_for_fast_route", "vector": []}
    )
    query_vector = query_embedding.get("vector") if isinstance(query_embedding, Mapping) and query_embedding.get("ok") else []
    if vector_only and not query_vector:
        return []
    scored: list[tuple[float, ChromaDocument, dict[str, Any]]] = []
    limit = max(1, int(top_k or 5))
    per_token_limit = max(20, min(120, limit * 20))
    for db_path in db_paths:
        connection = _chroma_connection(db_path)
        if connection is None:
            continue
        try:
            if not vector_only:
                ids = _candidate_chroma_ids(connection, tokens, per_token_limit=per_token_limit)
                documents = _chroma_documents_by_ids(connection, db_path, ids, source_types=source_types)
                vectors = _chroma_vectors_by_ids(connection, [document.embedding_id for document in documents]) if query_vector else {}
                for document in documents:
                    keyword_score = _score(tokens, document.text, document.source_type)
                    vector_score = cosine_similarity(query_vector, vectors.get(document.embedding_id, [])) if query_vector else None
                    if keyword_score <= 0 and vector_score is None:
                        continue
                    source_bonus = {
                        SOURCE_TYPE_SOP: 0.04,
                        SOURCE_TYPE_NXI: 0.04,
                        SOURCE_TYPE_SIMILAR_REPORT: 0.03,
                        SOURCE_TYPE_PRODUCT_INFORMATION: 0.02,
                        SOURCE_TYPE_THEORY: 0.01,
                    }.get(document.source_type, 0.0)
                    if vector_score is not None:
                        score = 1.0 + max(0.0, vector_score) * 0.5 + min(keyword_score, 1.0) * 0.2 + source_bonus
                        retrieval_mode = "chroma_vector_e5_hybrid"
                        score_detail = {
                            "vector_score": round(vector_score, 4),
                            "keyword_score": round(keyword_score, 4),
                            "embedding_backend": query_embedding.get("backend", ""),
                            "embedding_model": query_embedding.get("model", ""),
                        }
                    else:
                        score = keyword_score
                        retrieval_mode = "chroma_sqlite_metadata"
                        score_detail = {
                            "keyword_score": round(keyword_score, 4),
                            "embedding_status": query_embedding.get("reason", "not_requested") if isinstance(query_embedding, Mapping) else "not_requested",
                        }
                    trimmed = document
                    if len(trimmed.text) > max_chars:
                        trimmed = ChromaDocument(
                            db_path=trimmed.db_path,
                            embedding_id=trimmed.embedding_id,
                            source_type=trimmed.source_type,
                            text=trimmed.text[:max_chars].rstrip(),
                            source=trimmed.source,
                            file_path=trimmed.file_path,
                            location=trimmed.location,
                            collection=trimmed.collection,
                            categories=trimmed.categories,
                            doc_type=trimmed.doc_type,
                        )
                    scored.append((score, trimmed, {"retrieval_mode": retrieval_mode, **score_detail}))
            if query_vector:
                for vector_score, document in _queue_vector_documents(
                    connection,
                    db_path,
                    query_vector,
                    source_types=source_types,
                ):
                    keyword_score = _score(tokens, document.text, document.source_type)
                    source_bonus = {
                        SOURCE_TYPE_SOP: 0.04,
                        SOURCE_TYPE_NXI: 0.04,
                        SOURCE_TYPE_SIMILAR_REPORT: 0.03,
                        SOURCE_TYPE_PRODUCT_INFORMATION: 0.02,
                        SOURCE_TYPE_THEORY: 0.01,
                    }.get(document.source_type, 0.0)
                    score = (
                        1.0 + max(0.0, vector_score) * 0.5 + source_bonus
                        if vector_only
                        else 1.0 + max(0.0, vector_score) * 0.5 + min(keyword_score, 1.0) * 0.2
                    )
                    trimmed = document
                    if len(trimmed.text) > max_chars:
                        trimmed = ChromaDocument(
                            db_path=trimmed.db_path,
                            embedding_id=trimmed.embedding_id,
                            source_type=trimmed.source_type,
                            text=trimmed.text[:max_chars].rstrip(),
                            source=trimmed.source,
                            file_path=trimmed.file_path,
                            location=trimmed.location,
                            collection=trimmed.collection,
                            categories=trimmed.categories,
                            doc_type=trimmed.doc_type,
                        )
                    scored.append(
                        (
                            score,
                            trimmed,
                            {
                                "retrieval_mode": "chroma_vector_e5" if vector_only else "chroma_vector_e5_hybrid",
                                "vector_score": round(vector_score, 4),
                                "embedding_backend": query_embedding.get("backend", ""),
                                "embedding_model": query_embedding.get("model", ""),
                                **({} if vector_only else {"keyword_score": round(keyword_score, 4)}),
                            },
                        )
                    )
        finally:
            connection.close()
    deduped: list[tuple[float, ChromaDocument, dict[str, Any]]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for score, document, extra in scored:
        key = (document.source_type, document.source, document.location, document.text[:120])
        if key in seen:
            continue
        seen.add(key)
        deduped.append((score, document, extra))
    deduped.sort(key=lambda row: (-row[0], row[1].source_type, row[1].source, row[1].location))
    return [
        _chroma_hit_record(document, score=score, rank=index, extra=extra)
        for index, (score, document, extra) in enumerate(deduped[:limit], start=1)
    ]



def _tokens(text: str) -> list[str]:
    normalized = _normalize_space(text).lower()
    raw_tokens = re.findall(r"[a-z0-9_+\-.]{2,}|[가-힣]{2,}", normalized)
    out: list[str] = []
    seen: set[str] = set()
    for token in raw_tokens:
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


SYNONYM_GROUPS = (
    ("압력", "손실", "압력손실", "pressure", "pa", "유량", "풍량"),
    ("이슬", "결로", "condensation", "dew", "습도", "rh"),
    ("유동", "풍속", "토출", "흡입", "flow", "air", "velocity"),
    ("열", "온도", "냉각", "thermal", "heat", "temp"),
    ("소음", "진동", "noise", "vibration", "hz"),
    ("구조", "응력", "변형", "structure", "stress"),
    ("필터", "그릴", "팬", "fan", "rpm", "filter", "grille"),
)


def _expanded_tokens(text: str) -> list[str]:
    tokens = _tokens(text)
    lowered = " ".join(tokens).lower()
    out = list(tokens)
    seen = set(out)
    for group in SYNONYM_GROUPS:
        if any(item.lower() in lowered for item in group):
            for item in group:
                token = item.lower()
                if token not in seen:
                    seen.add(token)
                    out.append(token)
    return out


def _chunks(text: str, *, max_chars: int) -> list[tuple[str, str]]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if _normalize_space(part)]
    if not paragraphs:
        paragraphs = [line.strip() for line in text.splitlines() if _normalize_space(line)]
    chunks: list[tuple[str, str]] = []
    for index, paragraph in enumerate(paragraphs, start=1):
        normalized = _normalize_space(paragraph)
        if not normalized:
            continue
        while len(normalized) > max_chars:
            chunks.append((f"chunk:{index}", normalized[:max_chars].rstrip()))
            normalized = normalized[max_chars:].lstrip()
        chunks.append((f"chunk:{index}", normalized))
    return chunks


def _score(query_tokens: Sequence[str], text: str, source_type: str) -> float:
    if not query_tokens:
        return 0.0
    lowered = text.lower()
    hits = sum(1 for token in query_tokens if token.lower() in lowered)
    if hits <= 0:
        return 0.0
    source_bonus = {
        SOURCE_TYPE_SOP: 0.18,
        SOURCE_TYPE_NXI: 0.16,
        SOURCE_TYPE_SIMILAR_REPORT: 0.10,
        SOURCE_TYPE_PRODUCT_INFORMATION: 0.08,
        SOURCE_TYPE_THEORY: 0.05,
    }.get(source_type, 0.0)
    return (hits / max(len(query_tokens), 1)) + source_bonus


def _hit_record(document: SearchDocument, *, location: str, content: str, score: float, rank: int) -> dict[str, Any]:
    return {
        "rank": rank,
        "score": round(score, 4),
        "source_type": document.source_type,
        "source_type_label": SOURCE_TYPE_LABELS.get(document.source_type, document.source_type),
        "source": document.path.name,
        "file_path": str(document.path),
        "location": location,
        "content": content,
        "modality": "text",
        "read_only": True,
        "retrieval_mode": "file_keyword",
    }


def _chroma_hit_record(
    document: ChromaDocument,
    *,
    score: float,
    rank: int,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "rank": rank,
        "score": round(score, 4),
        "source_type": document.source_type,
        "source_type_label": SOURCE_TYPE_LABELS.get(document.source_type, document.source_type),
        "source": document.source,
        "file_path": document.file_path,
        "location": document.location,
        "content": document.text[:DEFAULT_MAX_CHARS].rstrip(),
        "modality": "text",
        "read_only": True,
        "retrieval_mode": "chroma_sqlite_metadata",
        "vector_store": str(document.db_path),
        "collection": document.collection,
        "categories": document.categories,
        "doc_type": document.doc_type,
    }
    if isinstance(extra, Mapping):
        payload.update({key: value for key, value in extra.items() if value not in ("", None, [])})
    return payload


def search_rag_documents(
    query: str,
    top_k: int = 5,
    *,
    source_types: Sequence[str] | None = None,
    search_roots: Sequence[str | Path] | None = None,
    db_root_path: str | None = None,
    modality: str = "text",
    runtime: Any = None,
    retrieval_config: Mapping[str, Any] | None = None,
    device: str | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
    use_vector: bool = True,
    vector_only: bool = False,
    product_terms: Sequence[str] | None = None,
    analysis_type_terms: Sequence[str] | None = None,
    **_: Any,
) -> list[dict[str, Any]]:
    """Return read-only text hits.

    The signature accepts report-agent-like options, but this implementation
    intentionally does not mutate runtime, vectorstores, files, or state.
    """

    _ = runtime, retrieval_config, device
    if _normalize_space(modality).lower() not in {"", "text", "both"}:
        return []
    q = _normalize_space(query)
    if not q:
        return []
    query_tokens = _expanded_tokens(q)
    scored: list[tuple[float, str, SearchDocument, str, str]] = []
    for document in iter_search_documents(search_roots=search_roots, db_root_path=db_root_path, source_types=source_types):
        for location, chunk in _chunks(document.text, max_chars=max_chars):
            score = _score(query_tokens, chunk, document.source_type)
            if score <= 0:
                continue
            scored.append((score, "file", document, location, chunk))
    scored.sort(
        key=lambda row: (
            -row[0],
            row[2].source_type,
            str(row[2].path),
            row[3],
        )
    )
    limit = max(1, int(top_k or 5))
    file_hits = [
        _hit_record(document, location=location, content=content, score=score, rank=index)
        for index, (score, _mode, document, location, content) in enumerate(scored[:limit], start=1)
    ]
    chroma_hits = search_chroma_documents(
        q,
        top_k=limit,
        source_types=source_types,
        search_roots=search_roots,
        db_root_path=db_root_path,
        max_chars=max_chars,
        query_tokens=query_tokens,
        use_vector=use_vector,
        vector_only=vector_only,
    )
    merged = chroma_hits + file_hits
    products = [item.lower() for item in (product_terms or []) if _normalize_space(item)]
    analysis_terms = [item.lower() for item in (analysis_type_terms or []) if _normalize_space(item)]
    if products or analysis_terms:
        boosted = []
        for hit in merged:
            haystack = f"{hit.get('source', '')} {hit.get('file_path', '')} {hit.get('content', '')}".lower()
            product_matches = sum(1 for term in products if term in haystack)
            analysis_matches = sum(1 for term in analysis_terms if term in haystack)
            boost = product_matches * 0.30 + analysis_matches * 0.10
            boosted.append({**hit, "score": float(hit.get("score", 0) or 0) + boost, "ranking_policy": "product_first" if boost else hit.get("ranking_policy", "")})
        merged = boosted
    merged.sort(
        key=lambda hit: (
            -float(hit.get("score", 0) or 0),
            0
            if str(hit.get("retrieval_mode", "")).startswith("chroma_vector_e5")
            else 1
            if hit.get("retrieval_mode") == "chroma_sqlite_metadata"
            else 2,
            _normalize_space(hit.get("source_type")),
            _normalize_space(hit.get("source")),
            _normalize_space(hit.get("location")),
        )
    )
    return [{**hit, "rank": index} for index, hit in enumerate(merged[:limit], start=1)]


def render_hits_as_context(hits: Sequence[Mapping[str, Any]], *, max_items: int = 6) -> str:
    lines: list[str] = []
    for hit in hits[:max_items]:
        source_type = _normalize_space(hit.get("source_type_label")) or _normalize_space(hit.get("source_type"))
        source = _normalize_space(hit.get("source"))
        location = _normalize_space(hit.get("location"))
        content = _normalize_space(hit.get("content"))
        if not content:
            continue
        lines.append(f"[{source_type}] {source} {location}: {content}")
    return "\n".join(lines)
