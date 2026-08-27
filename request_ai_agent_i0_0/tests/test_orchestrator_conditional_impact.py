from test_orchestrator_chat_panel import _panel_source, _run_panel_runtime


def test_approved_latest_read_only_compares_server_fieldset_snapshots_and_preserves_value_notice():
    _run_panel_runtime(
        """
const before = {
  metadata:{}, basic_info:{}, analysis_overview:{}, geometry:{}, case_matrix:{}, review:{}, legacy_internal:{},
  request_context:{condition_fieldset_snapshot:[
    {key:"operating", active:true, fields:[{key:"fan_rpm", label:"팬 회전수", active:true, required:true}]},
    {key:"heat_exchanger", active:true, fields:[{key:"fin_type", label:"Fin type", active:true, required:false}]},
    {key:"space_environment", active:true, fields:[{key:"room_temp", label:"공간 온도", active:true, required:true}]}
  ]},
  conditions:{condition_sets:[
    {type:"operating", fans:[{running:true, values:{fan_rpm:"780"}}]},
    {type:"heat_exchanger", fields:{fin_type:{value:"plain"}}},
    {type:"space_environment", fields:{room_temp:{value:"25"}}}
  ]}
};
const latest = {
  metadata:{}, basic_info:{}, analysis_overview:{}, geometry:{}, case_matrix:{}, review:{}, legacy_internal:{},
  request_context:{condition_fieldset_snapshot:[
    {key:"operating", active:true, fields:[{key:"fan_rpm", label:"팬 회전수", active:true, required:true}]},
    {key:"heat_exchanger", active:true, fields:[{key:"fin_type", label:"Fin type", active:true, required:true}]},
    {key:"space_environment", active:false, fields:[{key:"room_temp", label:"공간 온도", active:true, required:false}]},
    {key:"supply_air", active:true, fields:[{key:"heat_exchanger_temp", label:"취출 공기 온도", active:true, required:true}]}
  ]},
  conditions:{condition_sets:[{type:"operating", fans:[{running:true, values:{fan_rpm:"780"}}]}]}
};
orchestratorPanelState.requestId = "request_server";
orchestratorPanelState.latestApprovedState = before;
global.fetch = async url => url === "/api/orchestrator/proposals/decision"
  ? {ok:true, json:async()=>({ok:true, proposal_id:"proposal_server", status:"approved", read_only:true})}
  : {ok:true, json:async()=>({request_id:"request_server", request_version:8, state:latest})};
await decideOrchestratorProposal("proposal_server", "approve", {children:[]}, {textContent:""});
const impact = elements.orchestratorLog.children[0];
if (!String(impact.textContent).includes("조건부 필드 영향 안내")) throw new Error("impact notice missing");
const detail = String(impact.children[0].textContent);
for (const expected of ["활성화: 취출 공기 온도", "새 필수 입력: 취출 공기 온도", "새 필수 입력: Fin type", "비활성화: 공간 온도", "기존 값 25", "자동으로 삭제하거나 정리하지 않습니다."]) {
  if (!detail.includes(expected)) throw new Error(`missing impact: ${expected}`);
}
if (requestState !== latest || orchestratorPanelState.requestVersion !== 8 || editorSyncs !== 1 || derivedRenders !== 1) throw new Error("latest state was not the only adopted authority");
"""
    )


def test_nonapproved_or_malformed_results_do_not_calculate_or_render_conditional_impact():
    _run_panel_runtime(
        """
const before = {metadata:{}, basic_info:{}, analysis_overview:{}, geometry:{}, case_matrix:{}, review:{}, legacy_internal:{}, request_context:{condition_fieldset_snapshot:[{key:"space_environment", active:true, fields:[{key:"room_temp", label:"공간 온도", active:true, required:true}]}]}, conditions:{condition_sets:[{type:"space_environment", fields:{room_temp:{value:"25"}}}]}};
orchestratorPanelState.requestId = "request_server";
orchestratorPanelState.latestApprovedState = before;
const results = [
  {ok:true, json:async()=>({ok:true, proposal_id:"proposal_rejected", status:"rejected", read_only:true})},
  {ok:true, json:async()=>({ok:true, proposal_id:"proposal_empty", status:"approved", read_only:true})},
  {ok:true, json:async()=>({request_id:"request_server", request_version:8, state:{}})},
  {ok:true, json:async()=>({ok:true, proposal_id:"proposal_partial", status:"approved", read_only:true})},
  {ok:true, json:async()=>({request_id:"request_server", request_version:9, state:{metadata:{}, basic_info:{}, analysis_overview:{}, conditions:{}, request_context:{}}})},
];
global.fetch = async () => results.shift();
await decideOrchestratorProposal("proposal_rejected", "approve", {children:[]}, {textContent:""});
await decideOrchestratorProposal("proposal_empty", "approve", {children:[]}, {textContent:""});
await decideOrchestratorProposal("proposal_partial", "approve", {children:[]}, {textContent:""});
if (elements.orchestratorLog.children.length || editorSyncs || derivedRenders) throw new Error("non-approved or malformed result rendered impact or synchronized form");
"""
    )


def test_impact_helper_uses_only_existing_server_fieldset_snapshot_and_has_no_rule_engine_copy():
    source = _panel_source()
    assert "condition_fieldset_snapshot" in source
    assert "approvedConditionFieldset" in source
    for forbidden in ("build_condition_fieldset", "get_field_registry", "validate_state", "apply_patch", "condition_fieldsets.py"):
        assert forbidden not in source
