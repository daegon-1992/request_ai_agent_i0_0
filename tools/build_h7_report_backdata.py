#!/usr/bin/env python3
"""Build the h7_v0 standardization and implementation report backdata workbook."""

from __future__ import annotations

import argparse
import ast
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from build_h7_current_cfd_reference import (  # noqa: E402
    EXPECTED_ACTIVE_TYPES,
    RESULT_LABELS,
    _analysis_rows,
    _case_rule_rows,
    _common_field_rows,
    _gap_rows,
    _object_rows,
)
from build_structural_sme_request_pack import (  # noqa: E402
    NS_MAIN,
    SheetSpec,
    write_xlsx,
)
from request_ai_agent_i0_0.analysis_type_master import ANALYSIS_TYPE_MASTER  # noqa: E402
from request_ai_agent_i0_0.condition_fieldsets import (  # noqa: E402
    build_condition_fieldset,
    get_active_case_matrix_columns,
)
from request_ai_agent_i0_0.constants import (  # noqa: E402
    ANALYSIS_TYPE_OPTIONS,
    DISABLED_ANALYSIS_TYPE_OPTIONS,
    ENABLED_ANALYSIS_TYPE_OPTIONS,
)
from request_ai_agent_i0_0.normalized_product_hierarchy import (  # noqa: E402
    NORMALIZED_PRODUCT_HIERARCHY,
)


OUTPUT_DIR = ROOT / "docs" / "h7_v0_report_backdata"
XLSX_PATH = OUTPUT_DIR / "h7_v0_해석의뢰_표준화_적용_Backdata.xlsx"
REFERENCE_DATE = "2026-08-21"
REFERENCE_VERSION = "h7_v0-report-backdata-20260821"

STATUS_APPLIED = "적용"
STATUS_PARTIAL = "부분 적용"
STATUS_PLANNED = "미적용/예정"
STATUS_NO_EVIDENCE = "운영 증빙 없음"

EXPECTED_SHEETS = (
    "00_보고요약",
    "01_산정기준",
    "02_해석유형",
    "03_표준화_적용률",
    "04_사용자시나리오",
    "05_유형별_조건Matrix",
    "06_제품분류",
    "07_Field_Rule",
    "08_Object_Case",
    "09_검증근거",
    "10_효과측정",
    "11_Gap_Roadmap",
    "12_Source_Index",
)

EXPECTED_TOTAL_ANALYSIS_TYPES = 10
EXPECTED_ENABLED_ANALYSIS_TYPES = 4
EXPECTED_DISABLED_ANALYSIS_TYPES = 6
EXPECTED_FIELD_RULES = 38
EXPECTED_OBJECT_RULES = 8
EXPECTED_CASE_RULES = 4
EXPECTED_GAPS = 10
EXPECTED_BUSINESS_UNITS = 4
EXPECTED_PRODUCT_GROUPS = 25
EXPECTED_PLATFORMS = 141
EXPECTED_TEST_FILES = 57
EXPECTED_TEST_FUNCTIONS = 393


PARTIAL_FIELD_IDS = {
    "request_context.operation_mode": "필드는 있으나 현행 fieldset과 사용자 선택 정책에서 사용하지 않음",
    "conditions.operating.fan_count": "팬 수 구성은 지원하지만 핵심 validator의 독립 차단 규칙은 없음",
    "conditions.operating.fan_location": "다중 팬 위치는 표시되지만 핵심 validator 필수값은 아님",
    "conditions.heat_exchanger.type": "유형 선택·정규화는 지원하지만 핵심 validator의 독립 차단 규칙은 없음",
}


def _percent(numerator: int, denominator: int) -> str:
    return f"{(numerator / denominator * 100):.1f}%" if denominator else "해당 없음"


def _test_function_count(path: Path) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
    )


def _test_inventory() -> tuple[tuple[str, int, str], ...]:
    tests_dir = ROOT / "request_ai_agent_i0_0" / "tests"
    rows = []
    for path in sorted(tests_dir.glob("test_*.py"), key=lambda item: item.name):
        name = path.name
        topic = "공통 회귀"
        if "analysis_type" in name:
            topic = "해석유형·조건 분기"
        elif "product" in name or "business_unit" in name or "dropdown" in name:
            topic = "제품 분류·제품 형상"
        elif "condition" in name or "heat_exchanger" in name:
            topic = "해석조건·조건 반복"
        elif "case_matrix" in name:
            topic = "Case Matrix·Coverage"
        elif "word" in name or "preview" in name:
            topic = "미리보기·Word"
        elif "agent" in name or "orchestrator" in name or "proposal" in name:
            topic = "Agent·제안·오류 복구"
        rows.append((path.relative_to(ROOT).as_posix(), _test_function_count(path), topic))
    return tuple(rows)


def _product_counts() -> tuple[int, int, int]:
    business_units = len(NORMALIZED_PRODUCT_HIERARCHY)
    product_groups = sum(len(groups) for groups in NORMALIZED_PRODUCT_HIERARCHY.values())
    platforms = sum(
        len(platforms)
        for groups in NORMALIZED_PRODUCT_HIERARCHY.values()
        for platforms in groups.values()
    )
    return business_units, product_groups, platforms


def _scenario_rows() -> tuple[tuple[str, ...], ...]:
    """Return the decision-complete direct-form and Agent scenario inventory."""

    return (
        ("SCN-CTX-01", "직접 작성", "시작·Context", "새 의뢰", "사업부·제품군·Platform 선택", "등록된 계층 순서로 선택지를 제한", "등록되지 않은 조합", "유효한 제품 Context 후보 완성", STATUS_APPLIED, "product_hierarchy.py; ui.py", "test_business_unit_availability.py; test_dropdown_custom_switching.py"),
        ("SCN-CTX-02", "직접 작성", "시작·Context", "제품 Context 선택 완료", "활성 해석유형 선택", "풍량·기류 패턴·이슬맺힘·열교환기 유속 프로파일만 확정 허용", "예정 유형 선택", "지원 유형만 작성 단계 진입", STATUS_APPLIED, "constants.py; request_context_confirmation.py", "test_analysis_type_catalog.py"),
        ("SCN-CTX-03", "직접 작성", "시작·Context", "첫 화면", "예정 해석유형 확인", "6종을 예정·선택 불가로 표시", "API 직접 요청", "화면과 API 모두 확정 차단", STATUS_APPLIED, "constants.py; app.py; ui.py", "test_analysis_type_catalog.py"),
        ("SCN-CTX-04", "직접 작성", "시작·Context", "필수 Context 4개 입력", "의뢰서 작성 시작", "Context 잠금·의뢰번호 발급·유형별 fieldset snapshot 생성", "필수 Context 누락", "누락 안내 후 다음 단계 차단", STATUS_APPLIED, "request_context_confirmation.py; state.py", "test_analysis_type_catalog.py; test_t102_navigation_gate_focus.py"),
        ("SCN-CTX-05", "직접 작성", "시작·Context", "작성 중 Context 잠금", "제품군·Platform·유형 변경", "변경 확인 후 새 fieldset 적용 및 비활성 조건 제거", "기존 조건과 새 유형 불일치", "새 유형에서 유효한 조건만 유지", STATUS_APPLIED, "condition_fieldsets.py; state.py; ui.py", "test_task12_minimal_regression.py"),
        ("SCN-OVR-01", "직접 작성", "의뢰 내용", "Context 확정", "의뢰자 정보 입력", "사업부·부서·요청자·직급을 필수 상태로 저장", "필수값 누락", "검증 오류로 표시", STATUS_APPLIED, "constants.py; state.py; validator.py", "test_task12_minimal_regression.py"),
        ("SCN-OVR-02", "직접 작성", "의뢰 내용", "Context 확정", "프로젝트·개발 등급·NPI·모델 입력", "선택 또는 직접 입력값을 canonical Field로 저장", "직접 입력 전환", "사용자 입력을 보존", STATUS_APPLIED, "constants.py; state.py; ui.py", "test_project_name_editable_combobox.py; test_dropdown_custom_switching.py"),
        ("SCN-OVR-03", "직접 작성", "의뢰 내용", "의뢰 요청일 존재", "희망 완료일 선택", "요청일 이전 날짜를 허용하지 않음", "과거 날짜 선택", "입력 단계에서 차단 안내", STATUS_APPLIED, "ui.py; validator.py", "test_desired_completion_date_minimum.py"),
        ("SCN-OVR-04", "직접 작성", "의뢰 내용", "작성 단계", "요청 배경과 확인 내용 입력", "두 서술 필드를 필수·진행률 대상으로 관리", "빈 값", "검증·진행률에 미완료 반영", STATUS_APPLIED, "constants.py; validator.py", "test_t201b_request_content_canonical.py"),
        ("SCN-OVR-05", "직접 작성", "의뢰 내용", "결과 활용 목적", "선택 입력 또는 미작성", "선택값은 저장하되 미작성은 제출을 차단하지 않음", "미작성", "선택 항목으로 정상 처리", STATUS_APPLIED, "constants.py; validator.py", "test_t201b_request_content_canonical.py"),
        ("SCN-GEO-01", "직접 작성", "제품 형상", "제품 입력 시작", "Base 제품 입력", "Base 제품을 정확히 1개 유지", "Base 제거", "Base 부재를 차단", STATUS_APPLIED, "state.py; validator.py", "test_t202_product_card_workflow.py"),
        ("SCN-GEO-02", "직접 작성", "제품 형상", "Base 존재", "비교 제품 추가·삭제", "비교 제품을 0..N 반복 객체로 관리", "행 삭제 중 미저장 값", "현재 입력을 보존한 뒤 선택 행만 변경", STATUS_APPLIED, "state.py; ui.py", "test_t202_product_card_workflow.py"),
        ("SCN-GEO-03", "직접 작성", "제품 형상", "비교 제품 추가", "Base 대비 차이 입력", "비교 제품마다 차이 설명을 조건부 필수로 검증", "차이 설명 누락", "해당 비교 제품을 특정해 차단", STATUS_APPLIED, "state.py; validator.py", "test_t202_product_card_workflow.py"),
        ("SCN-GEO-04", "직접 작성", "제품 형상", "제품 행 존재", "도면번호 입력", "영문·숫자·하이픈 형식과 제품 간 중복을 검증", "형식 오류·중복", "오류 제품을 특정해 차단", STATUS_APPLIED, "state.py; validator.py", "test_t202_product_card_workflow.py"),
        ("SCN-GEO-05", "직접 작성", "제품 형상", "유효 도면번호 존재", "형상 축 생성", "제품 순서대로 형상 1..N과 안정적인 geometry_id 생성", "표시명 사용자 수정", "사용자 표시명을 보존", STATUS_APPLIED, "geometry_engine.py; state.py", "test_t202_product_card_workflow.py; test_task12_minimal_regression.py"),
        ("SCN-CND-01", "직접 작성", "해석조건", "풍량 선택", "조건 입력", "운전·열교환기 카드만 활성화", "온·습도 legacy 값", "비활성 조건을 Field·Case에서 제외", STATUS_APPLIED, "condition_fieldsets.py; state.py", "test_analysis_type_catalog.py"),
        ("SCN-CND-02", "직접 작성", "해석조건", "열교환기 유속 프로파일 선택", "조건 입력", "운전·열교환기 카드만 활성화", "온·습도 입력 시도", "비활성 조건을 노출·저장하지 않음", STATUS_APPLIED, "condition_fieldsets.py; ui.py", "test_analysis_type_catalog.py"),
        ("SCN-CND-03", "직접 작성", "해석조건", "기류 패턴 선택", "조건 입력", "운전·열교환기·취출 온도·공간 온도를 활성화하고 RH 제외", "온도 기준 없음", "직접 값 또는 없음 선택 허용", STATUS_APPLIED, "condition_fieldsets.py; ui.py", "test_analysis_type_catalog.py"),
        ("SCN-CND-04", "직접 작성", "해석조건", "이슬맺힘 선택", "조건 입력", "운전·열교환기·취출/공간 온도·RH를 모두 활성화", "온·습도 누락", "활성 필드를 차단 검증", STATUS_APPLIED, "condition_fieldsets.py; validator.py", "test_analysis_type_catalog.py"),
        ("SCN-CND-05", "직접 작성", "해석조건", "활성 조건 카드", "조건 행 추가·삭제", "첫 기본 카드를 유지하고 추가 카드를 반복 관리", "마지막 기본 카드 삭제", "기본 카드 유지", STATUS_APPLIED, "condition_fieldsets.py; ui.py", "test_t203_condition_card_workflow.py"),
        ("SCN-CND-06", "직접 작성", "해석조건", "운전 카드", "팬 개수·위치 입력", "복수 팬 구성과 화면 표시는 지원", "팬 위치 누락", "표시는 가능하지만 핵심 validator 필수 판정은 없음", STATUS_PARTIAL, "condition_fieldsets.py; ui.py; validator.py", "test_t203_condition_card_workflow.py"),
        ("SCN-CND-07", "직접 작성", "해석조건", "운전 카드", "팬별 RPM 입력", "활성 팬마다 RPM을 필수로 처리하고 하나의 팬 구성을 한 조건으로 관리", "RPM 누락", "해당 팬 구성을 미완료 처리", STATUS_APPLIED, "condition_fieldsets.py; validator.py", "test_t203_condition_card_workflow.py"),
        ("SCN-CND-08", "직접 작성", "해석조건", "열교환기 카드", "Fin&Tube/Micro-Channel 입력", "W 접두 관 직경을 Micro-Channel로 분류하고 Fin type을 Flat으로 정규화", "Catalog 불일치", "확인 또는 수정 제안", STATUS_APPLIED, "condition_fieldsets.py; heat_exchanger_catalog.py", "test_t205_heat_exchanger_catalog.py"),
        ("SCN-CND-09", "직접 작성", "해석조건", "열교환기 카드", "관 직경·Fin type·열 수·FPI 입력", "활성 상세 필드를 사양 단위로 필수 검증", "수치 물리 범위 이탈", "누락은 차단하나 물리 범위 정책은 없음", STATUS_PARTIAL, "condition_fieldsets.py; validator.py", "test_t203_condition_card_workflow.py"),
        ("SCN-CND-10", "직접 작성", "해석조건", "기류 패턴 온도 Field", "없음 선택", "빈 값과 구분되는 제공 상태로 저장", "RH Field에서 없음 시도", "허용 대상 Field에만 적용", STATUS_APPLIED, "condition_fieldsets.py; state.py; ui.py", "test_analysis_type_catalog.py"),
        ("SCN-CND-11", "직접 작성", "해석조건", "조건 Field 상태", "모름·해당 없음 표현", "일부 상태값은 존재하지만 조건별 통합 정책은 미완성", "유형별 판단 필요", "담당자 확인 대상으로 남김", STATUS_PARTIAL, "constants.py; state.py", "test_task4b_main_chat_decision.py"),
        ("SCN-CASE-01", "직접 작성", "Case Matrix", "유효 형상 존재", "Case Matrix 진입", "형상당 기본 Case 행 1개와 첫 활성 조건값 연결", "조건 미완성", "선택 누락 상태로 표시", STATUS_APPLIED, "state.py; case_matrix.py", "test_task12_minimal_regression.py"),
        ("SCN-CASE-02", "직접 작성", "Case Matrix", "기본 Case 존재", "Case 행 추가·삭제", "필요한 조합만 수동 추가하고 최소 1행 유지", "마지막 Case 삭제", "로컬 안내와 함께 최소 행 유지", STATUS_APPLIED, "state.py; ui.py", "test_case_matrix_coverage.py"),
        ("SCN-CASE-03", "직접 작성", "Case Matrix", "Case 편집 중", "형상·조건 원본 변경", "존재하지 않는 선택을 비우고 새 옵션을 반영", "삭제된 조건 참조", "유효하지 않은 선택 제거", STATUS_APPLIED, "state.py; ui.py", "test_task12_minimal_regression.py"),
        ("SCN-CASE-04", "직접 작성", "Case Matrix", "Case 행 존재", "필수 선택 확인", "유형별 활성 열의 누락을 차단", "한 열 미선택", "Case·열을 특정해 오류 표시", STATUS_APPLIED, "validator.py; ui.py", "test_task12_minimal_regression.py; test_case_matrix_coverage.py"),
        ("SCN-CASE-05", "직접 작성", "Case Matrix", "완성 Case 2개 이상", "중복 조합 확인", "형상과 모든 활성 조건값이 같은 signature를 중복 판정", "중복 Case", "Word 생성 차단", STATUS_APPLIED, "validator.py", "test_task12_minimal_regression.py; test_case_matrix_coverage.py"),
        ("SCN-CASE-06", "직접 작성", "Case Matrix", "형상·조건 입력 완료", "Coverage 확인", "입력값이 최소 한 Case에 사용됐는지 별도 표시", "Cartesian product 미생성", "모든 값이 한 번 이상 사용되면 완료", STATUS_APPLIED, "validator.py; ui.py", "test_case_matrix_coverage.py"),
        ("SCN-CASE-07", "직접 작성", "Case Matrix", "Coverage 미완료", "다음 화면 이동", "검토는 허용하되 Word 생성은 차단", "미사용 입력 존재", "미사용 열별 안내", STATUS_APPLIED, "validator.py; app.py; ui.py", "test_case_matrix_coverage.py"),
        ("SCN-OUT-01", "직접 작성", "미리보기·Word", "작성 중", "전체 미리보기", "현재 State의 요청·형상·조건·Case와 오류를 같은 계약으로 표시", "누락 입력", "경고와 현재 값을 함께 표시", STATUS_APPLIED, "preview_document.py; ui.py", "test_full_preview_labels.py; test_preview_missing_input_warnings.py"),
        ("SCN-OUT-02", "직접 작성", "미리보기·Word", "Case·Coverage 정상", "Word 생성", "렌더링된 미리보기 payload를 DOCX 원본으로 사용", "중복·누락·Coverage 미완료", "DOCX 생성 전 차단", STATUS_APPLIED, "app.py; word_export.py", "test_case_matrix_coverage.py; test_word_export_dependency.py"),
        ("SCN-AGT-01", "Agent 지원", "질문·제안", "서버 State 존재", "현재 값 질문", "State를 읽기 전용으로 답하고 제안을 만들지 않음", "RAG/외부 응답 실패", "State 무변경", STATUS_APPLIED, "agent_decision.py; app.py", "test_task4b_main_chat_decision.py"),
        ("SCN-AGT-02", "Agent 지원", "질문·제안", "활성 Field 존재", "짧은 값 답변", "정확한 대상 Field 제안만 생성하고 승인 대기", "비활성 Field", "제안하지 않음", STATUS_APPLIED, "agent_decision.py; proposal_store.py", "test_task4b_main_chat_decision.py"),
        ("SCN-AGT-03", "Agent 지원", "질문·제안", "여러 값이 한 메시지에 존재", "복수 입력 전달", "여러 operation을 하나의 원자적 proposal로 생성", "일부 값 모호", "명확한 값 보존 후 추가 확인", STATUS_APPLIED, "agent_decision.py; proposal_store.py", "test_task4b_main_chat_decision.py"),
        ("SCN-AGT-04", "Agent 지원", "질문·제안", "제안 생성", "승인·거절", "승인 전 State 무변경, 승인 시 버전 검증 후 한 번만 적용", "거절", "State 유지", STATUS_APPLIED, "proposal_store.py; request_state_store.py", "test_orchestrator_proposal_store.py; test_orchestrator_proposal_ui.py"),
        ("SCN-AGT-05", "Agent 지원", "질문·제안", "필수 사실 근거 부족", "Agent 작성 위임", "임의 추정하지 않고 명확화 질문", "필수 공학 정보 없음", "사용자 확인 대기", STATUS_APPLIED, "agent_decision.py; form_context.py", "test_task4b_main_chat_decision.py"),
        ("SCN-AGT-06", "Agent 지원", "질문·제안", "입력 질문 진행 중", "제품 계층 등 부가 질문", "읽기 전용 답변 후 원래 입력 초점을 유지", "0·1·복수 검색 결과", "결과 수에 맞춰 안내하고 교차 입력 방지", STATUS_APPLIED, "agent_decision.py; product_hierarchy.py", "test_task4b_main_chat_decision.py"),
        ("SCN-AGT-07", "Agent 지원", "오류 복구", "pending proposal 존재", "두 번째 변경 요청", "기존 proposal 처리 전 새 proposal 생성을 차단", "단순 현재 값 질문", "읽기 전용 답변은 허용", STATUS_APPLIED, "agent_decision.py; proposal_store.py", "test_task4b_main_chat_decision.py"),
        ("SCN-AGT-08", "Agent 지원", "오류 복구", "제안 생성 이후 State 변경", "과거 제안 승인", "request version·fingerprint 불일치로 stale 제안 차단", "동시 편집", "새 제안 요청 안내", STATUS_APPLIED, "proposal_store.py; request_state_store.py", "test_orchestrator_request_version.py; test_task4b_main_chat_decision.py"),
        ("SCN-AGT-09", "Agent 지원", "오류 복구", "LLM 호출", "LLM 실패 또는 잘못된 operation", "규칙 기반 임의 fallback 없이 State와 대화 저장을 보존", "LLM 오류", "오류 안내만 반환", STATUS_APPLIED, "agent_decision.py; app.py", "test_task4b_main_chat_decision.py; test_task12_minimal_regression.py"),
        ("SCN-AGT-10", "Agent 지원", "다음 질문", "반복 제품·조건 객체", "다음 미입력 질문", "정확한 객체 인스턴스와 활성 Field를 대상으로 질문", "시스템 생성·비활성 Field", "질문 대상에서 제외", STATUS_APPLIED, "agent_next_question.py; next_field_planner.py", "test_task5a_agent_next_question.py"),
        ("SCN-OPS-01", "운영 검증", "실제 사례", "활성 유형 4종", "실제 정상·다중·누락 사례 재현", "유형별 3건을 Master로 재현해야 업무 승인", "저장소 사례 없음", "코드 구현과 분리해 증빙 없음 표시", STATUS_NO_EVIDENCE, "docs/structural_analysis_sme_request/h7_v0_현행_유동해석_Field_Master.xlsx#07_검수_승인", "현행 자동화 테스트는 업무 사례를 대체하지 않음"),
    )


def _analysis_type_rows() -> tuple[tuple[str, ...], ...]:
    rows = []
    for source in _analysis_rows():
        analysis_type = source[0]
        enabled = analysis_type in ENABLED_ANALYSIS_TYPE_OPTIONS
        columns = get_active_case_matrix_columns({"analysis_type": analysis_type}) if enabled else []
        rows.append((
            "Catalog 분모",
            "예",
            analysis_type,
            "활성" if enabled else "예정",
            source[1],
            RESULT_LABELS.get(analysis_type, "담당자 확인 필요"),
            source[10],
            ", ".join(column["label"] for column in columns) if enabled else "유형별 Case 규칙 미정",
            STATUS_APPLIED if enabled else STATUS_PLANNED,
            "자동검증 있음" if enabled else "예정 유형 선택 차단만 검증",
            STATUS_NO_EVIDENCE,
            source[12],
            "test_analysis_type_catalog.py",
        ))
    rows.extend((
        ("Legacy 참고", "아니오", "일반 유동 해석", "Legacy 읽기", "기존 저장 의뢰 호환용 조건 정의", "현행 신규 결과 안내 아님", "운전 조건, 열교환기 사양", "형상, 운전, 사양", STATUS_PARTIAL, "Legacy 읽기 호환", STATUS_NO_EVIDENCE, "condition_fieldsets.py", "test_task12_minimal_regression.py"),
        ("Legacy 참고", "아니오", "열유동 해석", "Legacy 읽기", "기존 저장 의뢰 호환용 조건 정의", "현행 신규 결과 안내 아님", "운전, 열교환기, 취출, 공간(습도 제외)", "형상 및 활성 온도", STATUS_PARTIAL, "Legacy 읽기 호환", STATUS_NO_EVIDENCE, "condition_fieldsets.py", "test_task12_minimal_regression.py"),
        ("Catalog Gap", "아니오", "냉매누설", "안내 Master만 존재", ANALYSIS_TYPE_MASTER.get("냉매누설", "결과 안내만 존재"), "Catalog 미등록", "미정", "미정", STATUS_PLANNED, "자동검증 대상 아님", STATUS_NO_EVIDENCE, "analysis_type_master.py; constants.py", "10_현행_Gap_목록 GAP-10"),
    ))
    return tuple(rows)


def _condition_matrix_rows() -> tuple[tuple[str, ...], ...]:
    rows = []
    for analysis_type in ANALYSIS_TYPE_OPTIONS:
        if analysis_type not in ENABLED_ANALYSIS_TYPE_OPTIONS:
            rows.append((analysis_type, "예정", "미정", "미정", "미정", "미정", "미정", "미정", "미정", "미정", STATUS_PLANNED, "유형별 Field/Case Master 필요"))
            continue
        fieldset = build_condition_fieldset({"analysis_type": analysis_type})
        fields = {field["key"]: field for group in fieldset["groups"] for field in group["fields"] if group["active"] and field["active"]}
        columns = get_active_case_matrix_columns({"analysis_type": analysis_type})
        def state(key: str) -> str:
            return "필수" if key in fields and fields[key].get("required") else ("활성" if key in fields else "비활성")
        none_allowed = ", ".join(
            fields[key]["label"]
            for key in ("heat_exchanger_temp", "room_temp")
            if key in fields and "없음" in fields[key].get("allowed_values", [])
        ) or "허용 없음"
        rows.append((
            analysis_type,
            "활성",
            state("fan_rpm"),
            "필수" if all(key in fields for key in ("tube_diameter", "fin_type", "row_count", "fpi")) else "비활성",
            state("heat_exchanger_temp"),
            state("heat_exchanger_rh"),
            state("room_temp"),
            state("room_rh"),
            none_allowed,
            "형상, " + ", ".join(column["label"] for column in columns),
            STATUS_APPLIED,
            "condition_fieldsets.py; test_analysis_type_catalog.py",
        ))
    return tuple(rows)


def _product_rows() -> tuple[tuple[str, ...], ...]:
    rows = []
    for business_unit, groups in NORMALIZED_PRODUCT_HIERARCHY.items():
        unit_platforms = sum(len(platforms) for platforms in groups.values())
        for order, (product_group, platforms) in enumerate(groups.items(), 1):
            rows.append((
                business_unit,
                str(len(groups)),
                str(unit_platforms),
                str(order),
                product_group,
                str(len(platforms)),
                ", ".join(platforms),
                STATUS_APPLIED,
                "현재 등록 규모이며 전사 제품 대비 커버리지 비율이 아님",
                "normalized_product_hierarchy.py",
            ))
    return tuple(rows)


def _field_rows() -> tuple[tuple[str, ...], ...]:
    rows = []
    for row in _common_field_rows():
        rule_id = row[0]
        status = STATUS_PARTIAL if rule_id in PARTIAL_FIELD_IDS else STATUS_APPLIED
        limitation = PARTIAL_FIELD_IDS.get(rule_id, "현행 코드 기준 구현·추적 가능")
        automated = "관련 회귀 있음" if status in {STATUS_APPLIED, STATUS_PARTIAL} else "없음"
        rows.append((*row, status, automated, STATUS_NO_EVIDENCE, limitation))
    return tuple(rows)


def _object_case_rows() -> tuple[tuple[str, ...], ...]:
    rows = []
    for row in _object_rows():
        rows.append((
            "핵심 객체", row[0], row[1], row[3], row[2], f"최소 {row[4]} / 최대 {row[5]}",
            row[6], row[8], row[9], STATUS_APPLIED, STATUS_NO_EVIDENCE, row[14],
        ))
    for row in _case_rule_rows():
        rows.append((
            "Case 규칙", row[0], row[1], row[1], row[2], row[5], "행 추가 가능", row[2],
            f"{row[6]} / 중복: {row[7]}", STATUS_APPLIED, STATUS_NO_EVIDENCE, row[14],
        ))
    return tuple(rows)


def _rate_rows(scenarios: Iterable[tuple[str, ...]]) -> tuple[tuple[str, ...], ...]:
    scenario_rows = tuple(scenarios)
    field_rows = _field_rows()
    context_rows = [row for row in field_rows if row[1] == "공통"]
    common_rows = [row for row in field_rows if row[1] in {"의뢰 정보", "해석 개요"}]
    geometry_rows = [row for row in field_rows if row[1] == "제품/형상"]
    condition_rows = [row for row in field_rows if row[1] == "해석조건"]

    def rate_row(category: str, items: Iterable[str], source: str, note: str) -> tuple[str, ...]:
        values = tuple(items)
        counts = Counter(values)
        total = len(values)
        applied = counts[STATUS_APPLIED]
        partial = counts[STATUS_PARTIAL]
        planned = counts[STATUS_PLANNED]
        no_evidence = counts[STATUS_NO_EVIDENCE]
        return (category, str(total), str(applied), str(partial), str(planned), str(no_evidence), _percent(applied, total), source, note)

    direct_scenarios = [row[8] for row in scenario_rows if row[1] == "직접 작성"]
    agent_scenarios = [row[8] for row in scenario_rows if row[1] == "Agent 지원"]
    output_scenarios = [row[8] for row in scenario_rows if row[2] == "미리보기·Word"]
    return (
        rate_row("전체 해석유형 Catalog", [STATUS_APPLIED] * len(ENABLED_ANALYSIS_TYPE_OPTIONS) + [STATUS_PLANNED] * len(DISABLED_ANALYSIS_TYPE_OPTIONS), "constants.py", "최상단 구현률: 전체 Catalog 10종을 분모로 사용"),
        rate_row("활성 유형별 Fieldset·Case 정책", [STATUS_APPLIED] * len(EXPECTED_ACTIVE_TYPES), "condition_fieldsets.py", "현재 활성 4종 내부 표준화"),
        rate_row("Context Field", [row[20] for row in context_rows], "07_Field_Rule", "운전 모드는 현행 미사용"),
        rate_row("의뢰자·해석개요 Field", [row[20] for row in common_rows], "07_Field_Rule", "필수·선택·날짜·직접 입력 계약"),
        rate_row("제품/형상 Field", [row[20] for row in geometry_rows], "07_Field_Rule", "Base 1개와 비교 제품 0..N"),
        rate_row("해석조건 Field", [row[20] for row in condition_rows], "07_Field_Rule", "팬 위치·물리 범위 등 부분 적용 분리"),
        rate_row("핵심 객체", [STATUS_APPLIED] * len(_object_rows()), "08_Object_Case", "Context부터 Case까지 객체 계약"),
        rate_row("유형별 Case 규칙", [STATUS_APPLIED] * len(_case_rule_rows()), "08_Object_Case", "활성 4종 수동 매핑 규칙"),
        rate_row("직접 작성 사용자 시나리오", direct_scenarios, "04_사용자시나리오", "활성 유형의 표준 사용자 흐름"),
        rate_row("Agent 지원 시나리오", agent_scenarios, "04_사용자시나리오", "제안·승인·명확화·오류 복구"),
        rate_row("미리보기·Word 시나리오", output_scenarios, "04_사용자시나리오", "Case 검증과 출력 계약"),
    )


def _summary_rows() -> tuple[tuple[str, ...], ...]:
    business_units, product_groups, platforms = _product_counts()
    tests = _test_inventory()
    test_functions = sum(row[1] for row in tests)
    active_rate = _percent(len(ENABLED_ANALYSIS_TYPE_OPTIONS), len(ANALYSIS_TYPE_OPTIONS))
    return (
        ("기준", "기준일", REFERENCE_DATE, "저장소 현행 코드 기준", "업무 재승인과 구분"),
        ("기준", "백데이터 버전", REFERENCE_VERSION, "재생성 가능한 정적 집계", "--check 지원"),
        ("핵심 KPI", "전체 Catalog 해석유형 구현률", active_rate, f"활성 {len(ENABLED_ANALYSIS_TYPE_OPTIONS)}종 / 전체 {len(ANALYSIS_TYPE_OPTIONS)}종", "예정 6종 포함 분모"),
        ("핵심 KPI", "활성 유형 Fieldset·Case 정책", _percent(len(EXPECTED_ACTIVE_TYPES), len(EXPECTED_ACTIVE_TYPES)), "4종 / 4종", "현재 활성 범위"),
        ("등록 규모", "제품 분류", f"{business_units}개 사업영역 / {product_groups}개 제품군 / {platforms}개 Platform", "현재 코드 등록값", "전사 커버리지 비율 아님"),
        ("표준화 원천", "Field Rule", f"{len(_common_field_rows())}개", "코드 근거 추적 완료", f"부분 적용 {len(PARTIAL_FIELD_IDS)}개 별도 표시"),
        ("표준화 원천", "핵심 객체", f"{len(_object_rows())}개", "Context·제품·조건·Case", "업무 승인 별도"),
        ("표준화 원천", "유형별 Case 규칙", f"{len(_case_rule_rows())}개", "활성 유형별 1개", "물리 금지 조합 Gap 별도"),
        ("자동검증", "테스트 규모", f"{len(tests)}개 파일 / {test_functions}개 함수", "h7_v0 tests 디렉터리", "업무 완료사례를 대체하지 않음"),
        ("잔여과제", "미해결 Gap", f"{len(_gap_rows())}건", "높음·중간·낮음 분리", "11_Gap_Roadmap 참조"),
        ("업무 검증", "활성 유형 실제 사례·SME 승인", "저장소 증빙 0/4", "코드 구현률과 분리", "유형별 최소 3건 재현 필요"),
        ("보고 메시지", "표준화 성과", "활성 4종의 Field·객체·Case·사용자 시나리오는 대부분 코드에 적용", "세부 적용률은 03 시트", "전체 유형 확장률 40%와 혼동 금지"),
        ("보고 메시지", "향후 과제", "예정 6종 Field/Case Master, 물리 범위, 모름 정책, 결과 판정, 실제 사례 승인", "11 시트 우선순위", "운영 실적 확보 후 효과 정량화"),
    )


def _criteria_rows() -> tuple[tuple[str, ...], ...]:
    return (
        ("상태", STATUS_APPLIED, "표준 규칙이 사용자 흐름과 State/검증/출력 중 필요한 경로에 구현되고 코드 또는 테스트 근거가 있음", "엄격 구현률 분자 포함", "근거 없는 적용 표기 금지"),
        ("상태", STATUS_PARTIAL, "구조나 UI는 구현됐지만 필수 검증·업무 규칙·연계 중 일부가 미완성", "구현률 분자 제외, 별도 건수 표시", "0.5 가중치를 사용하지 않음"),
        ("상태", STATUS_PLANNED, "Catalog에는 있으나 사용자 선택·유형별 Field/Case 구현이 없음", "구현률 분자 제외", "예정 6종 포함"),
        ("상태", STATUS_NO_EVIDENCE, "코드 구현과 별개로 실제 완료사례·사용 빈도·SME 승인 근거가 없음", "코드 구현률과 분리", "운영 미구현이라는 뜻은 아님"),
        ("산식", "해석유형 구현률", "활성 해석유형 수 / 전체 Catalog 해석유형 수 × 100", "4 / 10 = 40.0%", "Legacy와 Catalog 불일치는 분모 제외"),
        ("산식", "항목별 엄격 구현률", "적용 항목 수 / 해당 범주의 전체 표준항목 수 × 100", "부분 적용은 분자 제외", "범주별로만 비교"),
        ("금지", "단일 종합점수", "유형·Field·객체·시나리오를 임의 가중해 하나의 점수로 합산하지 않음", "해당 없음", "Field 수가 전체 결과를 왜곡하는 것을 방지"),
        ("해석", "제품 분류 수", "4개 사업영역·25개 제품군·141개 Platform은 현재 등록 규모", "커버리지율 산정 안 함", "전사 전체 제품 Master가 없기 때문"),
        ("해석", "자동화 테스트", "코드 회귀 근거이며 실제 업무 적합성·무재문의 착수 가능성을 직접 증명하지 않음", "업무 승인과 분리", "실제 사례 재현 필요"),
    )


def _verification_rows() -> tuple[tuple[str, ...], ...]:
    key_files = {
        "test_analysis_type_catalog.py": "해석유형 10종·활성 4종·유형별 조건 정책",
        "test_t202_product_card_workflow.py": "Base/비교 제품·도면번호·형상 축",
        "test_t203_condition_card_workflow.py": "조건 카드 반복·복수 팬·미리보기",
        "test_case_matrix_coverage.py": "Case 누락·중복·Coverage·Word 차단",
        "test_task12_minimal_regression.py": "활성 조건·수동 Case·미리보기·Word 통합 회귀",
        "test_task4b_main_chat_decision.py": "Agent 제안·명확화·오류 복구",
        "test_task5a_agent_next_question.py": "반복 객체별 다음 질문",
    }
    rows = []
    for path, count, topic in _test_inventory():
        name = Path(path).name
        rows.append((
            "핵심 회귀" if name in key_files else "전체 회귀",
            path,
            str(count),
            topic,
            key_files.get(name, "h7_v0 전체 회귀 근거"),
            "실행 대상" if name in key_files else "전체 테스트 시 포함",
            "코드 검증",
            "실제 업무 사례·SME 승인을 대체하지 않음",
        ))
    return tuple(rows)


def _benefit_rows() -> tuple[tuple[str, ...], ...]:
    return (
        ("KPI-01", "필수정보 누락률", "최초 제출 의뢰 중 필수 Field 누락 의뢰 비율", "필수정보 누락 의뢰 건수 / 전체 최초 제출 건수 × 100", "제출 시 validation 결과·의뢰 ID", "월별", "도입 전·후 동일 유형 비교", "기대: 유형별 필수 Field와 차단 검증으로 감소", "실적 없음"),
        ("KPI-02", "재문의율", "최초 의뢰 후 해석 담당자가 추가 정보를 요청한 비율", "재문의 발생 의뢰 건수 / 전체 접수 의뢰 건수 × 100", "의뢰 ID·재문의 일시·재문의 사유", "월별", "유형·제품군별 분리", "기대: 조건 세분화와 Agent 질문으로 감소", "실적 없음"),
        ("KPI-03", "Case 수정률", "접수 검토 중 형상·조건 Case 조합을 수정한 비율", "Case 수정 의뢰 건수 / Case 작성 의뢰 건수 × 100", "Case revision·수정 사유", "월별", "중복·누락·Coverage 사유 구분", "기대: 수동 Matrix와 검증으로 오류 감소", "실적 없음"),
        ("KPI-04", "의뢰서 작성시간", "새 의뢰 시작부터 Word 생성까지 걸린 활성 작성시간", "Word 생성시각 - 작성 시작시각 - 비활성 시간", "세션 시작·Field 변경·Word 생성 시각", "월별 중앙값", "유형 난이도별 비교", "기대: 표준 선택지와 Agent 보조로 단축", "실적 없음"),
        ("KPI-05", "1차 접수 가능률", "추가 정보 요청 없이 해석 담당자가 1차 검토 가능한 비율", "무재문의 접수 가능 건수 / 전체 검토 건수 × 100", "담당자 접수 판정·사유", "월별", "SME 판정 기준 선행 정의", "기대: 표준 Field·Case 완결성으로 증가", "실적 없음"),
    )


def _gap_roadmap_rows() -> tuple[tuple[str, ...], ...]:
    sequence = {"GAP-01": 1, "GAP-04": 2, "GAP-05": 3, "GAP-08": 4, "GAP-07": 5, "GAP-06": 6, "GAP-02": 7, "GAP-09": 8, "GAP-03": 9, "GAP-10": 10}
    prerequisites = {
        "GAP-01": "유형별 익명화 완료사례·재문의·보고서",
        "GAP-02": "미사용 public Field의 업무 필요성 검토",
        "GAP-03": "예정 유형별 SME와 대표 사례",
        "GAP-04": "제품·유형별 물리 허용범위",
        "GAP-05": "조건별 모름·해당 없음·담당자 이관 기준",
        "GAP-06": "유형별 물리적 금지·필수 Case 조합",
        "GAP-07": "복수 팬 위치의 업무 필수성",
        "GAP-08": "유형별 결과 항목·정량 판정 기준",
        "GAP-09": "로그인·사용자 프로필 연동 정책",
        "GAP-10": "냉매누설 Catalog 운영 결정",
    }
    rows = []
    for gap in sorted(_gap_rows(), key=lambda row: sequence[row[0]]):
        rows.append((
            str(sequence[gap[0]]), gap[0], gap[1], gap[2], gap[3], gap[4], prerequisites[gap[0]], gap[5], gap[6],
            "업무 표준 고도화" if gap[3] == "높음" else ("구현 완결성" if gap[3] == "중간" else "Catalog 정합성"),
            gap[7],
        ))
    return tuple(rows)


def _source_rows() -> tuple[tuple[str, ...], ...]:
    business_units, product_groups, platforms = _product_counts()
    tests = _test_inventory()
    return (
        ("기준", "기준일", REFERENCE_DATE, "보고 Backdata 기준일", "고정", "00_보고요약"),
        ("코드", "해석유형 Catalog", "request_ai_agent_i0_0/constants.py", f"전체 {len(ANALYSIS_TYPE_OPTIONS)} / 활성 {len(ENABLED_ANALYSIS_TYPE_OPTIONS)} / 예정 {len(DISABLED_ANALYSIS_TYPE_OPTIONS)}", "직접 import", "02_해석유형"),
        ("코드", "유형별 조건·Case", "request_ai_agent_i0_0/condition_fieldsets.py", "활성 Field와 Case 열", "직접 import", "05_유형별_조건Matrix"),
        ("코드", "제품 분류", "request_ai_agent_i0_0/normalized_product_hierarchy.py", f"{business_units}/{product_groups}/{platforms}", "직접 import", "06_제품분류"),
        ("코드", "State·제품·Case", "request_ai_agent_i0_0/state.py", "정규화·수동 Case", "코드 추적", "04·08"),
        ("코드", "검증", "request_ai_agent_i0_0/validator.py", "필수 Field·제품·조건·Case·Coverage", "코드 추적", "03·04·08"),
        ("코드", "Agent", "request_ai_agent_i0_0/agent_decision.py", "질문·제안·명확화·오류 복구", "코드 추적", "04_사용자시나리오"),
        ("코드", "Word", "request_ai_agent_i0_0/word_export.py", "미리보기 기반 DOCX", "코드 추적", "04_사용자시나리오"),
        ("문서", "현행 CFD 기준", "docs/structural_analysis_sme_request/04_h7_v0_현행_유동해석_기준.md", "2026-08-20 역정리", "기존 기준", "전체"),
        ("문서", "현행 Field Master", "docs/structural_analysis_sme_request/h7_v0_현행_유동해석_Field_Master.xlsx", f"Field {len(_common_field_rows())} / 객체 {len(_object_rows())} / Case {len(_case_rule_rows())} / Gap {len(_gap_rows())}", "기존 산출물", "07·08·11"),
        ("테스트", "자동화 테스트", "request_ai_agent_i0_0/tests", f"{len(tests)}개 파일 / {sum(row[1] for row in tests)}개 함수", "AST 집계", "09_검증근거"),
        ("산정", "해석유형 구현률", "활성 / 전체 Catalog", f"{len(ENABLED_ANALYSIS_TYPE_OPTIONS)}/{len(ANALYSIS_TYPE_OPTIONS)}={_percent(len(ENABLED_ANALYSIS_TYPE_OPTIONS), len(ANALYSIS_TYPE_OPTIONS))}", "부분 적용 가중 없음", "00·01·03"),
    )


def _sheet_specs() -> tuple[SheetSpec, ...]:
    scenarios = _scenario_rows()
    return (
        SheetSpec("00_보고요약", ("구분", "지표", "현행 값", "산출 근거", "해석·주의사항"), rows=_summary_rows(), instruction_sheet=True, blank_rows=0),
        SheetSpec("01_산정기준", ("구분", "항목", "정의·산식", "집계 처리", "주의사항"), rows=_criteria_rows(), reference_sheet=True, blank_rows=0),
        SheetSpec("02_해석유형", ("행 구분", "Catalog 분모 포함", "해석유형", "현재 상태", "사용자 목적", "대표 결과", "활성 조건 카드", "Case 선택 열", "구현 상태", "자동검증", "업무 검증", "코드 근거", "테스트·Gap 근거"), rows=_analysis_type_rows(), reference_sheet=True, blank_rows=0),
        SheetSpec("03_표준화_적용률", ("표준화 범주", "전체 항목", "적용", "부분 적용", "미적용/예정", "운영 증빙 없음", "엄격 구현률", "상세 근거", "해석"), rows=_rate_rows(scenarios), reference_sheet=True, blank_rows=0),
        SheetSpec("04_사용자시나리오", ("시나리오 ID", "경로", "단계", "사전조건", "사용자 행동·입력", "표준 동작", "예외·실패조건", "기대 결과", "구현 상태", "코드 근거", "테스트·업무 근거"), rows=scenarios, reference_sheet=True, blank_rows=0),
        SheetSpec("05_유형별_조건Matrix", ("해석유형", "현재 상태", "팬 RPM", "열교환기 사양", "취출 온도", "취출 RH", "공간 온도", "공간 RH", "없음 허용", "Case 선택 열", "구현 상태", "근거·필요조치"), rows=_condition_matrix_rows(), reference_sheet=True, blank_rows=0),
        SheetSpec("06_제품분류", ("사업영역", "사업영역 내 제품군 수", "사업영역 내 Platform 수", "제품군 순서", "제품군", "Platform 수", "Platform 목록", "구현 상태", "해석 주의사항", "코드 근거"), rows=_product_rows(), reference_sheet=True, blank_rows=0),
        SheetSpec("07_Field_Rule", ("규칙 ID", "입력 그룹", "사용자 표시명", "정의", "적용 해석유형", "필수 수준", "활성 조건", "입력 주체", "입력 방식", "단위·좌표계", "선택지·범위", "반복 가능 여부", "연결 대상", "모름/해당 없음 처리", "차단 검증", "사용자 질문", "정상 예시", "오류 예시", "기존 검수 상태", "코드 근거", "구현 상태", "자동검증", "업무 검증", "제약·잔여사항"), rows=_field_rows(), reference_sheet=True, blank_rows=0),
        SheetSpec("08_Object_Case", ("표준항목 유형", "ID", "이름", "적용 대상", "정의·Case 축", "최소·기본 규칙", "반복·복제", "연결 대상", "차단·중복 규칙", "구현 상태", "업무 검증", "코드 근거"), rows=_object_case_rows(), reference_sheet=True, blank_rows=0),
        SheetSpec("09_검증근거", ("검증 구분", "테스트 파일", "테스트 함수 수", "주제", "주요 검증 범위", "보고 Backdata 사용", "증빙 수준", "한계"), rows=_verification_rows(), reference_sheet=True, blank_rows=0),
        SheetSpec("10_효과측정", ("KPI ID", "지표", "정의", "산식", "필요 데이터", "측정 주기", "비교 기준", "기대 효과", "현행 실적"), rows=_benefit_rows(), reference_sheet=True, blank_rows=0),
        SheetSpec("11_Gap_Roadmap", ("권장 순서", "Gap ID", "구분", "현행 상태", "영향도", "결정 담당", "선행자료", "필요 조치", "상태", "보고 구분", "근거"), rows=_gap_roadmap_rows(), reference_sheet=True, blank_rows=0),
        SheetSpec("12_Source_Index", ("원천 유형", "원천 항목", "경로·값", "산출 내용", "수집 방식", "사용 시트"), rows=_source_rows(), reference_sheet=True, blank_rows=0),
    )


def _source_errors() -> list[str]:
    errors = []
    business_units, product_groups, platforms = _product_counts()
    tests = _test_inventory()
    invariants = (
        (len(ANALYSIS_TYPE_OPTIONS), EXPECTED_TOTAL_ANALYSIS_TYPES, "analysis type catalog"),
        (len(ENABLED_ANALYSIS_TYPE_OPTIONS), EXPECTED_ENABLED_ANALYSIS_TYPES, "enabled analysis types"),
        (len(DISABLED_ANALYSIS_TYPE_OPTIONS), EXPECTED_DISABLED_ANALYSIS_TYPES, "disabled analysis types"),
        (len(_common_field_rows()), EXPECTED_FIELD_RULES, "field rules"),
        (len(_object_rows()), EXPECTED_OBJECT_RULES, "object rules"),
        (len(_case_rule_rows()), EXPECTED_CASE_RULES, "case rules"),
        (len(_gap_rows()), EXPECTED_GAPS, "gaps"),
        (business_units, EXPECTED_BUSINESS_UNITS, "business units"),
        (product_groups, EXPECTED_PRODUCT_GROUPS, "product groups"),
        (platforms, EXPECTED_PLATFORMS, "platforms"),
        (len(tests), EXPECTED_TEST_FILES, "test files"),
        (sum(row[1] for row in tests), EXPECTED_TEST_FUNCTIONS, "test functions"),
    )
    for actual, expected, label in invariants:
        if actual != expected:
            errors.append(f"{label}: expected {expected}, got {actual}")

    if tuple(ENABLED_ANALYSIS_TYPE_OPTIONS) != tuple(EXPECTED_ACTIVE_TYPES):
        errors.append(f"active analysis type order changed: {tuple(ENABLED_ANALYSIS_TYPE_OPTIONS)}")
    if _percent(len(ENABLED_ANALYSIS_TYPE_OPTIONS), len(ANALYSIS_TYPE_OPTIONS)) != "40.0%":
        errors.append("top analysis type implementation rate is not 40.0%")

    for row in _field_rows():
        if row[20] in {STATUS_APPLIED, STATUS_PARTIAL} and not row[19].strip():
            errors.append(f"field rule missing evidence: {row[0]}")
    for row in _scenario_rows():
        if row[8] in {STATUS_APPLIED, STATUS_PARTIAL} and (not row[9].strip() or not row[10].strip()):
            errors.append(f"scenario missing evidence: {row[0]}")
    for spec in _sheet_specs():
        for row_number, row in enumerate(spec.rows, 2):
            if len(row) != len(spec.headers):
                errors.append(
                    f"{spec.name} row {row_number}: expected {len(spec.headers)} columns, got {len(row)}"
                )
    return errors


def build_xlsx() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_xlsx(XLSX_PATH, _sheet_specs())


def check_output() -> list[str]:
    errors = _source_errors()
    try:
        with ZipFile(XLSX_PATH) as archive:
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            sheet_names = tuple(
                sheet.attrib["name"]
                for sheet in workbook.findall(f".//{{{NS_MAIN}}}sheet")
            )
            if sheet_names != EXPECTED_SHEETS:
                errors.append(f"unexpected sheet names: {sheet_names}")
            for index, spec in enumerate(_sheet_specs(), 1):
                root = ET.fromstring(archive.read(f"xl/worksheets/sheet{index}.xml"))
                rows = root.findall(f".//{{{NS_MAIN}}}sheetData/{{{NS_MAIN}}}row")
                expected_rows = len(spec.rows) + 1
                if len(rows) != expected_rows:
                    errors.append(f"{spec.name}: expected {expected_rows} XML rows, got {len(rows)}")
            summary = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            summary_text = " ".join(text.text or "" for text in summary.findall(f".//{{{NS_MAIN}}}t"))
            for phrase in ("40.0%", "4개 사업영역 / 25개 제품군 / 141개 Platform", "57개 파일 / 393개 함수", "저장소 증빙 0/4"):
                if phrase not in summary_text:
                    errors.append(f"summary missing phrase: {phrase}")
    except (OSError, KeyError, BadZipFile, ET.ParseError) as exc:
        errors.append(f"invalid workbook: {exc}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or verify the h7_v0 report backdata workbook.")
    parser.add_argument("--check", action="store_true", help="verify the existing workbook without rewriting it")
    args = parser.parse_args()
    if not args.check:
        source_errors = _source_errors()
        if source_errors:
            print("Source verification failed; workbook was not generated:")
            for error in source_errors:
                print(f"- {error}")
            return 1
        build_xlsx()
        print(f"Generated: {XLSX_PATH}")
    errors = check_output()
    if errors:
        print("Report backdata verification failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Report backdata verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
