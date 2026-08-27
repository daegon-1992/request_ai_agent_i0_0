"""Read-only, LLM-facing context for the current analysis request form.

The context is assembled from the existing Field Registry and active condition
Fieldset.  The small maps in this module only add UI location, meaning, and
examples that are not represented by the current schema; they do not decide
field activation, requirement, validation, or Request State mutation.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from .condition_fieldsets import CARD_TEMPLATES, HEAT_EXCHANGER_TYPES, get_active_condition_fields
from .constants import DROPDOWN_OPTION_DEFS
from .field_registry import get_field_registry, get_geometry_products_adapter
from .heat_exchanger_catalog import (
    HeatExchangerCatalogError,
    SPEC_FIELD_KEYS,
    catalog_field_allowed_values,
    load_heat_exchanger_catalog,
)


@dataclass(frozen=True)
class FormFieldContext:
    """Minimum meaning and UI location needed to explain one form field."""

    field_id: str
    screen: str
    section: str
    label: str
    description: str
    example: str
    required: bool
    unit: str
    system_generated: bool = False
    read_only: bool = False
    allowed_values: tuple[str, ...] = ()
    allow_custom_input: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.allowed_values:
            payload["allowed_values"] = list(self.allowed_values)
        else:
            payload.pop("allowed_values")
        if not self.allowed_values and not self.allow_custom_input:
            payload.pop("allow_custom_input")
        return payload


@dataclass(frozen=True)
class FormContext:
    """Immutable snapshot of fields visible in the current form."""

    form_id: str
    title: str
    fields: tuple[FormFieldContext, ...]
    analysis_type_context: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "form_id": self.form_id,
            "title": self.title,
            "fields": [field.to_dict() for field in self.fields],
            "analysis_type_context": deepcopy(dict(self.analysis_type_context)),
        }


ANALYSIS_TYPE_CONTEXT: dict[str, Any] = {
    "field_id": "request_context.analysis_type",
    "screen": "01 의뢰 대상·시작",
    "section": "request_context",
    "label": "해석유형",
    "description": (
        "해석을 통해 확인하려는 현상이나 결과에 맞는 해석유형을 선택합니다. "
        "사용자가 어떤 해석유형을 선택해야 할지 모르는 경우, "
        "확인하려는 문제·현상·목적을 바탕으로 Agent가 적합한 유형을 안내합니다. "
        "최종 해석유형은 사용자가 선택합니다."
    ),
    "options": {
        "풍량": {
            "availability": "available",
            "selectable": True,
            "description": "제품의 흡입·토출 또는 관심 위치에서의 풍량을 확인하는 해석입니다.",
            "what_can_be_checked": [
                "제품의 풍량",
                "형상 또는 운전조건 변경에 따른 풍량 변화",
                "여러 제품 또는 조건 간 풍량 차이",
            ],
            "suitable_when": [
                "풍량이 충분한지 확인하려는 경우",
                "풍량 부족 또는 변화가 문제인 경우",
                "설계 변경 전후의 풍량 차이를 비교하려는 경우",
            ],
            "example_request": "그릴 형상을 변경했을 때 기존 제품 대비 풍량이 얼마나 달라지는지 확인하고 싶습니다.",
            "distinction": "공기의 흐르는 모양보다 풍량 값과 그 차이가 주요 관심 대상이면 이 유형을 우선 검토합니다.",
        },
        "기류 패턴": {
            "availability": "available",
            "selectable": True,
            "description": "제품 내부 또는 외부에서 공기가 어떤 방향과 형태로 흐르는지 확인하는 해석입니다.",
            "what_can_be_checked": [
                "기류의 이동 방향",
                "유속 분포",
                "특정 영역으로의 기류 편중",
                "재순환 또는 정체되는 유동 영역",
                "형상 변경에 따른 유동 패턴 변화",
            ],
            "suitable_when": [
                "바람이 어느 방향으로 흐르는지 확인하려는 경우",
                "특정 방향으로 기류가 편중되는 원인을 확인하려는 경우",
                "형상 변경 전후의 유동 분포를 비교하려는 경우",
            ],
            "example_request": "토출 공기가 한쪽 방향으로 편중되는 원인과 그릴 변경 전후의 기류 패턴을 비교하고 싶습니다.",
            "distinction": "풍량의 크기보다 공기가 어디로 어떻게 흐르는지가 주요 관심 대상이면 이 유형을 우선 검토합니다.",
        },
        "이슬맺힘": {
            "availability": "available",
            "selectable": True,
            "description": "제품에서 이슬맺힘이 발생할 가능성이 있는 위치와 관련 원인을 검토하는 해석입니다.",
            "what_can_be_checked": [
                "이슬맺힘 발생 가능 영역",
                "온도·습도·유동 조건에 따른 이슬맺힘 영향",
                "제품 또는 조건 변경 전후의 이슬맺힘 차이",
            ],
            "suitable_when": [
                "제품 표면이나 특정 부위에 이슬맺힘이 발생하는 경우",
                "이슬맺힘 발생 원인을 검토하려는 경우",
                "개선안 적용 시 이슬맺힘이 줄어드는지 비교하려는 경우",
            ],
            "example_request": "토출부 주변에 반복적으로 이슬맺힘이 발생하는데 발생 위치와 개선안 적용 효과를 확인하고 싶습니다.",
            "distinction": "온도·습도와 관련된 이슬맺힘 현상 자체가 주요 문제이면 이 유형을 선택합니다.",
        },
        "열교환기 유속 프로파일": {
            "availability": "available",
            "selectable": True,
            "description": "열교환기를 통과하는 공기의 유속 분포를 확인하는 해석입니다.",
            "what_can_be_checked": [
                "열교환기 통과 유속 분포",
                "열교환기 영역별 유속 편차",
                "유동 편중 또는 저유속 영역",
                "형상 또는 운전조건 변화에 따른 유속 분포 차이",
            ],
            "suitable_when": [
                "열교환기 전면의 유속이 균일한지 확인하려는 경우",
                "열교환기 특정 영역의 유속이 낮거나 높은지 확인하려는 경우",
                "설계 변경에 따른 열교환기 유속 분포를 비교하려는 경우",
            ],
            "example_request": "열교환기 전면에서 유속이 한쪽으로 편중되는지 확인하고 기존안과 변경안을 비교하고 싶습니다.",
            "distinction": "제품 전체의 기류보다 열교환기를 통과하는 유속 분포가 주요 관심 대상이면 이 유형을 선택합니다.",
        },
        "기류도달거리": {
            "availability": "planned",
            "selectable": False,
            "description": "토출된 기류가 공간에서 어느 정도까지 도달하는지를 검토하기 위한 개발 예정 해석유형입니다.",
            "agent_behavior": (
                "현재 지원하지 않는 해석유형임을 사용자에게 안내합니다. "
                "현재 지원되는 다른 유형으로 임의 변환하지 않습니다."
            ),
        },
        "PDB": {
            "availability": "planned",
            "selectable": False,
            "description": "세부 업무 정의가 아직 Context에 등록되지 않은 개발 예정 해석유형입니다.",
            "agent_behavior": (
                "PDB의 의미를 임의로 해석하거나 설명하지 않습니다. "
                "현재 지원하지 않는 해석유형임을 안내합니다."
            ),
        },
        "실사용 해석": {
            "availability": "planned",
            "selectable": False,
            "description": "실사용 조건을 고려하는 해석으로 개발 예정인 유형입니다. 세부 적용 범위는 추후 정의합니다.",
            "agent_behavior": "현재 지원하지 않는 해석유형임을 안내합니다.",
        },
        "집진해석(먼지거동)": {
            "availability": "planned",
            "selectable": False,
            "description": "먼지 또는 입자의 이동과 집진 관련 거동을 확인하기 위한 개발 예정 해석유형입니다.",
            "agent_behavior": "현재 지원하지 않는 해석유형임을 안내합니다.",
        },
        "PCB발열": {
            "availability": "planned",
            "selectable": False,
            "description": "PCB 발열과 관련된 온도 및 냉각 상태를 검토하기 위한 개발 예정 해석유형입니다.",
            "agent_behavior": "현재 지원하지 않는 해석유형임을 안내합니다.",
        },
        "다상유동": {
            "availability": "planned",
            "selectable": False,
            "description": "여러 상이 함께 존재하는 유동 현상을 검토하기 위한 개발 예정 해석유형입니다.",
            "agent_behavior": "현재 지원하지 않는 해석유형임을 안내합니다.",
        },
    },
}


# These are the current user-facing fields in SCREEN-01 and SCREEN-02.  Internal
# Registry rows (lock/snapshot/operation fields) are intentionally not presented
# to the LLM as form inputs.
_GENERAL_UI_BINDINGS: tuple[tuple[str, str, str], ...] = (
    ("request_context.division", "01 의뢰 대상·시작", "해석 대상 제품 선택"),
    ("request_context.product_lineup", "01 의뢰 대상·시작", "해석 대상 제품 선택"),
    ("request_context.platform", "01 의뢰 대상·시작", "해석 대상 제품 선택"),
    ("request_context.chassis", "01 의뢰 대상·시작", "해석 대상 제품 선택"),
    ("request_context.analysis_type", "01 의뢰 대상·시작", "해석 대상 제품 선택"),
    ("basic_info.division", "02 요청 내용", "의뢰자 정보"),
    ("basic_info.department", "02 요청 내용", "의뢰자 정보"),
    ("basic_info.requester_name", "02 요청 내용", "의뢰자 정보"),
    ("basic_info.requester_role", "02 요청 내용", "의뢰자 정보"),
    ("analysis_overview.project_name", "02 요청 내용", "의뢰 기본 정보"),
    ("analysis_overview.development_grade", "02 요청 내용", "의뢰 기본 정보"),
    ("analysis_overview.npi_stage", "02 요청 내용", "의뢰 기본 정보"),
    ("analysis_overview.model_suffix", "02 요청 내용", "의뢰 기본 정보"),
    ("analysis_overview.request_date", "02 요청 내용", "의뢰 기본 정보"),
    ("analysis_overview.desired_completion_date", "02 요청 내용", "의뢰 기본 정보"),
    ("analysis_overview.request_description", "02 요청 내용", "해석 요청 내용"),
    ("analysis_overview.additional_result_request", "02 요청 내용", "해석 요청 내용"),
)


_DESCRIPTIONS = {
    "request_context.division": "해석 대상 제품의 Division입니다. 요청자의 소속이 아니라 제품을 기준으로 선택합니다.",
    "request_context.product_lineup": "선택한 Division의 Product Line-up입니다.",
    "request_context.platform": "선택한 Product Line-up의 Platform입니다. RAC와 Air Care에서는 Product Line-up과 같은 값으로 자동 설정됩니다.",
    "request_context.chassis": "선택한 Platform의 Chassis입니다. Chassis가 없는 분류 경로는 null로 자동 설정됩니다.",
    "request_context.analysis_type": ANALYSIS_TYPE_CONTEXT["description"],
    "basic_info.division": "해석을 의뢰하는 요청자의 소속 사업부입니다.",
    "basic_info.department": "해석을 의뢰하는 요청자의 소속 부서입니다.",
    "basic_info.requester_name": "해석 의뢰 내용과 결과를 협의할 요청자 이름입니다.",
    "basic_info.requester_role": "해석을 의뢰하는 요청자의 직급입니다.",
    "analysis_overview.project_name": "의뢰와 연결할 PMS 프로젝트명을 입력합니다.",
    "analysis_overview.development_grade": "제품 개발 과제의 등급입니다.",
    "analysis_overview.npi_stage": "현재 제품 개발이 위치한 NPI 단계입니다.",
    "analysis_overview.model_suffix": "해석 대상 제품의 모델명 또는 Model Suffix입니다.",
    "analysis_overview.request_date": "해석 의뢰를 요청한 날짜입니다.",
    "analysis_overview.desired_completion_date": "해석 결과를 받기 원하는 완료 희망일입니다.",
    "analysis_overview.request_description": "이번 해석을 의뢰하게 된 문제, 현상, 설계 변경 또는 검토 배경을 작성합니다.",
    "analysis_overview.additional_result_request": "이번 해석 결과를 통해 확인하거나 비교하고 싶은 내용을 작성합니다.",
    "geometry.base_product.drawing_no": "해석에 사용할 Base 제품의 총 조립 형상을 식별하는 도면번호입니다. 형상 또는 조립 상태가 다른 해석 대상은 각각 다른 도면번호를 사용하며, 필요 시 임시 도면번호를 사용할 수 있습니다.",
    "geometry.comparison_products[].drawing_no": "해석에 사용할 비교 제품의 총 조립 형상을 식별하는 도면번호입니다. 형상 또는 조립 상태가 다른 해석 대상은 각각 다른 도면번호를 사용하며, 필요 시 임시 도면번호를 사용할 수 있습니다.",
    "geometry.comparison_products[].difference_from_base": "비교 제품의 총 조립 형상에 이미 반영된 Base 제품 대비 형상·조립 상태 차이를 작성합니다.",
    "material_type": "해석 영역 안에서 흐르거나 열을 전달하는 작동유체입니다.",
    "fan_rpm": "해당 Fan의 회전수 조건입니다. 해당 운전 조건에서 적용할 회전수를 입력합니다.",
    "name": "Case에서 열교환기 사양을 구분하기 위해 시스템이 자동 생성하는 이름입니다.",
    "tube_diameter": "Fin&Tube 열교환기의 관 직경(Pi) 또는 Micro-Channel의 채널 폭(Width)입니다.",
    "fin_type": "열교환기에 적용된 Fin 형상 유형입니다.",
    "row_count": "공기 흐름 방향으로 배치된 열교환기 관 또는 채널의 열 수입니다.",
    "fpi": "Fin&Tube의 인치당 Fin 수(FPI) 또는 Micro-Channel의 미터당 Fin 수(FPDM)입니다.",
    "heat_exchanger_temp": "열교환기를 지난 뒤 취출되는 공기의 온도 조건입니다.",
    "heat_exchanger_rh": "열교환기를 지난 뒤 취출되는 공기의 상대습도 조건입니다.",
    "room_temp": "제품이 설치된 공간의 공기 온도 조건입니다.",
    "room_rh": "제품이 설치된 공간 공기의 상대습도 조건입니다.",
}


_EXAMPLES = {
    "request_context.division": "예: RAC",
    "request_context.product_lineup": "예: Wall Mounted",
    "request_context.platform": "예: Wall Mounted",
    "request_context.chassis": "예: SK 또는 null",
    "request_context.analysis_type": "예: 이슬맺힘",
    "basic_info.division": "예: RAC",
    "basic_info.department": "예: 개발1팀",
    "basic_info.requester_name": "예: 홍길동",
    "basic_info.requester_role": "예: 책임연구원",
    "analysis_overview.project_name": "예: 26년향 하이드로타워 대용량 가습공청기",
    "analysis_overview.development_grade": "예: A",
    "analysis_overview.npi_stage": "예: DV",
    "analysis_overview.model_suffix": "",
    "analysis_overview.request_date": "예: 2026-08-11",
    "analysis_overview.desired_completion_date": "예: 2026-08-25",
    "analysis_overview.request_description": "예: 설계 변경 후 성능 저하 현상이 발생하여 원인 검토가 필요합니다.",
    "analysis_overview.additional_result_request": "예: 기존안과 변경안의 결과 차이와 개선 효과를 확인하고 싶습니다.",
    "geometry.base_product.drawing_no": "예: AJT000123 또는 TEMP-BASE-01",
    "geometry.comparison_products[].drawing_no": "예: AJT000234 또는 TEMP-COMP-01",
    "geometry.comparison_products[].difference_from_base": "예: 베인 각도 30° 적용, Fan 위치 상향 20 mm",
    "fan_rpm": "예: 780",
    "name": "예: 사양 1",
    "tube_diameter": "예: 7.0",
    "fin_type": "예: Slit",
    "row_count": "예: 2",
    "fpi": "예: 18",
    "heat_exchanger_temp": "예: 12°C",
    "heat_exchanger_rh": "예: 95%",
}


_ANALYSIS_TYPE_FIELD_EXAMPLES = {
    "풍량": {
        "analysis_overview.request_description": "그릴 형상 변경 후 풍량 저하가 우려되어 검토가 필요합니다.",
        "analysis_overview.additional_result_request": "기존 제품과 변경 제품의 풍량 차이를 확인하고 싶습니다.",
    },
    "기류 패턴": {
        "analysis_overview.request_description": "토출 기류가 한쪽 방향으로 편중되어 유동 상태 확인이 필요합니다.",
        "analysis_overview.additional_result_request": "기류 분포와 편중 영역을 기존안과 변경안에서 비교하고 싶습니다.",
    },
    "이슬맺힘": {
        "analysis_overview.request_description": "토출부 주변에 이슬맺힘이 반복되어 발생 현상 검토가 필요합니다.",
        "analysis_overview.additional_result_request": "이슬맺힘 발생 영역과 개선안별 차이를 확인하고 싶습니다.",
    },
    "열교환기 유속 프로파일": {
        "analysis_overview.request_description": "열교환기 전면의 유속 편차가 우려되어 분포 확인이 필요합니다.",
        "analysis_overview.additional_result_request": "열교환기 전면의 위치별 유속 분포와 편차를 확인하고 싶습니다.",
    },
}


_GUIDE_EXAMPLE_BINDINGS = {
    "material_type": ("conditions", "작동유체"),
    "room_temp": ("conditions", "Room 온도"),
    "room_rh": ("conditions", "Room 상대습도"),
}


_HELP_QUESTIONS = {
    "material_type": "작동유체는 뭐야?",
    "room_rh": "상대습도는 뭐야?",
}


def _existing_guidance() -> tuple[Mapping[str, Any], Any]:
    """Load the current chat guidance lazily without changing chat flow."""

    from .app import STAGE_WRITING_GUIDES, _field_help_answer

    return STAGE_WRITING_GUIDES, _field_help_answer


def _existing_example(field_id: str, field_key: str = "") -> str:
    binding = _GUIDE_EXAMPLE_BINDINGS.get(field_id) or _GUIDE_EXAMPLE_BINDINGS.get(field_key)
    if not binding:
        return ""
    guides, _field_help = _existing_guidance()
    stage_key, wanted_label = binding
    guide = guides.get(stage_key, {}) if isinstance(guides, Mapping) else {}
    examples = guide.get("examples", []) if isinstance(guide, Mapping) else []
    for label, example in examples:
        if str(label).strip() == wanted_label:
            return str(example).strip()
    return ""


def _existing_description(field_id: str, field_key: str = "") -> str:
    question = _HELP_QUESTIONS.get(field_id) or _HELP_QUESTIONS.get(field_key)
    if not question:
        return ""
    _guides, field_help_answer = _existing_guidance()
    return str(field_help_answer(question) or "").strip()


def _meaning(field_id: str, field_key: str = "") -> str:
    return _existing_description(field_id, field_key) or _DESCRIPTIONS.get(field_id) or _DESCRIPTIONS.get(field_key, "")


def _example(field_id: str, field_key: str = "") -> str:
    return _existing_example(field_id, field_key) or _EXAMPLES.get(field_id) or _EXAMPLES.get(field_key, "")


def _choice_metadata(field_id: str, field_key: str = "") -> tuple[tuple[str, ...], bool]:
    option_path = field_id if field_id in DROPDOWN_OPTION_DEFS else f"conditions.{field_key}"
    dropdown_options = tuple(str(value) for value in DROPDOWN_OPTION_DEFS.get(option_path, ()))
    allow_custom_input = "직접 입력" in dropdown_options
    allowed_values = tuple(value for value in dropdown_options if value and value != "직접 입력")
    return allowed_values, allow_custom_input


_CONDITION_SECTION_BY_FIELD = {
    field_key: str(template["label"])
    for template in CARD_TEMPLATES
    for field_key, _label, _unit in template["fields"]
}


_HEAT_EXCHANGER_FIELD_CONTEXT = {
    "Fin&Tube": {
        "tube_diameter": {
            "label": "관 직경(Pi)",
            "description": "Fin&Tube 열교환기의 관 직경(Pi)입니다.",
            "unit": "mm",
            "example": "예: 7.0",
        },
        "fin_type": {
            "label": "Fin type",
            "description": "Fin&Tube 열교환기의 Fin type입니다.",
            "unit": "",
            "example": "예: Slit",
        },
        "row_count": {
            "label": "열 수",
            "description": "공기 흐름 방향으로 배치된 Fin&Tube 열교환기 관의 열 수입니다.",
            "unit": "",
            "example": "예: 2",
        },
        "fpi": {
            "label": "FPI",
            "description": "Fin&Tube의 인치당 Fin 수(FPI)입니다.",
            "unit": "",
            "example": "예: 18",
        },
    },
    "Micro-Channel": {
        "tube_diameter": {
            "label": "채널 폭(Width)",
            "description": "Micro-Channel 열교환기의 채널 폭(Width)입니다.",
            "unit": "mm",
            "example": "",
        },
        "fin_type": {
            "label": "Flat Fin type",
            "description": "Micro-Channel 열교환기의 Flat Fin type입니다.",
            "unit": "",
            "example": "예: Flat",
        },
        "row_count": {
            "label": "열 수",
            "description": "공기 흐름 방향으로 배치된 Micro-Channel 열교환기 채널의 열 수입니다.",
            "unit": "",
            "example": "예: 2",
        },
        "fpi": {
            "label": "FPDM",
            "description": "Micro-Channel의 미터당 Fin 수(FPDM)입니다.",
            "unit": "",
            "example": "",
        },
    },
}


def _heat_exchanger_cards_by_id(state: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    conditions = state.get("conditions") if isinstance(state, Mapping) else None
    cards = conditions.get("condition_sets") if isinstance(conditions, Mapping) else None
    result: dict[str, Mapping[str, Any]] = {}
    for card in cards if isinstance(cards, list) else []:
        if not isinstance(card, Mapping) or card.get("type") != "heat_exchanger":
            continue
        card_id = card.get("id")
        heat_exchanger_type = card.get("heat_exchanger_type")
        if isinstance(card_id, str) and heat_exchanger_type in _HEAT_EXCHANGER_FIELD_CONTEXT:
            result[card_id] = card
    return result


def _selected_analysis_type(state: Mapping[str, Any] | None) -> str:
    request_context = state.get("request_context", {}) if isinstance(state, Mapping) else {}
    if not isinstance(request_context, Mapping):
        return ""
    value = request_context.get("analysis_type", "")
    if isinstance(value, Mapping):
        value = value.get("value", "")
    return str(value or "").strip()


def _analysis_type_semantic_context(state: Mapping[str, Any] | None) -> dict[str, Any]:
    context = deepcopy(ANALYSIS_TYPE_CONTEXT)
    options = context["options"]
    selected_type = _selected_analysis_type(state)
    selected_option = options.get(selected_type)
    selected_supported = bool(
        isinstance(selected_option, Mapping)
        and selected_option.get("availability") == "available"
        and selected_option.get("selectable") is True
    )
    context["selectable_options"] = [
        name
        for name, option in options.items()
        if option.get("availability") == "available" and option.get("selectable") is True
    ]
    context["selected_type"] = selected_type
    context["selected_option"] = deepcopy(selected_option) if isinstance(selected_option, Mapping) else None
    context["selected_type_supported"] = selected_supported
    return context


def _general_fields(
    registry: Mapping[str, Any],
    analysis_type_context: Mapping[str, Any],
) -> list[FormFieldContext]:
    fields: list[FormFieldContext] = []
    selected_type = str(analysis_type_context.get("selected_type") or "").strip()
    selected_examples = (
        _ANALYSIS_TYPE_FIELD_EXAMPLES.get(selected_type, {})
        if analysis_type_context.get("selected_type_supported") is True
        else {}
    )
    for field_id, screen, section in _GENERAL_UI_BINDINGS:
        dto = registry.get(field_id)
        if dto is None:
            continue
        example = _example(field_id)
        if field_id in selected_examples:
            example = f"예: {selected_examples[field_id]}"
        allowed_values, allow_custom_input = _choice_metadata(field_id)
        fields.append(
            FormFieldContext(
                field_id=field_id,
                screen=screen,
                section=section,
                label=dto.label,
                description=_meaning(field_id),
                example=example,
                required=dto.required,
                unit=dto.unit,
                allowed_values=allowed_values,
                allow_custom_input=allow_custom_input,
            )
        )
    return fields


def _geometry_fields() -> list[FormFieldContext]:
    adapter = get_geometry_products_adapter()
    base_drawing, comparison_drawing = adapter.canonical_paths
    definitions = (
        (base_drawing, "총조립도 도면번호 (NPDM MCAD)"),
        (comparison_drawing, "총조립도 도면번호 (NPDM MCAD)"),
        ("geometry.comparison_products[].difference_from_base", "Base 대비 변경점"),
    )
    return [
        FormFieldContext(
            field_id=field_id,
            screen="03 해석 제품",
            section="총 조립 형상",
            label=label,
            description=_meaning(field_id),
            example=_example(field_id),
            required=True,
            unit="",
        )
        for field_id, label in definitions
    ]


def _system_generated_condition_ids(state: Mapping[str, Any] | None) -> set[str]:
    generated: set[str] = set()
    for field in get_active_condition_fields(state or {}):
        values = field.get("values", [])
        if values and all(
            isinstance(value, Mapping) and value.get("source") == "system"
            for value in values
        ):
            generated.add(f"conditions.{field['key']}")
    return generated


def _condition_fields(
    registry_rows: tuple[Any, ...],
    state: Mapping[str, Any] | None,
) -> list[FormFieldContext]:
    fields: list[FormFieldContext] = []
    fieldset_metadata = {
        f"conditions.{field['key']}": field
        for field in get_active_condition_fields(state or {})
    }
    system_generated_ids = _system_generated_condition_ids(state)
    heat_exchanger_cards = _heat_exchanger_cards_by_id(state)
    try:
        catalog_rows = load_heat_exchanger_catalog() if heat_exchanger_cards else []
    except HeatExchangerCatalogError:
        catalog_rows = []
    for dto in registry_rows:
        if not dto.field_id.startswith("conditions.") or not dto.active:
            continue
        field_key = dto.field_key
        system_generated = dto.field_id in system_generated_ids
        allowed_values, allow_custom_input = _choice_metadata(dto.field_id, field_key)
        field_metadata = fieldset_metadata.get(dto.field_id, {})
        metadata_allowed_values = field_metadata.get("allowed_values")
        if isinstance(metadata_allowed_values, (list, tuple)):
            allowed_values = tuple(str(value) for value in metadata_allowed_values if str(value))
        if isinstance(field_metadata.get("allow_custom_input"), bool):
            allow_custom_input = field_metadata["allow_custom_input"]
        heat_exchanger_card = heat_exchanger_cards.get(dto.card_id, {})
        heat_exchanger_type = str(heat_exchanger_card.get("heat_exchanger_type", ""))
        heat_exchanger_context = _HEAT_EXCHANGER_FIELD_CONTEXT.get(
            heat_exchanger_type, {}
        ).get(field_key, {})
        micro_channel_fin = (
            heat_exchanger_type == HEAT_EXCHANGER_TYPES[1]
            and field_key == "fin_type"
        )
        if field_key in SPEC_FIELD_KEYS and heat_exchanger_card:
            card_fields = heat_exchanger_card.get("fields")
            spec = card_fields if isinstance(card_fields, Mapping) else {}
            allowed_values = catalog_field_allowed_values(
                spec,
                field_key,
                heat_exchanger_type,
                catalog_rows,
            )
            allow_custom_input = not micro_channel_fin
        fields.append(
            FormFieldContext(
                field_id=dto.field_id,
                screen="04 해석 조건",
                section=_CONDITION_SECTION_BY_FIELD.get(field_key, "해석 조건"),
                label=str(heat_exchanger_context.get("label", dto.label)),
                description=str(
                    heat_exchanger_context.get("description", _meaning(dto.field_id, field_key))
                ),
                example=str(heat_exchanger_context.get("example", _example(dto.field_id, field_key))),
                required=dto.required,
                unit=str(heat_exchanger_context.get("unit", dto.unit)),
                system_generated=system_generated,
                read_only=system_generated or micro_channel_fin,
                allowed_values=allowed_values,
                allow_custom_input=allow_custom_input,
            )
        )
    return fields


def build_form_context(state: Mapping[str, Any] | None = None) -> FormContext:
    """Build a side-effect-free Form Context for the current Request State.

    Active and required condition fields are always taken from a fresh Field
    Registry snapshot, so this function does not duplicate Fieldset or Validator
    rules.
    """

    source = state or {}
    analysis_type_context = _analysis_type_semantic_context(source)
    registry_rows = get_field_registry(source)
    registry = {field.field_id: field for field in registry_rows}
    condition_fields = (
        _condition_fields(registry_rows, source)
        if analysis_type_context["selected_type_supported"] is True
        else []
    )
    fields = (
        *_general_fields(registry, analysis_type_context),
        *_geometry_fields(),
        *condition_fields,
    )
    return FormContext(
        form_id="analysis_request",
        title="해석의뢰서",
        fields=fields,
        analysis_type_context=analysis_type_context,
    )
