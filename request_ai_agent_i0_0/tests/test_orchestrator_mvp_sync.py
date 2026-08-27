from test_orchestrator_chat_panel import _run_panel_runtime


def test_approved_decision_refreshes_its_panel_request_once_and_adopts_server_latest_state():
    _run_panel_runtime(
        """
const requests = [];
const serverState = {metadata:{request_no:"SERVER-1"}, basic_info:{requester_name:{value:"server only"}}, analysis_overview:{}, geometry:{}, conditions:{}, request_context:{}, case_matrix:{}, review:{}, legacy_internal:{}};
global.fetch = async (url, options={}) => {
  requests.push({url, body:options.body || null});
  return url === "/api/orchestrator/proposals/decision"
    ? {ok:true, json:async()=>({ok:true, proposal_id:"proposal_server", status:"approved", read_only:true})}
    : {ok:true, json:async()=>({request_id:"request_server", request_version:7, state:serverState})};
};
orchestratorPanelState.requestId = "request_server";
const status = {textContent:""};
await decideOrchestratorProposal("proposal_server", "approve", {children:[]}, status);
await decideOrchestratorProposal("proposal_server", "approve", {children:[]}, status);
if (JSON.stringify(requests.map(item => [item.url, item.body])) !== JSON.stringify([
  ["/api/orchestrator/proposals/decision", '{"proposal_id":"proposal_server","decision":"approve"}'],
  ["/api/request/versioned/request_server", null],
  ["/api/orchestrator/proposals/decision", '{"proposal_id":"proposal_server","decision":"approve"}']
])) throw new Error("approved refresh was not exact-once");
if (requestState !== serverState || orchestratorPanelState.requestVersion !== 7 || editorSyncs !== 1 || derivedRenders !== 1) throw new Error("server latest state/version was not adopted");
if (!hasSyncedCaseMatrixRequest()) throw new Error("approved latest GET did not enable the Case Matrix action gate");
"""
    )


def test_non_approved_terminals_and_decision_or_get_failures_never_sync_or_send_follow_up():
    _run_panel_runtime(
        """
const outcomes = [
  {ok:true, json:async()=>({ok:true, proposal_id:"proposal_rejected", status:"rejected", read_only:true})},
  {ok:true, json:async()=>({ok:true, proposal_id:"proposal_conflicted", status:"conflicted", read_only:true})},
  {ok:false, json:async()=>({ok:false, error:"proposal_not_found"})},
  {ok:true, json:async()=>({ok:true, proposal_id:"proposal_get_failure", status:"approved", read_only:true})},
  {ok:false, json:async()=>({error:"request_read_failed"})},
];
const requests = [];
global.fetch = async (url, options={}) => { requests.push({url, body:options.body || null}); return outcomes.shift(); };
orchestratorPanelState.requestId = "request_server";
for (const proposalId of ["proposal_rejected", "proposal_conflicted", "proposal_unknown", "proposal_get_failure"]) {
  await decideOrchestratorProposal(proposalId, "approve", {children:[]}, {textContent:""});
}
if (requests.filter(item => item.url.startsWith("/api/request/versioned/")).length !== 1) throw new Error("only approved may GET");
if (editorSyncs !== 0 || derivedRenders !== 0 || requestState.basic_info.requester_name?.value === "server only") throw new Error("terminal or failure synchronized form");
if (requests.some(item => item.url === "/api/orchestrator/messages")) throw new Error("follow-up message sent");
"""
    )


def test_undo_creation_never_syncs_and_only_approved_inverse_uses_existing_latest_get_once():
    _run_panel_runtime(
        """
const requests = [];
const serverState = {metadata:{request_no:"SERVER-UNDO"}, basic_info:{requester_name:{value:"inverse server"}}, analysis_overview:{}, geometry:{}, conditions:{}, request_context:{}, case_matrix:{}, review:{}, legacy_internal:{}};
global.fetch = async (url, options={}) => {
  requests.push({url, body:options.body || null});
  if (url === "/api/orchestrator/proposals/undo") return {ok:true, json:async()=>({ok:true, kind:"undo_proposal_created", proposal:{proposal_id:"proposal_inverse", status:"pending", diff:{changed_path_count:1}}, read_only:true})};
  if (url === "/api/orchestrator/proposals/decision") return {ok:true, json:async()=>({ok:true, proposal_id:"proposal_inverse", status:"approved", read_only:true})};
  return {ok:true, json:async()=>({request_id:"request_server", request_version:9, state:serverState})};
};
orchestratorPanelState.requestId = "request_server";
const actions = {className:"proposal-actions", children:[], appendChild(node){this.children.push(node);}};
const status = {textContent:""};
await createOrchestratorUndoProposal("proposal_original", {children:[actions]}, status);
if (requests.some(item => item.url.startsWith("/api/request/versioned/")) || editorSyncs || derivedRenders) throw new Error("Undo creation synchronized form");
await decideOrchestratorProposal("proposal_inverse", "approve", {children:[]}, {textContent:""});
if (requests.filter(item => item.url.startsWith("/api/request/versioned/")).length !== 1 || editorSyncs !== 1 || derivedRenders !== 1) throw new Error("approved inverse did not use exactly one existing sync");
"""
    )
