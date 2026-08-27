"""Optional Azure OpenAI integration helpers."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .config import env_flag, load_local_env


DEFAULT_AZURE_API_VERSION = "2024-10-21"


def _clean(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def _secret_present(*names: str) -> tuple[str, bool]:
    for name in names:
        if _clean(os.getenv(name)):
            return name, True
    return names[0], False


def _env_first(*names: str) -> str:
    for name in names:
        value = _clean(os.getenv(name))
        if value:
            return value
    return ""


@dataclass(frozen=True)
class AzureOpenAISettings:
    enabled: bool
    endpoint: str
    deployment: str
    api_version: str
    api_key_env: str
    api_key_present: bool

    @property
    def missing(self) -> list[str]:
        missing: list[str] = []
        if not self.endpoint:
            missing.append("AZURE_OPENAI_ENDPOINT")
        if not self.deployment:
            missing.append("AZURE_OPENAI_CHAT_DEPLOYMENT or AZURE_OPENAI_DEPLOYMENT")
        if not self.api_key_present:
            missing.append(self.api_key_env)
        return missing

    @property
    def configured(self) -> bool:
        return not self.missing


def azure_openai_settings() -> AzureOpenAISettings:
    load_local_env()
    api_key_env, api_key_present = _secret_present("AZURE_OPENAI_API_KEY", "ASURE_API_KEY", "AZURE_API_KEY")
    endpoint = _env_first("AZURE_OPENAI_ENDPOINT", "ASURE_ENDPOINT")
    deployment = _env_first(
        "AZURE_OPENAI_CHAT_DEPLOYMENT",
        "AZURE_OPENAI_DEPLOYMENT",
        "AZURE_DEPLOYMENT_NAME",
        "ASURE_DEPLOYMENT",
    )
    return AzureOpenAISettings(
        enabled=env_flag("REQUEST_AGENT_LLM_ENABLED", default=bool(endpoint and deployment and api_key_present)),
        endpoint=endpoint,
        deployment=deployment,
        api_version=_env_first("AZURE_OPENAI_API_VERSION", "ASURE_API_VERSION") or DEFAULT_AZURE_API_VERSION,
        api_key_env=api_key_env,
        api_key_present=api_key_present,
    )


def llm_status() -> dict[str, Any]:
    settings = azure_openai_settings()
    return {
        "provider": "azure_openai",
        "enabled": settings.enabled,
        "configured": settings.configured,
        "ready": settings.enabled and settings.configured,
        "endpoint_configured": bool(settings.endpoint),
        "deployment": settings.deployment,
        "api_version": settings.api_version,
        "api_key_env": settings.api_key_env,
        "api_key_present": settings.api_key_present,
        "missing": settings.missing,
    }


def azure_chat_completion(
    messages: Sequence[Mapping[str, str]],
    *,
    temperature: float | None = None,
    max_tokens: int = 700,
    timeout: int = 30,
) -> dict[str, Any]:
    settings = azure_openai_settings()
    if not settings.enabled:
        raise RuntimeError("REQUEST_AGENT_LLM_ENABLED is not enabled.")
    if not settings.configured:
        raise RuntimeError(f"Azure OpenAI is not configured: {', '.join(settings.missing)}")
    api_key = _env_first(settings.api_key_env)
    endpoint = settings.endpoint.rstrip("/")
    deployment = quote(settings.deployment, safe="")
    url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={settings.api_version}"
    body = {
        "messages": [dict(item) for item in messages],
        "max_completion_tokens": max_tokens,
    }
    if temperature is not None:
        body["temperature"] = temperature
    request = Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "api-key": api_key},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code == 400 and "max_completion_tokens" in detail:
            fallback_body = {key: value for key, value in body.items() if key != "max_completion_tokens"}
            fallback_body["max_tokens"] = max_tokens
            fallback_request = Request(
                url,
                data=json.dumps(fallback_body, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json", "api-key": api_key},
                method="POST",
            )
            try:
                with urlopen(fallback_request, timeout=timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except HTTPError as fallback_exc:
                fallback_detail = fallback_exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"Azure OpenAI HTTP {fallback_exc.code}: {fallback_detail[:500]}") from fallback_exc
            except URLError as fallback_exc:
                raise RuntimeError(f"Azure OpenAI request failed: {fallback_exc}") from fallback_exc
        else:
            raise RuntimeError(f"Azure OpenAI HTTP {exc.code}: {detail[:500]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Azure OpenAI request failed: {exc}") from exc
    choices = payload.get("choices") if isinstance(payload, Mapping) else []
    first = choices[0] if isinstance(choices, list) and choices else {}
    message = first.get("message") if isinstance(first, Mapping) else {}
    content = message.get("content") if isinstance(message, Mapping) else ""
    return {
        "content": _clean(content),
        "raw": payload,
        "deployment": settings.deployment,
        "api_version": settings.api_version,
    }


def _json_object_from_text(text: str) -> dict[str, Any]:
    clean = _clean(text)
    if not clean:
        return {}
    try:
        payload = json.loads(clean)
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", clean, flags=re.DOTALL)
    if not match:
        return {}
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def synthesize_rag_answer(question: str, qa_payload: Mapping[str, Any]) -> dict[str, Any]:
    context = _clean(qa_payload.get("context_text"))
    if not context:
        context = "\n".join(
            _clean(item.get("source_snippet"))
            for item in qa_payload.get("sources", [])
            if isinstance(item, Mapping)
        )
    if not context:
        context = "검색된 근거가 없습니다."
    messages = [
        {
            "role": "system",
            "content": (
                "너는 CAE 해석 의뢰 보조자다. 제공된 RAG 근거 안에서만 한국어로 답한다. "
                "근거가 부족하면 부족하다고 말하고, 입력 state를 변경하지 않는다."
            ),
        },
        {
            "role": "user",
            "content": f"질문:\n{question}\n\nRAG 근거:\n{context}\n\n간결한 답변과 필요한 주의사항을 작성해줘.",
        },
    ]
    result = azure_chat_completion(messages, max_tokens=700)
    return {
        "used": True,
        "provider": "azure_openai",
        "answer_text": result["content"],
        "deployment": result["deployment"],
        "api_version": result["api_version"],
    }


def synthesize_general_chat_answer(question: str, *, state_summary: Mapping[str, Any]) -> dict[str, Any]:
    """Answer service or general CAE questions without using RAG evidence or changing state."""

    messages = [
        {
            "role": "system",
            "content": (
                "너는 CAE 해석 의뢰 보조 agent다. 사용자의 질문에 한국어로 답하되 입력 state는 절대 변경하지 않는다. "
                "의뢰서에 반영할 값처럼 보이면 사용자가 명시한 값만 확인 대상으로 설명하고, 확정 반영은 별도 Yes/No 승인이 필요하다고 말한다. "
                "현재 의뢰 상태가 필요한 질문은 제공된 state 요약만 사용한다. "
                "사내 SOP, NXI, 특정 보고서 근거가 필요한 내용은 문서/RAG 근거 확인이 필요하다고 구분한다."
            ),
        },
        {
            "role": "user",
            "content": (
                f"질문:\n{question}\n\n"
                "현재 의뢰 state 요약:\n"
                f"{json.dumps(state_summary, ensure_ascii=False, indent=2)}\n\n"
                "답변은 간결하게 작성해줘."
            ),
        },
    ]
    result = azure_chat_completion(messages, max_tokens=700)
    return {
        "used": True,
        "provider": "azure_openai",
        "answer_text": result["content"],
        "deployment": result["deployment"],
        "api_version": result["api_version"],
    }


def extract_form_patch_with_llm(
    message: str,
    *,
    state_summary: Mapping[str, Any],
    schema: Mapping[str, Any],
) -> dict[str, Any]:
    """Classify a chat message and extract an optional patch with Azure GPT."""

    messages = [
        {
            "role": "system",
            "content": (
                "너는 CAE 해석 의뢰 agent의 intent 분류기이자 입력 후보 추출기다. "
                "반드시 JSON object만 출력한다. state를 직접 변경하지 않는다. "
                "intent는 patch, general_qa, rag_qa, current_input, needs_clarification 중 하나다. "
                "patch는 사용자가 의뢰서에 반영할 명시적 값을 말한 경우에만 선택한다. "
                "사내 문서·SOP·NXI·유사 보고서 근거가 필요한 질문은 rag_qa, 현재 입력 상태를 묻는 질문은 current_input, "
                "그 밖의 설명 질문은 general_qa로 분류한다. 판단이 불명확하면 needs_clarification을 선택한다. "
                "사용자가 명시한 값만 추출하고, 추론값이나 RAG 근거값은 넣지 않는다. "
                "patch가 아닌 intent에서는 operations를 빈 배열로 둔다. "
                "허용 operation은 set, list_values, condition_values 뿐이다. "
                "geometry.products, geometry.parts, conditions.fields.*.values는 복수 값 배열을 지원한다. "
                "A100과 B200, A100, B200, Fan RPM 780/900, Room 온도 27도와 30도처럼 명확히 나뉜 값은 values에 각각 분리한다. "
                "1way 카세트, P7.0 2R 18FPI Slit(Half), 2R, 18FPI처럼 숫자나 공백이 있어도 하나의 모델명/사양인 표현은 단일 값으로 유지한다. "
                "복수인지 애매하면 임의로 반영하지 말고 warnings 또는 questions에 확인 문구를 넣는다."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "message": message,
                    "current_state_summary": state_summary,
                    "public_schema": schema,
                    "allowed_output": {
                        "intent": "patch|general_qa|rag_qa|current_input|needs_clarification",
                        "operations": [
                            {
                                "op": "set",
                                "path": "basic_info.division | analysis_overview.purpose | geometry.has_changed_part ...",
                                "value": "single value",
                                "label": "field label",
                                "confidence": "low|medium|high",
                            },
                            {
                                "op": "list_values",
                                "path": "geometry.products | geometry.parts",
                                "values": ["value1"],
                                "merge_strategy": "replace|append",
                                "label": "field label",
                                "confidence": "low|medium|high",
                            },
                            {
                                "op": "condition_values",
                                "field_key": "fan_rpm",
                                "path": "conditions.fields.fan_rpm.values",
                                "values": ["1000"],
                                "merge_strategy": "replace|append",
                                "label": "field label",
                                "confidence": "low|medium|high",
                            },
                        ],
                        "summary": "short Korean summary",
                        "questions": ["clarifying question if needed"],
                        "warnings": ["limitations"],
                    },
                },
                ensure_ascii=False,
            ),
        },
    ]
    result = azure_chat_completion(messages, max_tokens=1400)
    payload = _json_object_from_text(result.get("content", ""))
    return {
        "used": True,
        "provider": "azure_openai",
        "deployment": result["deployment"],
        "api_version": result["api_version"],
        "raw_content": result.get("content", ""),
        "payload": payload,
    }


def rerank_rag_hits(question: str, hits: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Use Azure GPT as a lightweight reranker over already retrieved RAG hits."""

    if not env_flag("REQUEST_AGENT_LLM_RERANK_ENABLED", default=True):
        return {"used": False, "reason": "disabled", "hits": list(hits)}
    candidates = []
    for index, hit in enumerate(hits[:8], start=1):
        if not isinstance(hit, Mapping):
            continue
        candidates.append(
            {
                "candidate_id": index,
                "rank": hit.get("rank", index),
                "score": hit.get("score", 0),
                "retrieval_mode": _clean(hit.get("retrieval_mode")),
                "source_type": _clean(hit.get("source_type")),
                "source": _clean(hit.get("source")),
                "location": _clean(hit.get("location")),
                "content": _clean(hit.get("content"))[:700],
            }
        )
    if len(candidates) < 2:
        return {"used": False, "reason": "not_enough_hits", "hits": list(hits)}
    messages = [
        {
            "role": "system",
            "content": (
                "너는 CAE RAG 검색 결과 reranker다. 질문에 직접 답하지 말고 후보 순서만 JSON으로 반환한다. "
                "질문 해결에 더 직접적인 근거, 구체적 조건/결론이 있는 근거, source_type 의도와 맞는 근거를 우선한다. "
                "없는 내용을 만들지 않는다."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "question": question,
                    "candidates": candidates,
                    "output_schema": {
                        "ranking": [
                            {"candidate_id": 1, "relevance": 0.0, "reason": "short reason"}
                        ]
                    },
                },
                ensure_ascii=False,
            ),
        },
    ]
    result = azure_chat_completion(messages, max_tokens=1200)
    payload = _json_object_from_text(result.get("content", ""))
    ranking = payload.get("ranking") if isinstance(payload, Mapping) else []
    if not isinstance(ranking, list):
        return {"used": False, "reason": "invalid_ranking", "hits": list(hits), "raw_content": result.get("content", "")}
    by_candidate_id = {index: dict(hit) for index, hit in enumerate(hits[:8], start=1)}
    ordered: list[dict[str, Any]] = []
    seen: set[int] = set()
    for item in ranking:
        if not isinstance(item, Mapping):
            continue
        try:
            candidate_id = int(item.get("candidate_id"))
        except (TypeError, ValueError):
            continue
        hit = by_candidate_id.get(candidate_id)
        if not hit or candidate_id in seen:
            continue
        seen.add(candidate_id)
        hit["rerank"] = {
            "provider": "azure_openai",
            "relevance": item.get("relevance", ""),
            "reason": _clean(item.get("reason")),
        }
        ordered.append(hit)
    for index, hit in enumerate(hits[:8], start=1):
        if index not in seen:
            ordered.append(dict(hit))
    ordered.extend(dict(hit) for hit in hits[8:] if isinstance(hit, Mapping))
    return {
        "used": True,
        "provider": "azure_openai",
        "deployment": result["deployment"],
        "api_version": result["api_version"],
        "hits": [{**hit, "rank": index} for index, hit in enumerate(ordered, start=1)],
        "raw_content": result.get("content", ""),
    }


def synthesize_request_draft(markdown: str, evidence_sources: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    evidence_lines = []
    for source in evidence_sources[:5]:
        if not isinstance(source, Mapping):
            continue
        evidence_lines.append(
            "- "
            + "; ".join(
                part
                for part in (
                    _clean(source.get("source_type_label") or source.get("source_type")),
                    _clean(source.get("source_name") or source.get("source")),
                    _clean(source.get("source_location") or source.get("location")),
                    _clean(source.get("source_snippet") or source.get("content"))[:220],
                )
                if part
            )
        )
    evidence_text = "\n".join(evidence_lines) or "- 검색 근거 없음"
    messages = [
        {
            "role": "system",
            "content": (
                "너는 CAE 해석 의뢰서 초안 편집자다. 제공된 구조화 초안과 RAG 근거만 사용한다. "
                "새 조건값, 수치, 확정 state를 만들지 말고 문장 품질만 개선한다. "
                "배경에는 조건/수치 나열을 섞지 말고, 기존 섹션 구조를 유지한다."
            ),
        },
        {
            "role": "user",
            "content": (
                "구조화 초안:\n"
                f"{markdown}\n\n"
                "읽기 전용 RAG 근거:\n"
                f"{evidence_text}\n\n"
                "위 범위 안에서 제출용 한국어 문장으로 다듬어줘."
            ),
        },
    ]
    result = azure_chat_completion(messages, max_tokens=1200)
    return {
        "used": True,
        "provider": "azure_openai",
        "markdown": result["content"],
        "deployment": result["deployment"],
        "api_version": result["api_version"],
        "rules": [
            "no_new_state_values",
            "rag_sentence_support_only",
            "background_without_condition_numeric_list",
        ],
    }
