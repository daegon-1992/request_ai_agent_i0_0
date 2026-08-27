"""Constants for the request assistant state model."""

from __future__ import annotations

APP_VERSION = "i0_0-baseline-20260825"
STATE_SCHEMA_VERSION = "request_state_v2"
DEFAULT_RAG_SCOPE = "LG CFD Reports 2025 해석보고서"
DEFAULT_REQUEST_NO_PREFIX = "CFD"
DEMO_REQUEST_NO_PREFIX = "DEMO-CFD"
DEMO_ANALYSIS_TYPE_NAME = "데모용"
DEMO_ANALYSIS_TYPE_CODE = "DEMO_FLUENT_242R2"
DEMO_CONDITION_MODE = "demo_fluent_242r2"

SUBMISSION_CONTACT = {
    "name": "홍승도 책임",
    "email": "sedo.hong@lge.com",
}

MAX_FANS_PER_OPERATING_CONDITION = 10
OPERATING_FAN_COUNT_LIMIT_MESSAGE = "한 운전 조건에는 Fan을 최대 10개까지 설정할 수 있습니다."

SECTION_METADATA = "metadata"
SECTION_REQUEST_CONTEXT = "request_context"
SECTION_BASIC_INFO = "basic_info"
SECTION_ANALYSIS_OVERVIEW = "analysis_overview"
SECTION_GEOMETRY = "geometry"
SECTION_CONDITIONS = "conditions"
SECTION_CASE_MATRIX = "case_matrix"
SECTION_REVIEW = "review"
SECTION_LEGACY_INTERNAL = "legacy_internal"

STATE_SECTION_KEYS = (
    SECTION_METADATA,
    SECTION_REQUEST_CONTEXT,
    SECTION_BASIC_INFO,
    SECTION_ANALYSIS_OVERVIEW,
    SECTION_GEOMETRY,
    SECTION_CONDITIONS,
    SECTION_CASE_MATRIX,
    SECTION_REVIEW,
    SECTION_LEGACY_INTERNAL,
)

FIELD_STATUS_PROVIDED = "provided"
FIELD_STATUS_MISSING = "missing"
FIELD_STATUS_UNKNOWN = "unknown"
FIELD_STATUS_NONE = "none"
FIELD_STATUS_SKIPPED = "skipped"

FIELD_STATUSES = (
    FIELD_STATUS_PROVIDED,
    FIELD_STATUS_MISSING,
    FIELD_STATUS_UNKNOWN,
    FIELD_STATUS_NONE,
    FIELD_STATUS_SKIPPED,
)

NON_PROVIDED_STATUSES = (
    FIELD_STATUS_MISSING,
    FIELD_STATUS_UNKNOWN,
    FIELD_STATUS_NONE,
    FIELD_STATUS_SKIPPED,
)

VALUE_SOURCE_USER = "user"
VALUE_SOURCE_SYSTEM = "system"
VALUE_SOURCE_LEGACY_INTERNAL = "legacy_internal"

UNKNOWN_TOKENS = {
    "모름",
    "몰라",
    "알수없음",
    "확인필요",
    "확인 필요",
    "unknown",
    "unsure",
    "tbd",
    "n/a?",
}

NONE_TOKENS = {
    "없음",
    "해당없음",
    "해당 없음",
    "무",
    "none",
    "no",
    "not applicable",
    "n/a",
    "na",
}

SKIPPED_TOKENS = {
    "건너뜀",
    "스킵",
    "skip",
    "skipped",
    "pass",
    "생략",
}

BASIC_INFO_FIELD_DEFS = (
    {"key": "request_no", "label": "의뢰 번호", "required": False, "legacy_key": "reqNo"},
    {"key": "division", "label": "사업부", "required": True},
    {"key": "department", "label": "부서", "required": True, "legacy_key": "deptName"},
    {"key": "requester_name", "label": "요청자", "required": True, "legacy_key": "requesterName"},
    {"key": "requester_role", "label": "직급", "required": True, "legacy_key": "requesterRole"},
)

REQUEST_CONTEXT_FIELD_DEFS = (
    {"key": "taxonomy_id", "label": "분류 ID", "required": False},
    {"key": "taxonomy_version", "label": "분류 버전", "required": False},
    {"key": "division", "label": "Division", "required": False},
    {"key": "product_lineup", "label": "Product Line-up", "required": False},
    {"key": "platform", "label": "Platform", "required": False},
    {"key": "chassis", "label": "Chassis", "required": False},
    {"key": "display_path", "label": "제품 분류 경로", "required": False},
    {"key": "analysis_type", "label": "해석 유형", "required": False},
    {"key": "operation_mode", "label": "운전 모드", "required": False},
    {"key": "context_locked", "label": "Context 확정 여부", "required": False, "value_type": "boolean"},
    {"key": "condition_fieldset_key", "label": "조건 fieldset key", "required": False},
    {"key": "condition_fieldset_snapshot", "label": "조건 fieldset snapshot", "required": False, "value_type": "list"},
)

ANALYSIS_OVERVIEW_FIELD_DEFS = (
    {"key": "project_name", "label": "프로젝트명(PMS)", "required": True},
    {"key": "development_grade", "label": "개발 등급", "required": True},
    {"key": "npi_stage", "label": "NPI 단계", "required": True},
    {"key": "model_suffix", "label": "모델명(Model Suffix)", "required": True},
    {"key": "request_date", "label": "의뢰 요청일", "required": True, "value_type": "date"},
    {"key": "desired_completion_date", "label": "희망 완료일", "required": True, "value_type": "date"},
    {"key": "request_description", "label": "해석을 요청하게 된 배경", "required": True, "track_progress": True},
    {"key": "decision_use", "label": "결과 활용 목적", "required": False},
    {"key": "additional_result_request", "label": "해석으로 확인하고 싶은 내용", "required": True, "track_progress": True},
)

GEOMETRY_INPUT_KEYS = (
    "base_product",
    "comparison_products",
    "boundary_bindings",
    "axis",
)

CONDITION_FIELD_DEFS = (
    {
        "key": "material_type",
        "label": "작동유체",
        "required": True,
        "binding": "condition-linked",
    },
    {
        "key": "fan_rpm",
        "label": "팬 회전수(RPM)",
        "required": False,
        "unit": "rpm",
        "binding": "condition-linked",
        "legacy_key": "fanRpm",
    },
    {
        "key": "heat_exchanger_spec",
        "label": "열교환기 사양",
        "required": False,
        "binding": "condition-linked",
        "legacy_key": "heatExchangerSpec",
    },
    {
        "key": "pressure",
        "label": "압력조건",
        "required": False,
        "binding": "condition-linked",
    },
    {
        "key": "room_temp",
        "label": "공간 온도",
        "required": False,
        "unit": "degC",
        "binding": "condition-linked",
        "legacy_key": "roomTemp",
    },
    {
        "key": "room_rh",
        "label": "공간 상대습도",
        "required": False,
        "unit": "%",
        "binding": "condition-linked",
        "legacy_key": "roomRH",
    },
    {
        "key": "heat_exchanger_temp",
        "label": "취출 온도",
        "required": False,
        "unit": "degC",
        "binding": "condition-linked",
        "legacy_key": "heatExchangerTemp",
    },
    {
        "key": "heat_exchanger_rh",
        "label": "취출 상대습도",
        "required": False,
        "unit": "%",
        "binding": "condition-linked",
        "legacy_key": "heatExchangerRH",
    },
    {
        "key": "installation_space",
        "label": "설치 환경",
        "required": False,
        "binding": "condition-linked",
        "legacy_key": "installationSpace",
    },
    {
        "key": "installation_location",
        "label": "제품 설치 위치",
        "required": False,
        "binding": "condition-linked",
        "legacy_key": "installationLocation",
    },
    {
        "key": "postprocess_air_speed",
        "label": "기류 도달 기준 거리",
        "required": False,
        "binding": "condition-linked",
        "legacy_key": "postprocessAirSpeed",
    },
    {
        "key": "postprocess",
        "label": "결과 확인 항목",
        "required": False,
        "binding": "condition-linked",
        "legacy_key": "postprocess",
    },
    {
        "key": "vane_or_louver",
        "label": "Vane/Louver",
        "required": False,
        "value_type": "checkbox",
        "binding": "unclassified-boundary",
        "legacy_key": "hasVane",
    },
    {
        "key": "filter_state",
        "label": "필터 유무",
        "required": False,
        "value_type": "checkbox",
        "binding": "unclassified-boundary",
    },
)

ANALYSIS_TYPE_OPTIONS = (
    "풍량",
    "기류 패턴",
    "이슬맺힘",
    "열교환기 유속 프로파일",
    "기류도달거리",
    "PDB",
    "실사용 해석",
    "집진해석(먼지거동)",
    "PCB발열",
    "다상유동",
)

DISABLED_ANALYSIS_TYPE_OPTIONS = (
    "기류도달거리",
    "PDB",
    "실사용 해석",
    "집진해석(먼지거동)",
    "PCB발열",
    "다상유동",
)

ENABLED_ANALYSIS_TYPE_OPTIONS = tuple(
    option for option in ANALYSIS_TYPE_OPTIONS if option not in DISABLED_ANALYSIS_TYPE_OPTIONS
)

ANALYSIS_TYPE_ALIASES = {
    "유동": "기류 패턴",
    "airflow": "기류 패턴",
    "flow": "기류 패턴",
    "air volume": "풍량",
    "airvolume": "풍량",
    "이슬 맺힘": "이슬맺힘",
    "condensation": "이슬맺힘",
    "dew": "이슬맺힘",
}

DROPDOWN_OPTION_DEFS = {
    "basic_info.division": ["SAC", "RAC", "Aircare", "Chiller", "연구소", "직접 입력"],
    "basic_info.requester_role": ["책임연구원", "선임연구원", "연구원", "직접 입력"],
    "analysis_overview.project_name": ["미정", "직접 입력"],
    "analysis_overview.development_grade": ["A", "B", "Ca", "Cb", "Cc", "선행", "미정", "직접 입력"],
    "analysis_overview.npi_stage": ["CP", "DV", "PV", "MP", "미정", "직접 입력"],
    "analysis_overview.model_suffix": ["미정", "직접 입력"],
    "conditions.material_type": ["", "Air", "직접 입력"],
    "conditions.working_fluid": ["air", "water"],
    "conditions.outlet_condition": ["pressure outlet"],
    "conditions.heat_exchanger_spec": ["", "P7.0 2R 18FPISlit(Half)", "직접 입력"],
}

REMOVED_PUBLIC_FIELD_PATHS = (
    "analysis_overview.representative_model",
)

LEGACY_INTERNAL_FIELD_DEFS = (
    {
        "key": "conditionPerPart",
        "label": "Legacy CAD별 조건 수",
        "derived": True,
    },
    {
        "key": "sameCondition",
        "label": "Legacy CAD 간 조건 동일 여부",
        "derived": True,
    },
)
