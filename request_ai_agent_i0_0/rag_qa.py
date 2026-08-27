"""Read-only RAG Q&A for the request assistant."""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from .constants import (
    SECTION_ANALYSIS_OVERVIEW,
    SECTION_BASIC_INFO,
    SECTION_CASE_MATRIX,
    SECTION_CONDITIONS,
    SECTION_GEOMETRY,
)
from .rag_search import (
    SOURCE_TYPE_NXI,
    SOURCE_TYPE_PRODUCT_INFORMATION,
    SOURCE_TYPE_SIMILAR_REPORT,
    SOURCE_TYPE_SOP,
    SOURCE_TYPE_THEORY,
    normalize_source_types,
    render_hits_as_context,
    search_rag_documents,
)
from .state import field_value, sanitize_state
from .llm_client import llm_status, rerank_rag_hits


QUESTION_TYPE_POLICY = "policy"
QUESTION_TYPE_SIMILAR_REPORT = "similar_report"
QUESTION_TYPE_CURRENT_INPUT = "current_input"
QUESTION_TYPE_COUNT = "count"
QUESTION_TYPE_GENERAL = "general"


def _clean(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def _line(value: Any) -> str:
    return " ".join(_clean(value).split())


def _contains_any(text: str, tokens: Iterable[str]) -> bool:
    lowered = _line(text).lower()
    return any(token.lower() in lowered for token in tokens)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def looks_like_current_input_question(question: str) -> bool:
    return _contains_any(
        question,
        (
            "현재 입력",
            "현재 상태",
            "입력 상태",
            "입력 요약",
            "지금까지 입력",
            "내가 쓴 내용",
            "state summary",
            "current input",
            "what did i enter",
        ),
    )


def classify_question(question: str) -> str:
    if looks_like_current_input_question(question):
        return QUESTION_TYPE_CURRENT_INPUT
    if _contains_any(question, ("몇 건", "몇개", "개수", "건수", "총 몇", "count", "how many")):
        return QUESTION_TYPE_COUNT
    if _contains_any(question, ("npi", "nxi", "sop", "규정", "기준", "절차", "표준", "필수", "의무", "required")):
        return QUESTION_TYPE_POLICY
    if _contains_any(question, ("유사 보고서", "유사보고서", "유사사례", "비슷한 사례", "similar report", "similar case")):
        return QUESTION_TYPE_SIMILAR_REPORT
    return QUESTION_TYPE_GENERAL


def infer_source_types(question: str, *, question_type: str | None = None) -> list[str]:
    qtype = question_type or classify_question(question)
    if qtype == QUESTION_TYPE_CURRENT_INPUT:
        return ["current_input_state"]
    if qtype == QUESTION_TYPE_POLICY:
        return [
            SOURCE_TYPE_SOP,
            SOURCE_TYPE_NXI,
            SOURCE_TYPE_PRODUCT_INFORMATION,
            SOURCE_TYPE_THEORY,
            SOURCE_TYPE_SIMILAR_REPORT,
        ]
    if qtype == QUESTION_TYPE_SIMILAR_REPORT:
        return [SOURCE_TYPE_SIMILAR_REPORT, SOURCE_TYPE_SOP, SOURCE_TYPE_NXI, SOURCE_TYPE_THEORY]
    if qtype == QUESTION_TYPE_COUNT:
        return [SOURCE_TYPE_SIMILAR_REPORT, SOURCE_TYPE_SOP, SOURCE_TYPE_NXI, SOURCE_TYPE_THEORY]
    return [
        SOURCE_TYPE_SOP,
        SOURCE_TYPE_NXI,
        SOURCE_TYPE_SIMILAR_REPORT,
        SOURCE_TYPE_THEORY,
        SOURCE_TYPE_PRODUCT_INFORMATION,
    ]


def _provided_row_values(rows: Any) -> list[str]:
    values: list[str] = []
    for row in _as_list(rows):
        if isinstance(row, Mapping):
            value = field_value(row, "")
        else:
            value = row
        text = _line(value)
        if text:
            values.append(text)
    return values


def summarize_current_state(state: Mapping[str, Any] | None) -> dict[str, Any]:
    safe = sanitize_state(state if isinstance(state, Mapping) else {})
    basic = _as_mapping(safe.get(SECTION_BASIC_INFO))
    overview = _as_mapping(safe.get(SECTION_ANALYSIS_OVERVIEW))
    geometry = _as_mapping(safe.get(SECTION_GEOMETRY))
    conditions = _as_mapping(safe.get(SECTION_CONDITIONS))
    case_matrix = _as_mapping(safe.get(SECTION_CASE_MATRIX))
    review = _as_mapping(safe.get("review"))
    validator = _as_mapping(review.get("validator"))
    summary = _as_mapping(validator.get("summary"))

    condition_items: list[dict[str, Any]] = []
    for field in _as_list(conditions.get("fields")):
        if not isinstance(field, Mapping):
            continue
        values = _provided_row_values(field.get("values"))
        if not values:
            continue
        condition_items.append(
            {
                "field_key": _line(field.get("key")),
                "field_label": _line(field.get("label")) or _line(field.get("key")),
                "values": values,
            }
        )

    complete_products = [geometry.get("base_product"), *_as_list(geometry.get("comparison_products"))]
    return {
        "basic_info": {
            "division": field_value(basic.get("division"), ""),
            "requester_name": field_value(basic.get("requester_name"), ""),
        },
        "analysis_overview": {
            "analysis_type": field_value(overview.get("analysis_type"), ""),
            "request_date": field_value(overview.get("request_date"), ""),
            "due_date": field_value(overview.get("due_date"), ""),
            "purpose": field_value(overview.get("purpose"), ""),
            "goal": field_value(overview.get("goal"), ""),
            "project_name": field_value(overview.get("project_name"), ""),
        },
        "geometry": {
            "products": _provided_row_values(
                [product.get("drawing_no")
                for product in complete_products
                if isinstance(product, Mapping)]
            ),
            "has_changed_part": field_value(geometry.get("has_changed_part"), ""),
            "changed_from_part": field_value(geometry.get("changed_from_part"), ""),
            "parts": _provided_row_values(geometry.get("parts")),
        },
        "conditions": condition_items,
        "case_matrix": {
            "case_count": len(_as_list(case_matrix.get("rows"))),
        },
        "validation": {
            "can_submit": summary.get("can_submit", False),
            "blocking_count": summary.get("blocking_count", 0),
            "warning_count": summary.get("warning_count", 0),
        },
    }


def _state_summary_text(state_summary: Mapping[str, Any]) -> str:
    basic = _as_mapping(state_summary.get("basic_info"))
    overview = _as_mapping(state_summary.get("analysis_overview"))
    geometry = _as_mapping(state_summary.get("geometry"))
    case_matrix = _as_mapping(state_summary.get("case_matrix"))
    validation = _as_mapping(state_summary.get("validation"))
    conditions = _as_list(state_summary.get("conditions"))
    condition_text = ", ".join(
        f"{item.get('field_label')}: {'/'.join(item.get('values', []))}"
        for item in conditions
        if isinstance(item, Mapping)
    ) or "-"
    products = ", ".join(geometry.get("products", []) or []) or "-"
    parts = ", ".join(geometry.get("parts", []) or []) or "-"
    return (
        "현재 입력 상태 질문으로 분류하여 문서 RAG 대신 structured state를 요약했습니다.\n"
        f"- 사업부/요청자: {basic.get('division') or '-'} / {basic.get('requester_name') or '-'}\n"
        f"- 해석 유형: {overview.get('analysis_type') or '-'}\n"
        f"- 목적: {overview.get('purpose') or '-'}\n"
        f"- 목표: {overview.get('goal') or '-'}\n"
        f"- 제품: {products}\n"
        f"- 변경 부품: {parts}\n"
        f"- 조건: {condition_text}\n"
        f"- Case: {case_matrix.get('case_count', 0)}건\n"
        f"- 검증: blocking {validation.get('blocking_count', 0)}, warning {validation.get('warning_count', 0)}, can_submit={validation.get('can_submit', False)}"
    )


def _context_query(question: str, state: Mapping[str, Any] | None) -> str:
    if not isinstance(state, Mapping):
        return _line(question)
    summary = summarize_current_state(state)
    overview = _as_mapping(summary.get("analysis_overview"))
    geometry = _as_mapping(summary.get("geometry"))
    conditions = _as_list(summary.get("conditions"))
    condition_bits = []
    for item in conditions[:5]:
        if isinstance(item, Mapping):
            condition_bits.append(f"{item.get('field_label')}: {'/'.join(item.get('values', []))}")
    parts = [
        f"question: {question}",
        f"analysis_type: {overview.get('analysis_type', '')}",
        f"purpose: {overview.get('purpose', '')}",
        f"goal: {overview.get('goal', '')}",
        f"products: {', '.join(geometry.get('products', []) or [])}",
        f"conditions: {' | '.join(condition_bits)}",
    ]
    return " | ".join(part for part in [_line(item) for item in parts] if part and not part.endswith(":"))


def _source_record(hit: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_type": _line(hit.get("source_type")),
        "source_type_label": _line(hit.get("source_type_label")),
        "source_name": _line(hit.get("source")),
        "source_path": _line(hit.get("file_path")),
        "source_location": _line(hit.get("location")),
        "source_snippet": _line(hit.get("content")),
        "score": hit.get("score", 0),
        "retrieval_mode": _line(hit.get("retrieval_mode")),
        "why_this_matters": "RAG Q&A evidence only. It must not auto-change request state.",
    }


def _dedupe_sources(hits: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for hit in hits:
        if not isinstance(hit, Mapping):
            continue
        row = _source_record(hit)
        key = "|".join(
            [
                row["source_type"],
                row["source_path"],
                row["source_location"],
                row["source_snippet"][:160],
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _confidence(question_type: str, sources: Sequence[Mapping[str, Any]]) -> tuple[str, list[str]]:
    if not sources:
        return "low", ["검색 결과가 없어 근거 기반 답변이 제한됩니다."]
    source_types = {_line(item.get("source_type")) for item in sources}
    limits = ["RAG 검색 결과는 일부 문서 스니펫일 수 있으므로 원문 확인이 필요합니다."]
    if question_type == QUESTION_TYPE_POLICY:
        if SOURCE_TYPE_SOP in source_types and SOURCE_TYPE_NXI in source_types:
            return "high", limits
        if SOURCE_TYPE_SOP in source_types or SOURCE_TYPE_NXI in source_types:
            return "medium", ["SOP/NXI 중 일부만 검색되어 최종 규정 판단은 원문 확인이 필요합니다."]
        return "low", ["규정성 질문이지만 SOP/NXI 근거가 부족합니다."]
    return ("medium" if len(sources) >= 2 else "low"), limits


def _answer_from_sources(sources: Sequence[Mapping[str, Any]], *, question_type: str) -> str:
    if not sources:
        return "직접 근거를 찾지 못했습니다. 질문을 더 구체화하거나 source_type/top_k를 조정해 주세요."
    ordered = list(sources)
    if question_type == QUESTION_TYPE_POLICY:
        rank = {SOURCE_TYPE_SOP: 0, SOURCE_TYPE_NXI: 1, SOURCE_TYPE_PRODUCT_INFORMATION: 2, SOURCE_TYPE_THEORY: 3, SOURCE_TYPE_SIMILAR_REPORT: 4}
        ordered.sort(key=lambda item: rank.get(_line(item.get("source_type")), 9))
        header = "규정성 질문 답변(SOP/NXI 우선 근거):"
    elif question_type == QUESTION_TYPE_SIMILAR_REPORT:
        header = "유사보고서/참고사례 기반 답변:"
    else:
        header = "검색 근거 기반 답변:"
    bullets = []
    for item in ordered[:4]:
        source_type = _line(item.get("source_type_label")) or _line(item.get("source_type"))
        source_name = _line(item.get("source_name"))
        snippet = _line(item.get("source_snippet"))
        if snippet:
            bullets.append(f"- [{source_type}] {source_name}: {snippet}")
    return header + ("\n" + "\n".join(bullets) if bullets else "\n- 검색 hit은 있으나 사용 가능한 스니펫이 부족합니다.")


def _format_answer(
    core: str,
    *,
    question_type: str,
    query: str,
    source_types: Sequence[str],
    confidence: str,
    limitations: Sequence[str],
) -> str:
    source_line = ", ".join(source_types) or "-"
    limit_lines = "\n".join(f"- {item}" for item in limitations) or "- 없음"
    return (
        f"[질문 분류] {question_type}\n"
        f"[검색 source_type] {source_line}\n"
        f"[실행 query] {query}\n"
        f"[신뢰도] {confidence}\n"
        "[한계]\n"
        f"{limit_lines}\n\n"
        f"{core}\n\n"
        "안내: RAG Q&A는 읽기 전용이며 입력 state를 자동 변경하지 않습니다."
    )


def run_rag_qa(
    question: str,
    *,
    state: Mapping[str, Any] | None = None,
    top_k: int = 5,
    source_types: Sequence[str] | None = None,
    search_roots: Sequence[str] | None = None,
    db_root_path: str | None = None,
    modality: str = "text",
    **search_options: Any,
) -> dict[str, Any]:
    """Answer a question using read-only document search or state summary."""

    q = _line(question)
    if not q:
        return {
            "ok": False,
            "question": "",
            "question_type": QUESTION_TYPE_GENERAL,
            "query": "",
            "sources": [],
            "hit_count": 0,
            "source_types_searched": [],
            "confidence": "low",
            "limitations": ["질문이 비어 있습니다."],
            "answer_text": "질문이 비어 있습니다.",
            "read_only": True,
            "state_changed": False,
        }

    question_type = classify_question(q)
    resolved_source_types = list(source_types or infer_source_types(q, question_type=question_type))
    if question_type == QUESTION_TYPE_CURRENT_INPUT:
        state_summary = summarize_current_state(state)
        query = _context_query(q, state)
        limitations = ["문서 RAG 검색을 수행하지 않았습니다. 현재 structured state만 요약했습니다."]
        return {
            "ok": True,
            "question": q,
            "question_type": question_type,
            "query": query,
            "sources": [],
            "hit_count": 0,
            "source_types_searched": resolved_source_types,
            "state_summary": state_summary,
            "confidence": "high",
            "limitations": limitations,
            "answer_text": _format_answer(
                _state_summary_text(state_summary),
                question_type=question_type,
                query=query,
                source_types=resolved_source_types,
                confidence="high",
                limitations=limitations,
            ),
            "read_only": True,
            "state_changed": False,
        }

    normalized_source_types = normalize_source_types(resolved_source_types)
    query = _context_query(q, state)
    state_summary = summarize_current_state(state)
    geometry_summary = _as_mapping(state_summary.get("geometry"))
    overview_summary = _as_mapping(state_summary.get("analysis_overview"))
    hits = search_rag_documents(
        query=query,
        top_k=top_k,
        source_types=normalized_source_types,
        search_roots=search_roots,
        db_root_path=db_root_path,
        modality=modality,
        product_terms=geometry_summary.get("products", []) if isinstance(geometry_summary.get("products"), list) else [],
        analysis_type_terms=[_line(overview_summary.get("analysis_type"))],
        **search_options,
    )
    reranker: dict[str, Any] = {"used": False}
    if llm_status().get("ready"):
        try:
            reranker = rerank_rag_hits(q, hits)
            reranked_hits = reranker.get("hits")
            if isinstance(reranked_hits, list):
                hits = reranked_hits
        except Exception as exc:  # pragma: no cover - network/config dependent
            reranker = {"used": False, "error": str(exc)}
    sources = _dedupe_sources(hits)
    confidence, limitations = _confidence(question_type, sources)
    core = _answer_from_sources(sources, question_type=question_type)
    return {
        "ok": True,
        "question": q,
        "question_type": question_type,
        "query": query,
        "sources": sources,
        "hit_count": len(sources),
        "context_text": render_hits_as_context(hits),
        "reranker": reranker,
        "source_types_searched": normalized_source_types,
        "confidence": confidence,
        "limitations": limitations,
        "answer_text": _format_answer(
            core,
            question_type=question_type,
            query=query,
            source_types=normalized_source_types,
            confidence=confidence,
            limitations=limitations,
        ),
        "read_only": True,
        "state_changed": False,
    }
