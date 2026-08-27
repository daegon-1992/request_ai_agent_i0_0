"""Read-only analysis-type Master guidance for the h5 overview."""

from __future__ import annotations

from typing import Any


ANALYSIS_TYPE_MASTER: dict[str, str] = {
    "이슬맺힘": "결로 위험 위치와 온도·습도 조건을 비교해 개선 방향을 확인합니다.",
    "열교환기 유속 프로파일": "열교환기 면의 유속 분포를 확인해 균일도와 개선 필요 지점을 검토합니다.",
    "PCB발열": "PCB의 온도 분포와 발열 부품의 열 영향을 검토합니다.",
    "PDB": "PDB의 발열과 냉각 성능을 검토합니다.",
    "기류도달거리": "토출 기류가 목표 지점까지 도달하는 거리와 분포를 검토합니다.",
    "냉매누설": "냉매 누설 시 확산 경로와 농도 분포를 검토합니다.",
    "집진해석(먼지거동)": "먼지 입자의 이동과 포집 거동을 검토합니다.",
    "실사용 해석": "실제 사용 조건을 반영한 유동 및 열 성능을 검토합니다.",
    "기류 패턴": "온도 조건을 포함한 기류 경로와 공간 분포를 검토합니다.",
    "풍량": "제품의 풍량과 유동 분포를 검토합니다.",
    "다상유동": "서로 다른 상의 계면과 혼합·이동 거동을 검토합니다.",
}


def get_analysis_result_guidance(analysis_type: Any) -> dict[str, str]:
    """Return the selected Master guidance, or a retryable lookup failure."""

    selected = str(analysis_type or "").strip()
    guidance = ANALYSIS_TYPE_MASTER.get(selected)
    if not guidance:
        raise LookupError("선택한 해석유형의 결과 안내를 조회하지 못했습니다.")
    return {"analysis_type": selected, "guidance": guidance}
