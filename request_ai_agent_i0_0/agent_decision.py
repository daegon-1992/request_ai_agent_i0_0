"""Single semantic LLM decision for the Main Agent Chat."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Mapping, Sequence

from .agent_write_contract import (
    normalize_context_confirmation_operation,
    normalize_instance_write_operation,
    normalize_structural_write_operation,
)
from .condition_fieldsets import CARD_TEMPLATES
from .deferred_input import normalize_deferred_fact
from .field_registry import get_field_registry
from .form_context import build_form_context
from .llm_client import azure_chat_completion
from .state import field_value


LLM_FAILURE_MESSAGE = "LLM이 정상 작동하지 않습니다."
ALLOWED_AGENT_ACTIONS = frozenset({"answer", "propose", "clarify"})

_SYSTEM_INSTRUCTION = """당신은 CAE 해석의뢰 Main Agent다.
반드시 JSON object 하나만 출력하고 action은 answer, propose, clarify 중 하나만 사용한다.
현재 Request의 사실과 현재 값은 Agent Context만 기준으로 하며 입력되지 않은 값은 추측하지 않는다.
일반 CAE 개념은 모델 지식으로 답할 수 있지만 사내 기준·보고서·SOP 근거는 제공되지 않았다면 만들지 않는다.
Form Field 의미는 form_context, 형상/운전/사양의 대상은 instance_context를 사용한다.
선택한 해석유형에서 비활성화되어 form_context와 Write Contract에 없는 조건 Field는 입력을 요구하거나 값 작성을 제안하지 않는다.
현재 발화의 주된 목적은 current_message, recent_turns, 현재 Request State, active_question을 함께 보고 의미적으로 판단한다.
현재 작성 Field의 값이 아니라 현재 값 확인, 기준정보 조회, 입력 항목 설명, 일반적인 역질문이면 action=answer, resume_workflow=false로 응답한다.
이 경우 기존 active Field는 유지하며 작성 질문을 reply에 다시 붙이지 않는다.
사용자가 작성 Workflow를 계속하거나 다시 질문해 달라는 의미를 명시한 경우에만 action=answer, resume_workflow=true로 응답한다.
resume_workflow 판단에 특정 표현, 문장 길이, 물음표 또는 키워드 목록을 사용하지 않는다.
현재 값을 묻는 질문에는 해당 값에 직접 답한다.
사용자가 명시적으로 질문한 경우에는 active_field_id가 있더라도 기존처럼 answer로 답한다.
active_field_id가 있으면 현재 대화 질문의 target Field로 사용한다.
active_field_id는 현재 질문의 중심일 뿐이다. 같은 발화에서 사용자가 다른 유효 writable target의 값도 명확히 제공하면 해당 candidate도 빠뜨리지 말고 함께 처리한다.
Field target은 값의 형태만으로 판단하지 않고 current_message, active_question, recent_turns, 현재 Request State를 함께 보고 발화의 의미로 결정한다.
현재 Request State에 이미 사용자 결정이 기록된 다른 Field는 current_message가 그 Field를 명시하거나 기존 결정을 변경·정정하려는 의미일 때만 target으로 고려한다.
사용자 발화를 그 target 질문에 대한 값 응답으로 자연스럽게 해석할 수 있으면 answer나 clarify가 아니라 propose를 사용한다.
사용자의 주된 의도가 현재 active Field의 후보값 작성을 Agent에게 맡기는 것이면, 사용자가 후보 문장을 직접 말하지 않았더라도 target 질문에 대한 값 응답으로 본다.
이때 Agent Context와 Request State에 해당 Field를 작성할 충분한 근거가 있으면 제공된 정보만 자연스럽게 종합하여 후보값을 만들고 propose한다.
작성 위임 여부와 근거 충분성은 특정 표현이나 키워드, 특정 Field가 아니라 current_message, active Field의 의미, 전체 Context를 함께 보고 의미적으로 판단한다.
Context에 없는 사실·식별자·수치를 새로 만들지 않으며, 근거 없는 정보가 후보값 작성에 반드시 필요할 때만 짧게 clarify한다.
복수 값의 의미는 특정 단어나 숫자 개수만으로 정하지 않는다. active_question의 현재 Field와 parent group, 전체 Request State, 사용자가 무엇을 복수라고 표현했는지, 대안·비교 조건인지, 동시에 존재하는 구성요소인지까지 함께 판단한다.
현재 active Field가 Write Contract의 set_condition_card_series target이면 그 Condition은 복수 Instance 입력이 가능하다. 사용자가 각 값이 서로 다른 Condition Instance에 대응한다고 명확히 표현하면 그 대응 순서대로 values를 구성한다.
사용자가 Base 제품이나 비교 제품을 언급하지 않고 현재 Condition Field의 여러 대안만 답한 경우, 제품 비교 가능성을 새로 만들어 clarify하지 않는다.
사용자가 여러 해석 제품을 비교하려는 의미이면 list_values의 geometry.products target을 사용한다. 첫 값은 기존 Base 제품, 이후 값은 기존 비교 제품 정책을 그대로 따른다.
해석 제품은 해석에 사용할 총 조립 형상을 기준으로 한다.
형상 자체뿐 아니라 부품 각도, 위치, Arrangement 등 조립 상태가 다른 해석 대상은 서로 다른 총 조립 형상이며 각각 다른 도면번호가 필요하다.
사용자가 동일 도면번호를 사용하면서 형상 또는 조립 상태만 다르게 비교 해석해 달라는 의미이면 동일 도면번호의 비교 제품 Proposal을 만들지 않는다.
이 경우 변경 상태가 이미 반영된 총 조립 형상을 준비하고 별도 도면번호 또는 현재 도면번호 입력 형식을 따르는 임시 도면번호를 알려 달라고 짧게 clarify하며, Agent가 임시 도면번호를 임의로 생성하지 않는다.
사용자가 서로 다른 도면번호와 비교 제품에 이미 반영된 Base 대비 차이를 제공하면 기존 geometry operation으로 정상 propose한다.
사용자가 명확히 단품 도면을 해석 제품으로 사용하려는 경우에는 해석에 사용할 총 조립 형상의 도면번호가 필요함을 안내한다.
위 판단은 특정 단어나 키워드 분기가 아니라 current_message, recent_turns, Form Context, Request State를 함께 보고 발화의 의미로 수행한다.
같은 Field 값이 서로 다른 조건 대안인 의미이면 set_condition_card_series를 사용한다. values의 각 항목은 조건 카드 하나의 scalar 값이어야 하며 하나의 Field에 쉼표 문자열로 합치지 않는다.
운전 조건에서 여러 값이 서로 다른 운전 대안이면 set_condition_card_series를 사용하고, 한 운전 조건에 동시에 존재하는 여러 Fan의 값이면 set_operating_fans를 사용한다.
예를 들어 RPM 800과 1000이 두 운전 대안이면 운전 조건 두 개이고 각 조건에는 scalar RPM 하나가 들어간다. 반면 Fan 두 개가 각각 800과 1000 RPM이면 운전 조건 하나 안에 Fan 두 개를 둔다.
한 운전 조건의 Fan별 위치와 RPM이 함께 명확하면 set_operating_fans의 locations과 values를 같은 순서로 사용하고 fan_rpm_mode를 individual로 둔다. 모든 Fan이 동일 RPM이라는 의미가 명확할 때만 common을 사용하며, RPM 숫자가 같다는 이유만으로 mode를 추론하지 않는다.
열교환기 사양, 공간 환경 조건, 취출 공기 조건의 한 Field에 대한 복수 대안도 set_condition_card_series로 기존 반복 condition card에 분배한다.
같은 종류의 Condition Instance 여러 개를 설명하면서 첫 Instance의 여러 속성을 제시하고 다음 Instance에서는 달라지는 일부 속성만 제시했다면, 발화의 대응 관계가 명확한 경우에만 앞에서 제시한 나머지 공통 속성을 후속 Instance에도 복원한다. 각 속성마다 set_condition_card_series 하나를 사용하고 values의 같은 위치가 같은 Instance를 나타내도록 정렬한다.
공통 속성 복원은 현재 발화와 recent_turns에서 같은 Condition의 Instance 관계가 명확할 때만 하며, 서로 무관한 값의 pairing이나 Cartesian product를 만들지 않는다.
열교환기 사양의 관경, Fin Type, 열 수, FPI는 form_context의 allowed_values에 있는 실제 Catalog 값을 사용하며, 아래 HEX 전용 확인 정책은 일반 선택형 Field의 allowed_values 규칙보다 우선하며 자유입력 Field, allow_custom_input=true, active Field의 직접 값 응답을 바로 propose하는 일반 규칙보다도 우선한다.
사용자 표현이 allowed_values의 canonical 값과 `_comparable_value` 기준으로 같은 표현이면 해당 canonical 값으로 바로 propose한다. 같은 표현은 아니지만 LLM이 현재 form_context.allowed_values와 전체 대화 문맥을 기준으로 하나의 Catalog 후보를 식별했다면 바로 propose하지 않고, 사용자 표현에 대응하는 후보를 의미상 식별한 것으로 보고 custom input으로도 바로 propose하지 않은 채 그 후보가 맞는지 clarify하며, 식별한 candidate operation은 pending_write_candidates로 보존한다.
의미상 가능한 Catalog 후보가 둘 이상이면 임의 선택하지 않고 현재 allowed_values 후보를 보여 주어 선택을 요청하며 operations는 비워 둔다. 사용자가 Catalog 후보를 선택하는 것이 아니라 자신이 말한 원래 값을 그대로 쓰겠다는 의미를 명확히 밝힌 경우에만 allow_custom_input에 따라 원래 값을 직접 입력값으로 propose한다.
Catalog에 없는 값을 스스로 생성하거나 보정하지 않으며 alias 사전, 특정 문구 규칙, fuzzy matching, 문자열 거리, 유사도 점수, Field별 가중치나 우선순위를 만들지 않는다. 자연어와 후보의 의미 관계는 전체 대화 문맥으로 판단한다.
서버는 Proposal 생성 전에 실제 Catalog 조합 확인과 구조적 검증만 수행하며 자동 대체 후보를 산출하지 않는다.
현재 문맥상 해석이 하나로 충분히 정해지고 Write Contract에 그 입력을 처리할 기존 operation이 있으면 해당 operation으로 propose하며, 값의 형태상 가능한 다른 target을 새로 만들어 clarify하지 않는다. 실제로 둘 이상의 해석이 Context에 근거하고 선택에 따라 State 변경이 달라질 때만 짧게 clarify한다. 충분한 active_question Context가 있으면 Field명을 다시 묻지 않는다.
active_field_id가 geometry.base_product.<field_key>이면 set_geometry_field targets의 role=base 항목에서 geometry_id를 찾아 해당 field_key의 operation을 만든다.
active_field_id가 geometry.comparison_products[N].<field_key>이면 Request State의 해당 비교 제품 geometry_id를 찾아 set_geometry_field operation을 만든다.
위 geometry target에 사용자가 유효한 단일 값을 답하면 같은 Field 질문을 reply로 반복하지 않고 propose한다.
선택형 Field는 form_context의 allowed_values를 canonical 값 판단 근거로 사용하고, 자연어 표현은 의미를 해석해 canonical 값으로 propose한다. 단, 위 HEX 4개 Field에는 이 일반 규칙보다 HEX 전용 확인 정책을 우선 적용한다.
현재 active Field의 allowed_values에 미정이 있고 사용자의 답이 현재 질문 문맥에서 아직 값이 결정되거나 확인되지 않았다는 의미이면 canonical 값 미정으로 propose한다.
이 판단은 current_message의 특정 문자열이나 키워드 목록이 아니라 active_question과 Field Context를 함께 사용하며, 실제로 해당 없음 또는 적용 대상이 없다는 의미와 구분한다.
allowed_values에 미정이 없는 Field에는 이 규칙을 적용하지 않는다.
자유입력 Field에서는 current_message가 명시적 질문이 아닌 비어 있지 않은 직접 값 응답으로 자연스러우면 첫 응답부터 원문 그대로 propose한다. form_context.example은 입력 예시일 뿐 허용 형식이나 검증 규칙이 아니며, 예시와 다르다는 이유로 같은 질문을 반복하거나 clarify하지 않는다.
current_message가 질문이 아니고 사용자가 form_context의 Field를 명시하여 값을 서술하면 해당 Field에 대한 직접 입력으로 판단하고, 현재값 안내로 answer하지 말고 propose한다.
allow_custom_input=true인 Field는 allowed_values 외에도 Field 의미에 맞는 사용자의 명시적 자유입력 값을 허용하며, 그 값을 원문 그대로 propose한다.
active_field_id가 없고 사용자가 Field를 특정하지 않은 값만 답하면 임의 Field를 추측하여 변경하지 않는다.
사용자가 직접 입력·변경하겠다고 한 값 또는 위 규칙에 따라 작성을 위임하여 기존 근거로 생성한 후보값만 Write Contract의 operation으로 propose한다.
서로 다른 Field의 여러 값이 명확하면 여러 operation을 한 propose에 담는다. 여러 Field 사이의 pairing이나 Cartesian product는 새로 추론하지 않는다.
값 candidate를 하나 이상 식별했지만 사용자 확인이나 추가 설명이 실제로 필요하면 action=clarify로 응답하고, 이미 식별한 모든 유효 candidate를 operations에 담는다. 이 operations는 Request State를 변경하지 않고 다음 turn의 pending_write_candidates로 보존된다.
conversation.pending_write_candidates가 있으면 current_message와 recent_turns를 함께 보고 사용자의 의미상 확인, 수정 또는 추가 설명인지 판단한다. 사용자가 candidate 전체에 의미상 동의하면 특정 확인 문구에 의존하지 말고 action=propose로 응답하며 보존된 candidate 전체를 operations에 포함한다.
pending_write_candidates 중 명시적으로 수정되거나 철회되지 않은 candidate는 다음 clarify에서도 유지하고, 수정된 candidate는 같은 writable target의 새 operation으로 교체한다.
현재 응답이 pending_write_candidates를 만든 바로 그 clarification을 의미상 이어받는 경우에만 continues_pending_clarification=true로 응답한다. 무관한 새 질문·새 변경·새 clarification이면 false이며 기존 pending candidate를 새 Proposal에 포함하지 않는다.
의뢰자 정보의 사업부, 부서, 요청자(사용자가 요청사라고 표현한 경우 포함), 직급 변경은 각각 basic_info.division, basic_info.department, basic_info.requester_name, basic_info.requester_role의 set target을 사용한다.
basic_info.division은 의뢰자 소속 사업부이고 request_context.division은 해석 대상 제품의 Division이므로 서로 대신 변경하지 않는다. 어느 Division을 뜻하는지 Context로 구분할 수 없을 때만 짧게 clarify한다.
한 메시지에서 active Field뿐 아니라 사용자가 명확히 제공한 모든 단계의 정보를 각각 판단한다. 일부 관계만 애매하면 명확한 정보는 operations 또는 deferred_facts로 유지하고 애매한 관계만 clarify한다.
deferred_facts는 의미가 명확하지만 아직 실제 writable target이 없는 정보만 담는다. 현재 target이 있는데 확인이 필요한 pending_write_candidates와 혼용하지 않는다.
deferred_facts에는 미래 geometry_id, card_id, fan_id를 추측하지 말고 업무상 role·제품 참조·조건 종류·Fan 이름/위치와 field_key/value를 구조화한다.
source_summary에는 사용자가 앞서 제공한 사실을 과장 없이 짧게 요약한다. reply에는 지금 반영할 정보, target이 없어 보관할 정보, 관계 확인이 필요한 정보가 있으면 간단히 구분해 알린다.
Agent Context의 request_deferred_input.ready 항목은 앞서 보관한 정보가 현재 target에 연결된 결과다. 현재 메시지의 더 최신 입력과 충돌하지 않으면 그 operation을 Proposal에 포함하고, 앞선 입력 근거와 당시 target 부재 및 지금 반영 가능해진 이유를 reply로 설명한다.
Write Contract에 없는 변경 중 target이 아직 없어서 보관 가능한 명확한 정보는 deferred_facts로 반환하고, 그 외에는 현재 Agent로 직접 반영할 수 없음을 answer로 안내한다.
request_context는 context_locked=false이고 정확히 하나의 제품 분류 경로와 해석유형이 명확할 때만 confirm_request_context 전용 operation 하나로 최초 확정할 수 있다. taxonomy_id를 알면 taxonomy_id와 analysis_type을, 모르면 division·product_lineup·platform·chassis의 정확한 canonical 값과 analysis_type을 context에 담는다. Chassis가 없는 canonical 경로는 chassis=null로 담는다. 제품 분류값을 일반 set operation으로 나누지 않는다.
context_locked=true인 request_context는 Agent가 변경하지 않는다.
이미 확정된 해석유형 변경을 요청하면 action은 answer, operations는 빈 배열, active_field_id는 request_context.analysis_type으로 응답한다.
이때 현재 해석유형을 알려 주고 화면의 해석유형 변경 기능을 이용하도록 안내하며, Agent에게 변경을 다시 요청하라고 안내하지 않는다.
현재 입력 내용만으로 근거가 충분하면 더 적합해 보이는 해석유형을 함께 안내할 수 있지만 추측하지 않는다.
해석유형의 현재 값이나 의미만 묻는 일반 질문에는 위 변경 요청 표시를 사용하지 않고 active_field_id를 null로 응답한다.
현재 Request에서 선택된 Division, Product Line-up, Platform, Chassis를 묻는 질문은 request_state로 답하고 product_hierarchy_query는 null로 둔다.
제품 분류 기준의 Division/Product Line-up/Platform/Chassis 관계를 묻는 질문은 action=answer, resume_workflow=false, product_hierarchy_query에 의미상 식별된 조건만 넣는다.
product_hierarchy_query의 허용 key는 taxonomy_id, division, product_lineup, platform, chassis이며 값은 사용자가 조회하려는 canonical 명칭이다. Duct(Multi V)와 Duct(Single CAC)의 NA만 실제 Chassis 값이며 그 밖의 NA를 분류값으로 만들지 않는다.
해석 대상 제품 분류와 해석유형에는 미정이나 직접 입력을 제안하지 않는다. 등록된 목록에 없는 값을 생성·보정하거나 유사한 값으로 임의 선택하지 않는다. 사용자가 미등록 값, 신규 Product Line-up·Platform·Chassis 또는 직접 입력을 요청하면 해석 대상 제품 분류는 등록된 목록에서만 선택할 수 있고 새로운 분류는 해석의뢰관리자에게 추가를 요청해야 한다고 안내한다.
연속 질문에서는 recent_turns를 이용해 생략된 조회 대상과 관계를 해석하되 현재 Request 값을 조회 대상의 분류 근거로 대신 사용하지 않는다.
Product Hierarchy의 실제 0건/1건/복수 결과 답변은 서버가 canonical source로 생성하므로 reply에서 관계를 추측하지 않는다.
다음 행동이나 제출 절차에 관한 질문은 특정 사용자 표현이나 키워드 목록이 아니라 current_message, recent_turns, validation과 submission_process를 함께 보고 의미적으로 판단한다.
submission_process.required_input_complete는 필수 입력 충족 여부일 뿐 실제 제출 또는 전체 절차 완료를 뜻하지 않는다. 이 상태를 제출 완료, 화면에서 제출 가능 또는 현재 화면에서 직접 제출하는 것으로 표현하지 않는다.
필수 입력이 완료된 뒤의 첫 행동은 Case Matrix 확인이다. 그 다음에는 전체 확인 화면에서 의뢰서 미리보기를 검토하고 의뢰서 생성(Word)을 실행하도록 순서대로 안내한다.
제출 방법을 안내할 때는 submission_process의 생성된 Word 파일, 이메일 제출 방식과 recipient를 사용한다. 담당자 정보를 추측하거나 Agent Context 밖의 제출 경로를 만들지 않는다.
Agent Context에는 Case Matrix 확인, 미리보기 검토 또는 Word 생성의 실제 완료 여부가 별도 기록되지 않으므로 완료했다고 추측하지 않는다. recent_turns에서 사용자가 직전 단계 완료를 분명히 밝힌 경우에만 다음 단계를 안내한다.
다음 행동이나 제출 방법에 답할 때 질문과 관계없는 미정 항목이나 누락 항목을 매번 반복하지 않는다.
Field, Instance, Value를 안전하게 특정할 수 없을 때만 clarify한다.
system_generated/read_only Field는 수정하지 않는다. RAG는 사용하지 않는다.
active_field_id와 recent_turns를 문맥으로 사용하되 Fan이 여러 개면 fan_id를 추측하거나 전체 Fan을 변경하지 않는다.
active question이 특정 Fan의 fan_location이면 사용자가 제공한 위치 표현을 변환하지 말고 해당 card_id와 fan_id의 set_condition_field로만 제안한다. 사용자가 말하지 않은 Fan 위치를 생성하지 않는다.
answer의 operations는 반드시 빈 배열이다. clarify의 operations에는 이미 식별한 유효 candidate가 있을 때만 그 candidate 전체를 담고, 아직 식별한 candidate가 없으면 빈 배열을 사용한다. propose의 operations는 하나 이상이어야 한다.
propose와 clarify에서는 resume_workflow=false이고 product_hierarchy_query는 null이어야 한다.
answer에서는 continues_pending_clarification=false여야 한다.
reply는 사용자에게 그대로 보여줄 자연스러운 한국어 문장이다.
Agent Context의 내부 정보는 판단에만 사용하고 reply에는 SCREEN-xx, State key/path, Field ID, active_field_id, workflow_status, geometry_id, card_id, fan_id, operation명, canonical path, Write Contract 등 구현용 명칭이나 식별자를 노출하지 않는다.
reply에서 위치나 항목을 설명할 때는 실제 UI의 단계 번호와 화면명, 실제 UI의 Section/Field 명칭, 대응 UI 명칭이 없으면 이해하기 쉬운 업무 용어 순서로 표현한다.
사용자가 사용 방법이나 진행 절차를 물으면 Navigation에 표시된 명칭을 그대로 사용한다: 01 의뢰 대상·시작, 02 요청 내용, 03 해석 제품, 04 해석 조건, 05 Case Matrix, 06 전체 확인·Preview·Word.
내부 식별자를 단순히 제거하거나 치환한 어색한 문장을 만들지 말고, 사용자가 이해할 수 있는 UI 명칭과 업무 용어로 문장 전체를 자연스럽게 작성한다."""


class AgentDecisionError(ValueError):
    """Raised when the one LLM result does not satisfy AgentDecision."""


@dataclass(frozen=True)
class AgentDecision:
    action: str
    reply: str
    operations: tuple[dict[str, Any], ...]
    active_field_id: str | None
    resume_workflow: bool
    product_hierarchy_query: dict[str, str] | None
    continues_pending_clarification: bool
    deferred_facts: tuple[dict[str, Any], ...] = ()


def _clean(value: Any) -> str:
    return str("" if value is None else value).replace("\x00", "").strip()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _condition_field_label(card_type: Any, field_key: Any) -> str:
    template = next((item for item in CARD_TEMPLATES if item["key"] == _clean(card_type)), None)
    if not isinstance(template, Mapping):
        return ""
    return next((label for key, label, _unit in template["fields"] if key == _clean(field_key)), "")


def _json_object(text: Any) -> dict[str, Any]:
    clean = _clean(text)
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", clean, flags=re.IGNORECASE)
    try:
        payload = json.loads(clean)
    except (json.JSONDecodeError, TypeError) as exc:
        raise AgentDecisionError("invalid_agent_decision_json") from exc
    if not isinstance(payload, dict):
        raise AgentDecisionError("agent_decision_must_be_object")
    return payload


def validate_agent_decision(raw: Any) -> AgentDecision:
    legacy_keys = {"action", "reply", "operations", "active_field_id"}
    previous_keys = {*legacy_keys, "resume_workflow", "product_hierarchy_query"}
    current_keys = {*previous_keys, "continues_pending_clarification"}
    deferred_keys = {*current_keys, "deferred_facts"}
    if not isinstance(raw, Mapping) or frozenset(raw) not in {
        frozenset(legacy_keys),
        frozenset(previous_keys),
        frozenset(current_keys),
        frozenset(deferred_keys),
    }:
        raise AgentDecisionError("invalid_agent_decision_shape")
    action = _clean(raw.get("action"))
    reply = _clean(raw.get("reply"))
    operations = raw.get("operations")
    active_field_id = raw.get("active_field_id")
    legacy_shape = set(raw) == legacy_keys
    resume_workflow = action == "answer" if legacy_shape else raw.get("resume_workflow")
    hierarchy_query_raw = None if legacy_shape else raw.get("product_hierarchy_query")
    continues_pending_clarification = (
        raw.get("continues_pending_clarification")
        if set(raw) == current_keys or set(raw) == deferred_keys
        else False
    )
    deferred_raw = raw.get("deferred_facts", []) if set(raw) == deferred_keys else []
    if action not in ALLOWED_AGENT_ACTIONS or not reply or not isinstance(operations, list):
        raise AgentDecisionError("invalid_agent_decision_value")
    if not isinstance(resume_workflow, bool):
        raise AgentDecisionError("invalid_resume_workflow")
    if not isinstance(continues_pending_clarification, bool):
        raise AgentDecisionError("invalid_pending_clarification_continuation")
    if not isinstance(deferred_raw, list) or len(deferred_raw) > 32:
        raise AgentDecisionError("invalid_deferred_facts")
    deferred_facts: list[dict[str, Any]] = []
    for raw_fact in deferred_raw:
        fact = normalize_deferred_fact(raw_fact) if isinstance(raw_fact, Mapping) else None
        if fact is None:
            raise AgentDecisionError("invalid_deferred_fact")
        deferred_facts.append(fact)
    if active_field_id is not None and (not isinstance(active_field_id, str) or not active_field_id.strip()):
        raise AgentDecisionError("invalid_active_field_id")
    hierarchy_query: dict[str, str] | None = None
    if hierarchy_query_raw is not None:
        allowed_query_keys = {"taxonomy_id", "division", "product_lineup", "platform", "chassis"}
        if not isinstance(hierarchy_query_raw, Mapping) or not hierarchy_query_raw or not set(hierarchy_query_raw) <= allowed_query_keys:
            raise AgentDecisionError("invalid_product_hierarchy_query")
        hierarchy_query = {
            key: _clean(value)
            for key, value in hierarchy_query_raw.items()
            if isinstance(value, str) and _clean(value)
        }
        if len(hierarchy_query) != len(hierarchy_query_raw):
            raise AgentDecisionError("invalid_product_hierarchy_query")
    if action == "propose":
        if not operations or not all(isinstance(operation, Mapping) for operation in operations):
            raise AgentDecisionError("propose_requires_operations")
    elif action == "clarify":
        if not all(isinstance(operation, Mapping) for operation in operations):
            raise AgentDecisionError("clarify_requires_valid_operations")
    elif operations:
        raise AgentDecisionError("read_only_action_forbids_operations")
    if action != "answer" and resume_workflow:
        raise AgentDecisionError("read_only_answer_required_for_resume")
    if action == "answer" and continues_pending_clarification:
        raise AgentDecisionError("answer_cannot_continue_pending_clarification")
    if hierarchy_query is not None and (action != "answer" or resume_workflow or active_field_id is not None):
        raise AgentDecisionError("invalid_product_hierarchy_lookup_action")
    return AgentDecision(
        action=action,
        reply=reply,
        operations=tuple(dict(operation) for operation in operations),
        active_field_id=active_field_id.strip() if isinstance(active_field_id, str) else None,
        resume_workflow=resume_workflow,
        product_hierarchy_query=hierarchy_query,
        continues_pending_clarification=continues_pending_clarification,
        deferred_facts=tuple(deferred_facts),
    )


def decide_agent_action(
    agent_context: Mapping[str, Any],
    write_contract: Mapping[str, Any],
) -> AgentDecision:
    """Make exactly one semantic LLM call from the two canonical contexts."""

    messages = [
        {"role": "system", "content": _SYSTEM_INSTRUCTION},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "agent_context": agent_context,
                    "write_contract": write_contract,
                    "output_contract": {
                        "action": "answer | propose | clarify",
                        "reply": "한국어 답변",
                        "operations": [],
                        "active_field_id": None,
                        "resume_workflow": False,
                        "product_hierarchy_query": None,
                        "continues_pending_clarification": False,
                        "deferred_facts": [],
                    },
                },
                ensure_ascii=False,
            ),
        },
    ]
    result = azure_chat_completion(messages, max_tokens=1800)
    raw_decision = _json_object(result.get("content"))
    if frozenset(raw_decision) != frozenset(
        {
            "action",
            "reply",
            "operations",
            "active_field_id",
            "resume_workflow",
            "product_hierarchy_query",
            "continues_pending_clarification",
            "deferred_facts",
        }
    ):
        raise AgentDecisionError("invalid_agent_decision_shape")
    return validate_agent_decision(raw_decision)


def operations_match_write_contract(
    operations: Sequence[Mapping[str, Any]],
    write_contract: Mapping[str, Any],
) -> bool:
    definitions = _mapping(write_contract.get("operations"))
    general_targets = _mapping(definitions.get("set")).get("targets")
    allowed_paths = {
        _clean(target.get("path"))
        for target in (general_targets if isinstance(general_targets, list) else [])
        if isinstance(target, Mapping)
    }
    for operation in operations:
        op = _clean(operation.get("op"))
        if op == "confirm_request_context":
            if _mapping(definitions.get(op)).get("available") is not True or normalize_context_confirmation_operation(
                operation,
                state={},
                source="main_agent_decision",
            ) is None:
                return False
        elif op == "set":
            if _clean(operation.get("path")) not in allowed_paths or not _clean(operation.get("value")):
                return False
        elif op in {"set_geometry_field", "set_condition_field"}:
            if normalize_instance_write_operation(
                operation,
                contract=write_contract,
                source="main_agent_decision",
            ) is None:
                return False
        elif op == "list_values":
            targets = _mapping(definitions.get(op)).get("targets")
            values = operation.get("values")
            if (
                not isinstance(targets, list)
                or not any(isinstance(target, Mapping) and target.get("path") == operation.get("path") for target in targets)
                or not isinstance(values, list)
                or len(values) < 2
                or any(not _clean(value) for value in values)
            ):
                return False
        elif op in {"set_condition_card_series", "set_operating_fans"}:
            if normalize_structural_write_operation(
                operation,
                contract=write_contract,
                source="main_agent_decision",
            ) is None:
                return False
        else:
            return False
    return bool(operations)


def merge_write_candidates(
    pending: Sequence[Mapping[str, Any]],
    decided: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Keep pending targets while replacing or adding targets decided this turn."""

    def target_key(operation: Mapping[str, Any]) -> tuple[Any, ...]:
        op = _clean(operation.get("op"))
        if op in {"set", "list_values"}:
            return (op, _clean(operation.get("path")))
        if op == "confirm_request_context":
            return (op,)
        if op == "set_geometry_field":
            return (op, _clean(operation.get("geometry_id")), _clean(operation.get("field_key")))
        if op == "set_condition_field":
            return (
                op,
                _clean(operation.get("card_id")),
                _clean(operation.get("field_key")),
                _clean(operation.get("fan_id")),
            )
        if op == "set_condition_card_series":
            return (op, _clean(operation.get("card_type")), _clean(operation.get("field_key")))
        if op == "set_operating_fans":
            return (op, _clean(operation.get("card_id")))
        return (op, json.dumps(dict(operation), ensure_ascii=False, sort_keys=True, default=str))

    merged = [dict(operation) for operation in pending]
    indexes = {target_key(operation): index for index, operation in enumerate(merged)}
    for operation in decided:
        candidate = dict(operation)
        key = target_key(candidate)
        if key in indexes:
            merged[indexes[key]] = candidate
        else:
            indexes[key] = len(merged)
            merged.append(candidate)
    return tuple(merged)


def writable_active_field_ids(
    agent_context: Mapping[str, Any],
    write_contract: Mapping[str, Any],
) -> set[str]:
    definitions = _mapping(write_contract.get("operations"))
    writable: set[str] = set()
    general = _mapping(definitions.get("set")).get("targets")
    writable.update(
        _clean(target.get("path"))
        for target in (general if isinstance(general, list) else [])
        if isinstance(target, Mapping)
    )
    conditions = _mapping(definitions.get("set_condition_field")).get("targets")
    location_active_fields = {
        f"conditions.{_clean(target.get('card_id'))}.fan_location"
        for target in (conditions if isinstance(conditions, list) else [])
        if isinstance(target, Mapping) and _clean(target.get("field_key")) == "fan_location"
    }
    writable.update(
        f"conditions.{_clean(target.get('card_id'))}.{_clean(target.get('field_key'))}"
        for target in (conditions if isinstance(conditions, list) else [])
        if isinstance(target, Mapping)
    )
    geometry = _mapping(definitions.get("set_geometry_field")).get("targets")
    for target in geometry if isinstance(geometry, list) else []:
        if not isinstance(target, Mapping):
            continue
        prefix = "geometry.base_product" if target.get("role") == "base" else "geometry.comparison_products[]"
        writable.update(
            f"{prefix}.{_clean(field.get('field_key'))}"
            for field in target.get("fields", [])
            if isinstance(field, Mapping)
        )
    form_fields = _mapping(agent_context.get("form_context")).get("fields")
    existing = {
        _clean(field.get("field_id"))
        for field in (form_fields if isinstance(form_fields, list) else [])
        if isinstance(field, Mapping) and not field.get("system_generated") and not field.get("read_only")
    }
    return (writable & existing) | location_active_fields


def _expand_state_path(state: Mapping[str, Any], path: str) -> list[tuple[str, Any, tuple[int, ...]]]:
    """Resolve Registry selectors and wildcards to concrete canonical values."""

    nodes: list[tuple[Any, str, tuple[int, ...]]] = [(state, "", ())]
    for segment in path.split("."):
        match = re.fullmatch(r"([^\[\]]+)(?:\[([^\]]*)\])?", segment)
        if match is None:
            return []
        name, selector = match.groups()
        expanded: list[tuple[Any, str, tuple[int, ...]]] = []
        for node, concrete_path, indexes in nodes:
            if not isinstance(node, Mapping):
                continue
            child = node.get(name)
            prefix = f"{concrete_path}.{name}" if concrete_path else name
            if selector is None:
                expanded.append((child, prefix, indexes))
                continue
            if not isinstance(child, list):
                continue
            if selector in {"", "*"}:
                expanded.extend(
                    (item, f"{prefix}[{index}]", (*indexes, index))
                    for index, item in enumerate(child)
                )
                continue
            selector_key, separator, selector_value = selector.partition("=")
            if not separator:
                continue
            item_key = "id" if selector_key.endswith("_id") else selector_key
            for index, item in enumerate(child):
                if isinstance(item, Mapping) and _clean(item.get(item_key)) == selector_value:
                    expanded.append((item, f"{prefix}[{selector}]", (*indexes, index)))
                    break
        nodes = expanded
    return [
        (path, field_value(value, "") if isinstance(value, Mapping) else value, indexes)
        for value, path, indexes in nodes
    ]


def _condition_card(state: Mapping[str, Any], card_id: str) -> tuple[Mapping[str, Any], int, int]:
    conditions = _mapping(state.get("conditions"))
    raw_cards = conditions.get("condition_sets")
    cards = [card for card in raw_cards if isinstance(card, Mapping)] if isinstance(raw_cards, list) else []
    card = next((item for item in cards if _clean(item.get("id")) == card_id), {})
    if not card:
        return {}, 0, 0
    same_type = [item for item in cards if item.get("type") == card.get("type")]
    index = next((position for position, item in enumerate(same_type, 1) if item is card), 0)
    return card, index, len(same_type)


def _condition_instance_label(card: Mapping[str, Any], index: int, count: int) -> str:
    card_label = _clean(card.get("label"))
    if count <= 1:
        return card_label
    name = _clean(card.get("name"))
    if not name:
        name = _clean(field_value(_mapping(card.get("fields")).get("name"), ""))
    return name or " ".join(part for part in (card_label, str(index)) if part)


def _proposal_field_projection(state: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    form_fields = build_form_context(state).to_dict()["fields"]
    registry = {field.field_id: field for field in get_field_registry(state)}
    projection: dict[str, dict[str, str]] = {}
    for field in form_fields:
        if field.get("system_generated") or field.get("read_only"):
            continue
        field_id = _clean(field.get("field_id"))
        registry_field = registry.get(field_id)
        value_path = registry_field.value_path if registry_field is not None else field_id
        for concrete_path, value, indexes in _expand_state_path(state, value_path):
            label = _clean(field.get("label")) or field_id
            if registry_field is None:
                if not field_id.startswith("request_context."):
                    geometry_index = indexes[0] + 2 if indexes else 1
                    label = f"형상 {geometry_index} · {label}"
            elif registry_field is not None and registry_field.card_id:
                card, card_index, card_count = _condition_card(state, registry_field.card_id)
                instance_label = _condition_instance_label(card, card_index, card_count)
                label = _condition_field_label(card.get("type"), registry_field.field_key) or label
                fans = card.get("fans") if isinstance(card.get("fans"), list) else []
                fan_label = ""
                if "[*]" in registry_field.value_path and len(fans) > 1 and indexes:
                    fan_index = indexes[-1]
                    fan = fans[fan_index] if fan_index < len(fans) and isinstance(fans[fan_index], Mapping) else {}
                    fan_label = _clean(fan.get("name")) or _clean(fan.get("location")) or str(fan_index + 1)
                label = " · ".join(part for part in (instance_label, label, fan_label) if part) or label
            projection[concrete_path] = {"label": label, "value": _clean(value)}
    conditions = _mapping(state.get("conditions"))
    for card in conditions.get("condition_sets", []) if isinstance(conditions.get("condition_sets"), list) else []:
        if not isinstance(card, Mapping) or _clean(card.get("type")) != "operating":
            continue
        card_id = _clean(card.get("id"))
        card_label = _clean(card.get("name")) or _clean(card.get("label")) or "운전 조건"
        fans = card.get("fans") if isinstance(card.get("fans"), list) else []
        for index, fan in enumerate(fans, 1):
            if not isinstance(fan, Mapping) or not _clean(fan.get("id")):
                continue
            fan_id = _clean(fan.get("id"))
            order = {1: "첫 번째", 2: "두 번째", 3: "세 번째"}.get(index, f"{index}번째")
            path = f"conditions.condition_sets[card_id={card_id}].fans[fan_id={fan_id}].location"
            projection[path] = {"label": f"{card_label} · {order} 팬 위치", "value": _clean(fan.get("location"))}
    return projection


def proposal_changes(
    current_state: Mapping[str, Any],
    proposed_state: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Describe only user-visible canonical fields changed by the approved dry-run."""

    current = _proposal_field_projection(current_state)
    proposed = _proposal_field_projection(proposed_state)
    changes: list[dict[str, str]] = []
    for path in dict.fromkeys((*current, *proposed)):
        before = current.get(path, {"label": "변경 항목", "value": ""})
        after = proposed.get(path, {"label": before["label"], "value": ""})
        if before["value"] == after["value"]:
            continue
        changes.append(
            {
                "label": after["label"],
                "current_value": before["value"],
                "new_value": after["value"],
            }
        )
    return changes
