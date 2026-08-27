"""Single page UI for the request assistant."""

from __future__ import annotations


HTML_TEMPLATE = r"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>CAE Request Assistant __APP_VERSION__</title>
  <style>
    :root{
      --ink:#4a4a4a;
      --muted:#707070;
      --bg:#f3f3f3;
      --paper:#ffffff;
      --line:#d6d6d6;
      --brand:#707070;
      --brand-strong:#5c5c5c;
      --accent:#707070;
      --danger:#4a4a4a;
      --warning:#5c5c5c;
      --ok:#4a4a4a;
      --blue:#5c5c5c;
      --soft:#f7f7f7;
      --shadow:0 4px 16px rgba(0,0,0,.07);
    }
    *{box-sizing:border-box;font-weight:400!important}
    html,body{height:100%}
    body{
      margin:0;
      color:var(--ink);
      background:var(--bg);
      font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans KR",sans-serif;
      font-size:15px;
      line-height:1.45;
      overflow-x:hidden;overflow-y:auto;
    }
    button,input,textarea,select{font:inherit}
    [hidden]{display:none!important}
    button{
      min-height:36px;
      border:1px solid #d6d6d6;
      border-radius:7px;
      background:var(--paper);
      color:var(--ink);
      cursor:pointer;
      font-size:13px;
      font-weight:500;
      padding:7px 11px;
    }
    button.primary{border-color:var(--brand);background:var(--brand);color:#fff}
    button.danger{border-color:#d6d6d6;background:#f7f7f7;color:var(--danger)}
    button.icon{width:34px;padding:0;display:grid;place-items:center}
    button.ghost{background:#fff;border-color:#d6d6d6}
    button:disabled{opacity:.48;cursor:not-allowed}
    input,textarea,select{
      width:100%;
      min-width:0;
      min-height:36px;
      border:1px solid #d6d6d6;
      border-radius:7px;
      background:var(--paper);
      color:#242424;
      padding:8px 9px;
      font-size:13px;
    }
    textarea{min-height:70px;resize:vertical;line-height:1.45}
    label{display:flex;flex-direction:column;gap:4px;font-size:13px;font-weight:500;color:#242424}
    button:focus-visible,input:focus-visible,textarea:focus-visible,select:focus-visible,[tabindex]:focus-visible{outline:3px solid #707070;outline-offset:2px}
    .topbar{
      height:48px;
      padding:6px 16px;
      display:grid;
      grid-template-columns:auto minmax(260px,1fr);
      gap:14px;
      align-items:center;
      border-bottom:1px solid rgba(0,0,0,.14);
      background:rgba(255,255,255,.9);
    }
    .brand{display:flex;align-items:center;gap:11px;min-width:0}
    .brand-mark{
      width:36px;height:36px;border-radius:8px;display:grid;place-items:center;
      color:#fff;background:linear-gradient(135deg,var(--brand),var(--accent));
      font-size:12px;font-weight:500;
    }
    h1{margin:0;font-size:16px;line-height:1.2;letter-spacing:0}
    .subtitle{margin-top:2px;color:var(--muted);font-size:12px}
    .top-meta{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:4px}
    .request-pill{
      display:inline-flex;align-items:center;min-height:24px;border:1px solid #d6d6d6;
      border-radius:8px;background:#f7f7f7;color:#4a4a4a;padding:2px 8px;
      font-size:12px;font-weight:500;
    }
    .request-pill.ok{border-color:#c6c6c6;background:#f7f7f7;color:var(--ok)}
    .request-pill.blocking{border-color:#bdbdbd;background:#f3f3f3;color:var(--danger)}
    .rag-toggle{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:500;color:#4a4a4a}
    .rag-toggle input{width:auto}
    .top-actions{display:flex;gap:7px;align-items:center;flex-wrap:wrap;justify-content:flex-end}
    .layout{
      height:auto;min-height:calc(100% - 48px);
      display:grid;
      grid-template-columns:minmax(0,1fr) 340px;
      gap:12px;
      padding:12px;
      width:min(100%,1500px);
      margin:0 auto;
      justify-content:center;
    }
    .panel{
      min-height:0;
      border:1px solid rgba(0,0,0,.13);
      border-radius:8px;
      background:var(--paper);
      box-shadow:var(--shadow);
      overflow:hidden;
    }
    .rail{display:grid;grid-template-rows:auto minmax(0,1fr)}
    .rail-head{padding:12px;border-bottom:1px solid var(--line);background:#f7f7f7}
    .rail-list{overflow:auto;padding:10px;display:flex;flex-direction:column;gap:8px}
    .main{display:grid;grid-template-rows:auto minmax(0,1fr)}
    .workspace-shell{min-width:0;min-height:0;display:grid;grid-template-rows:auto auto minmax(0,1fr);gap:10px;overflow:hidden}
    .workspace-bar{
      min-height:42px;display:flex;align-items:center;justify-content:space-between;gap:12px;
      padding:6px 10px;border:1px solid rgba(0,0,0,.13);border-radius:8px;background:var(--paper);box-shadow:var(--shadow);
    }
    .workspace-bar-copy{display:flex;align-items:baseline;gap:8px;min-width:0}
    .workspace-bar-copy strong{font-size:13px;color:#4a4a4a;white-space:nowrap}
    .workspace-bar-copy span{font-size:12px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .step-navigation{min-width:0}
    .screen-map{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:5px;min-height:96px;padding:0;background:transparent;isolation:isolate}
    .screen-map-item{
      position:relative;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;min-width:0;
      padding:10px 19px 9px 25px;border:0;background:#eeeeee;color:#707070;font-size:13px;font-weight:500;
      line-height:1.2;text-align:center;cursor:pointer;clip-path:polygon(0 0,calc(100% - 18px) 0,100% 50%,calc(100% - 18px) 100%,0 100%,18px 50%);
    }
    .screen-map-item:first-child{padding-left:18px;border-radius:12px 0 0 12px;clip-path:polygon(0 0,calc(100% - 18px) 0,100% 50%,calc(100% - 18px) 100%,0 100%)}
    .screen-map-item:last-child{padding-right:18px;border-radius:0 12px 12px 0;clip-path:polygon(0 0,100% 0,100% 100%,0 100%,18px 50%)}
    .screen-map-item:hover:not([aria-disabled="true"]){background:#e5e5e5;color:#4a4a4a}
    .screen-map-item:focus-visible{z-index:1;outline:3px solid rgba(92,92,92,.45);outline-offset:-3px}
    .screen-map-item[aria-current="page"]{background:linear-gradient(135deg,#707070,#5c5c5c);color:#fff}
    .screen-map-item[aria-disabled="true"]{cursor:not-allowed}
    .screen-map-number{font-size:31px;font-weight:500;line-height:.96;letter-spacing:-.04em;white-space:nowrap}
    .screen-map-label{max-width:100%;display:flex;align-items:center;justify-content:center;gap:4px;overflow-wrap:anywhere}
    .screen-map-lock{display:none;width:12px;height:12px;flex:0 0 12px;place-items:center}
    .screen-map-lock svg{width:12px;height:12px;fill:none;stroke:currentColor;stroke-linecap:round;stroke-linejoin:round;stroke-width:2}
    .screen-map-item[aria-disabled="true"] :is(.screen-map-number,.screen-map-label){color:#b8b8b8}
    .screen-map-item[aria-disabled="true"] .screen-map-lock{display:grid}
    .legacy-stage-rail{display:none}
    .screen-group{min-width:0}
    .screen-heading{margin:0 0 8px;font-size:13px;color:#707070}
    .screen-heading span{color:#4a4a4a}
    .title-with-icon{display:flex;align-items:center;gap:7px}
    .title-icon{width:22px;height:22px;display:inline-grid;flex:0 0 22px;place-items:center;border:1px solid #d6d6d6;border-radius:6px;background:#f7f7f7;color:var(--brand)}
    .title-icon svg{width:14px;height:14px;fill:none;stroke:currentColor;stroke-linecap:round;stroke-linejoin:round;stroke-width:1.8}
    .screen-heading-code{color:#707070!important}
    .hero{
      padding:12px;
      border-bottom:1px solid var(--line);
      background:#f7f7f7;
    }
    .hero-row{
      display:grid;
      grid-template-columns:minmax(210px,1fr) auto;
      gap:10px;
      align-items:end;
    }
    .hero h2{margin:0 0 7px;font-size:15px;color:#4a4a4a;letter-spacing:0}
    .hero p{margin:0;color:var(--muted);font-size:12px;line-height:1.45}
    .candidate-notice{
      margin-top:9px;
      display:none;
      border:1px solid #c6c6c6;
      background:#f7f7f7;
      color:#4a4a4a;
      border-radius:8px;
      padding:8px 10px;
      font-size:12px;
      line-height:1.45;
    }
    .workspace{min-height:0;overflow:visible;padding:12px}
    .workspace-tab{display:none;min-height:0}
    .workspace-tab.active{display:block}
    .workspace-form{
      width:100%;
      max-width:1120px;
      margin:0 auto;
    }
    .request-prep-card{
      margin-bottom:10px;
      border:1px solid #d6d6d6;
      border-radius:8px;
      background:#f7f7f7;
      overflow:hidden;
    }
    .request-prep-card[hidden]{display:none}
    .prep-head{
      display:grid;
      grid-template-columns:minmax(0,1fr) auto;
      gap:10px;
      align-items:start;
      padding:14px;
      border-bottom:1px solid #d6d6d6;
      background:#f7f7f7;
    }
    .prep-head h3{margin:0 0 6px;font-size:17px;color:#4a4a4a;letter-spacing:0}
    .prep-head p{margin:0;color:var(--muted);font-size:12px;line-height:1.45}
    .prep-head .prep-guidance{padding-left:10px;border-left:2px solid #b8b8b8;font-size:13px;line-height:1.6}
    .prep-guidance-line{display:block}
    .prep-guidance-next{margin-top:3px}
    .prep-guidance-emphasis{color:var(--ink);font-weight:600!important}
    .prep-actions{display:flex;gap:7px;align-items:center;flex-wrap:wrap;justify-content:flex-end}
    .prep-actions button.active{border-color:var(--brand);background:var(--brand);color:#fff}
    .prep-body{padding:12px;display:grid;gap:10px}
    .prep-flow{display:none}
    .prep-flow.active{display:grid;gap:10px}
    .prep-step{
      border:1px solid #d6d6d6;
      border-radius:8px;
      background:#fff;
      padding:10px;
    }
    .prep-step.disabled{opacity:.55}
    .prep-step-title{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px}
    .prep-step-title strong{font-size:13px;color:#4a4a4a}
    .prep-choice-grid{display:flex;gap:7px;flex-wrap:wrap}
    .prep-choice{
      min-width:76px;
      display:inline-flex;
      align-items:center;
      justify-content:center;
      gap:4px;
      background:#fff;
      border-color:#d6d6d6;
      color:#4a4a4a;
    }
    .prep-choice.selected{border-color:var(--brand);background:#eeeeee;color:var(--brand-strong)}
    .prep-choice:disabled{opacity:.48}
    .prep-choice-lock{width:12px;height:12px;display:inline-grid;flex:0 0 12px;place-items:center}
    .prep-choice-lock svg{width:12px;height:12px;fill:none;stroke:currentColor;stroke-linecap:round;stroke-linejoin:round;stroke-width:2}
    .prep-quick-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr)) auto;gap:8px;align-items:end}
    .prep-custom-control{display:grid;grid-template-columns:minmax(0,1fr) 36px;gap:6px;align-items:center}
    .prep-custom-control button{width:36px;min-width:36px;height:36px;padding:0;font-size:18px;line-height:1}
    .prep-summary{
      border:1px solid #d6d6d6;
      border-radius:8px;
      background:#f7f7f7;
      padding:10px;
      font-size:12px;
      line-height:1.5;
      display:grid;
      grid-template-columns:minmax(0,1fr) auto;
    }
    .prep-summary strong{display:block;grid-column:1 / -1;font-size:13px;color:#4a4a4a;margin-bottom:3px}
    .prep-summary .combo{grid-column:1 / -1;font-size:15px;font-weight:600;color:#4a4a4a}
    .prep-summary .note{grid-column:1;margin-top:4px;color:var(--muted)}
    .prep-summary-actions{grid-column:2;grid-row:3;display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end;margin-top:7px;margin-left:12px}
    .context-chip-bar{
      margin-bottom:10px;
      border:1px solid #d6d6d6;
      border-radius:8px;
      background:#f7f7f7;
      padding:10px;
      display:block;
      gap:10px;
      align-items:center;
    }
    .context-chip-bar[hidden]{display:none}
    .context-chip-list{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
    .context-chip-list .chip{font-size:12px}
    .context-chip-copy{margin-top:6px;color:var(--muted);font-size:12px;font-weight:500}
    .context-lock-gate{
      margin-bottom:10px;
      border:1px dashed #d6d6d6;
      border-radius:8px;
      background:#f7f7f7;
      padding:18px;
      text-align:center;
      color:#4a4a4a;
      font-size:13px;
      line-height:1.5;
      font-weight:500;
    }
    .context-lock-gate[hidden]{display:none}
    .gate{
      max-width:760px;
      margin:0 0 10px;
      border:1px dashed #d6d6d6;
      border-radius:8px;
      background:#f7f7f7;
      padding:22px;
      text-align:center;
    }
    .gate strong{display:block;margin-bottom:8px;font-size:18px;color:#4a4a4a}
    .section{
      margin-bottom:10px;
      border:1px solid var(--line);
      border-radius:8px;
      background:#fff;
      overflow:hidden;
    }
    .section-head{
      min-height:46px;
      display:flex;
      align-items:center;
      justify-content:space-between;
      gap:10px;
      padding:9px 11px;
      background:#f7f7f7;
      cursor:pointer;
    }
    .section-title{display:flex;align-items:center;gap:8px;min-width:0}
    .chev{width:20px;color:#707070;font-weight:500}
    .section h3{margin:0;font-size:14px;color:#4a4a4a;letter-spacing:0}
    .section-body{display:none;border-top:1px solid var(--line);padding:12px}
    .section.open .section-body{display:block}
    .section.open .chev{transform:rotate(90deg)}
    .request-content-screen .section-body{display:block}
    .request-content-screen .section-head{cursor:default}
    .geometry-screen .section-body{display:block}
    .stage-static-screen .section-body{display:block}
    .geometry-screen .section-head,
    .stage-static-screen .section-head{cursor:default}
    .geometry-screen .section-meta{display:none}
    .section-meta{display:flex;gap:6px;align-items:center;flex-wrap:wrap;justify-content:flex-end}
    .grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px}
    .grid.compact{grid-template-columns:repeat(3,minmax(0,1fr))}
    .request-basic-grid{grid-template-columns:repeat(4,minmax(0,1fr))}
    .request-basic-grid select[data-dropdown-path]{
      appearance:none;padding-right:42px;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23707070' stroke-linecap='round' stroke-linejoin='round' stroke-width='2'%3E%3Cpath d='m7 9 5 5 5-5'/%3E%3C/svg%3E");
      background-repeat:no-repeat;background-position:right 10px center;background-size:16px 16px
    }
    .request-basic-divider{grid-column:1/-1;border-top:1px solid var(--line);margin:3px 0}
    .grid.two{grid-template-columns:repeat(2,minmax(0,1fr))}
    .wide{grid-column:1/-1}
    .custom-input{margin-top:5px}
    .dropdown-custom-control .custom-input{margin-top:0}
    .undecided-field{display:flex;min-width:0;flex-direction:column;gap:4px}
    .undecided-combobox{
      position:relative;min-width:0;height:36px;display:grid;grid-template-columns:minmax(0,1fr) 36px;
      border:1px solid #d6d6d6;border-radius:7px;background:var(--paper)
    }
    .undecided-combobox:focus-within{outline:3px solid #707070;outline-offset:2px}
    .undecided-combobox input{height:34px;min-height:34px;border:0;border-radius:6px 0 0 6px;padding:8px 9px;background:transparent}
    .undecided-combobox input:focus-visible,
    .undecided-combobox-toggle:focus-visible{outline:0}
    .undecided-combobox input[readonly]{background:transparent;cursor:default}
    .undecided-combobox-toggle{
      width:36px;height:34px;min-height:34px;padding:0;
      display:grid;place-items:center;border:0;border-radius:0 6px 6px 0;
      background:transparent;color:var(--muted)
    }
    .undecided-combobox-toggle:hover{background:var(--soft);color:var(--ink)}
    .undecided-combobox-toggle svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-linecap:round;stroke-linejoin:round;stroke-width:2}
    .undecided-combobox-menu{
      position:absolute;z-index:40;top:calc(100% + 4px);left:-1px;right:-1px;padding:0;
      border:1px solid #d6d6d6;border-radius:0;background:var(--paper);box-shadow:none
    }
    .undecided-combobox-option{
      width:100%;min-height:30px;display:flex;align-items:center;
      border:0;border-radius:0;background:transparent;padding:5px 8px;text-align:left;cursor:default
    }
    .undecided-combobox-option:hover,
    .undecided-combobox-option:focus,
    .undecided-combobox-option[data-undecided-active="true"]{
      background-color:var(--brand)!important;color:#ffffff!important;outline:0
    }
    .request-detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;align-items:start}
    .request-detail-grid textarea{min-height:52px}
    .custom-input[hidden]{display:none}
    .subhead{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:10px 0 7px}
    .subhead strong{font-size:12px;color:#4a4a4a}
    .row-list{display:flex;flex-direction:column;gap:7px}
    .row-item{display:grid;grid-template-columns:minmax(0,1fr) 34px;gap:6px;align-items:center}
    .row-item.dual{grid-template-columns:minmax(0,1fr) minmax(0,1fr) 34px;align-items:end}
    .product-input-area{display:grid;gap:10px}
    .product-panel{border:1px solid #d6d6d6;border-radius:9px;background:#f7f7f7;padding:10px}
    .product-panel-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px}
    .product-panel-head strong{font-size:14px;color:#4a4a4a}
    .product-panel-copy{margin:2px 0 0;color:#707070;font-size:12px;line-height:1.4}
    .product-card{position:relative;border:1px solid #d6d6d6;border-radius:8px;background:#fff;padding:10px}
    .product-card + .product-card{margin-top:8px}
    .product-card-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:9px}
    .product-card-head h4{margin:0;color:#4a4a4a;font-size:13px;font-weight:600}
    .product-table{display:flex;flex-direction:column;gap:4px}
    .product-table-row{display:grid;grid-template-columns:minmax(74px,.55fr) minmax(180px,1.15fr) minmax(300px,2.3fr) 34px;gap:9px;align-items:end}
    .product-table-head{align-items:center}
    .product-table-head .product-action-heading{width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);clip-path:inset(50%);white-space:nowrap}
    .product-geometry-name,.base-product-description{display:flex;align-items:center;min-height:34px;padding:8px 9px;color:#242424;font-size:13px;font-weight:400;line-height:1.45}
    .product-card-actions{display:flex;justify-content:flex-end;margin-top:9px}
    .product-card-actions .icon{width:34px;min-width:34px}
    .geometry-inline-guidance{margin:0 0 0 auto;color:var(--request-workspace-muted);font-size:12px;font-weight:500;line-height:1.35}
    .changed-part-area{margin-top:10px}
    .part-input-area{border:1px solid #d6d6d6;border-radius:8px;padding:10px;background:#fff}
    .part-input-area .subhead{margin-top:0}
    .part-input-area.is-disabled{opacity:.55}
    .product-row-actions{display:flex;gap:4px;align-items:center}
    .product-row-actions .icon{width:30px;min-width:30px}
    .product-empty{margin:0;color:#707070;font-size:12px}
    .toggle-line{display:flex;flex-direction:row;align-items:center;gap:8px;font-size:13px;font-weight:500;margin:8px 0}
    .toggle-line input{width:auto}
    .condition-group{overflow:hidden;border:1px solid #d6d6d6;border-radius:8px;margin-bottom:10px;background:#fff}
    .condition-parent-label{display:inline-flex;align-items:center;min-height:22px;padding:0 7px;border-radius:999px;background:#eeeeee;color:#4a4a4a;font-size:11px;font-weight:500}
    .condition-group h4{margin:0;padding:9px 10px;border-bottom:1px solid #d6d6d6;font-size:13px;color:#4a4a4a}
    .condition-group-head{display:flex;align-items:center;justify-content:space-between;gap:8px;border-bottom:1px solid #d6d6d6;padding:9px 10px}
    .condition-group-head h3{margin:0;color:#4a4a4a;font-size:13px;font-weight:600}
    .condition-group-head-actions{display:flex;align-items:center;gap:6px}
    .condition-group-head-actions button{min-height:30px;padding:5px 9px}
    .condition-group-head-actions select{min-height:30px;width:156px;padding:5px 28px 5px 9px}
    .condition-group-head h4{border:0;padding:0;margin:0}
    .condition-group-guidance{margin:5px 0 0;color:#707070;font-size:12px;line-height:1.45}
    .condition-option-line{display:flex;align-items:center;gap:7px;font-size:12px;font-weight:500;color:#4a4a4a;white-space:nowrap}
    .condition-option-line input{width:auto}
    .operation-mode-control{display:flex;align-items:center;gap:6px;font-size:12px;font-weight:500;color:#4a4a4a}
    .operation-mode-control select{width:auto;min-width:116px;padding:6px 8px}
    .condition-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;padding:10px}
    .heat-exchanger-grid{grid-template-columns:repeat(5,minmax(120px,1fr));overflow:auto}
    .condition-card-layout{display:grid;gap:10px}
    .condition-primary-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
    .condition-primary-grid .condition-card-type-heat_exchanger{grid-column:1/-1}
    .condition-primary-grid .condition-card-type-operating{
      grid-column:1/-1;justify-self:start;
      width:min(100%,calc((100% - 10px)/2 + var(--operating-extra-width,0px)))
    }
    .condition-environment-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
    .condition-card-type-space_environment,.condition-card-type-supply_air{overflow:visible}
    .condition-card-type-space_environment:focus-within,.condition-card-type-supply_air:focus-within{position:relative;z-index:45}
    .condition-card-type-space_environment .condition-group-head,.condition-card-type-supply_air .condition-group-head{border-radius:7px 7px 0 0}
    .condition-card-rows{display:grid;gap:8px;padding:var(--request-workspace-card-content-padding,10px)}
    .condition-card-row{display:grid;grid-template-columns:repeat(var(--field-count),minmax(0,1fr)) max-content;gap:9px;align-items:end}
    .condition-card-type-heat_exchanger .condition-card-row{grid-template-columns:64px repeat(5,minmax(0,1fr)) max-content;gap:9px}
    .condition-card-type-heat_exchanger .condition-card-row>label{min-width:0;white-space:nowrap}
    .condition-card-type-heat_exchanger .condition-spec-name{padding-inline:4px;white-space:nowrap}
    .condition-card-type-operating .condition-card-rows{overflow-x:auto}
    .condition-card-type-operating .condition-card-row{grid-template-columns:minmax(42px,44px) 0 90px 9px max-content 9px max-content;column-gap:0}
    .condition-card-type-operating .condition-card-row>:nth-child(1){grid-column:1}
    .condition-card-type-operating .condition-card-row>:nth-child(2){grid-column:3}
    .condition-card-type-operating .condition-card-row>:nth-child(3){grid-column:5}
    .condition-card-type-operating .condition-card-row>:nth-child(4){grid-column:7}
    .condition-card-type-operating .condition-spec-name{padding-inline:3px;white-space:nowrap}
    .fan-configuration-inputs{display:flex;align-items:flex-end;white-space:nowrap}
    .fan-input-set{display:grid;grid-template-columns:78px;gap:9px;position:relative;align-items:end}
    .fan-configuration-inputs.multiple .fan-input-set{grid-template-columns:78px 78px}
    .fan-input-set+.fan-input-set{margin-left:30px}
    .fan-input-set+.fan-input-set::before{content:",";position:absolute;left:-18px;bottom:8px;color:#707070;font-size:16px;line-height:1}
    .fan-input-column{display:flex;flex-direction:column;gap:4px;min-width:0}
    .fan-input-column>span{font-size:13px;color:#242424}
    .fan-input-column input{width:78px}
    .fan-count-custom-control{grid-template-columns:minmax(0,1fr) 32px;gap:4px;width:90px}
    .fan-count-custom-control button{width:32px;min-width:32px}
    .fan-count-custom-control input{min-width:0}
    .condition-card-row input,.condition-card-row select{width:100%}
    .condition-row-actions{display:flex;gap:4px;align-items:center}
    .condition-row-action{width:34px;min-width:34px;height:34px;padding:0;display:grid;place-items:center;font-size:18px;line-height:1}
    .condition-row-action.remove{border-color:#bdbdbd;background:#f3f3f3;color:var(--danger)}
    .condition-field{border:1px solid #d6d6d6;border-radius:8px;padding:9px;background:#fff}
    .condition-head{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:7px}
    .condition-title strong{display:block;font-size:13px;color:#4a4a4a;overflow-wrap:anywhere}
    .chips{display:flex;gap:5px;flex-wrap:wrap;align-items:center}
    .chip{
      display:inline-flex;align-items:center;min-height:22px;border:1px solid #d6d6d6;
      border-radius:8px;background:#f7f7f7;color:#707070;padding:2px 7px;
      font-size:11px;font-weight:500;line-height:1.2;
    }
    .chip.required{border-color:#c6c6c6;background:#f7f7f7;color:#4a4a4a}
    .chip.blocking{border-color:#bdbdbd;background:#f3f3f3;color:var(--danger)}
    .chip.warning{border-color:#c6c6c6;background:#eeeeee;color:var(--warning)}
    .chip.info{border-color:#d6d6d6;background:#f7f7f7;color:var(--blue)}
    .chip.ok{border-color:#c6c6c6;background:#f7f7f7;color:var(--ok)}
    .chip.candidate{border-color:#c6c6c6;background:#f7f7f7;color:var(--warning)}
    .field-status-note{margin-top:6px;color:var(--muted);font-size:12px;font-weight:500}
    .matrix-wrap{overflow:auto;border:1px solid #d6d6d6;border-radius:8px;background:#fff}
    .case-source-reference{display:grid;gap:6px;margin-bottom:10px}
    .case-source-guidance{margin:0;color:#4a4a4a;font-size:12px;font-weight:500;line-height:1.45}
    .case-source-list{display:grid;margin:0;padding:0;list-style:none;border-top:1px solid #e5e5e5}
    .case-source-list li{display:grid;grid-template-columns:minmax(84px,140px) minmax(0,1fr);gap:10px;align-items:baseline;min-width:0;padding:6px 0;border-bottom:1px solid #e5e5e5;font-size:11px;line-height:1.4}
    .case-source-name{color:#242424;font-weight:600;overflow-wrap:anywhere}
    .case-source-details{color:#707070;overflow-wrap:anywhere}
    .case-toolbar{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px}
    table{width:100%;border-collapse:collapse;min-width:540px;font-size:12px}
    .combination-summary{display:flex;gap:7px;flex-wrap:wrap;padding:9px;border:1px solid #d6d6d6;border-radius:8px;background:#f7f7f7;font-size:12px}
    .combination-list{display:grid;gap:8px}
    .combination-card{border:1px solid #d6d6d6;border-radius:8px;background:#fff;padding:10px;display:grid;gap:8px}
    .combination-card-head{display:flex;justify-content:space-between;gap:8px;align-items:center}
    .combination-picker{display:flex;gap:6px;flex-wrap:wrap}
    .combination-picker label{display:inline-flex;flex-direction:row;align-items:center;gap:4px;padding:4px 6px;border:1px solid #d6d6d6;border-radius:6px;background:#f7f7f7;font-size:11px}
    .combination-picker input{width:auto}
    th,td{border-bottom:1px solid #d6d6d6;padding:8px;text-align:left;vertical-align:middle;overflow-wrap:anywhere}
    th{position:sticky;top:0;background:#f7f7f7;color:#4a4a4a;font-weight:600}
    tr.excluded td{color:#8a8a8a;background:#f3f3f3;text-decoration:line-through}
    .empty{border:1px dashed #c6c6c6;border-radius:8px;background:#f7f7f7;color:var(--muted);padding:12px;font-size:13px;line-height:1.45}
    .common-block{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
    .review-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-bottom:10px}
    .metric{border:1px solid #d6d6d6;border-radius:8px;background:#fff;padding:9px}
    .metric span{display:block;color:var(--muted);font-size:11px;font-weight:500}
    .metric strong{display:block;margin-top:3px;font-size:15px}
    .issue-list{display:flex;flex-direction:column;gap:7px}
    .issue{border:1px solid #d6d6d6;border-radius:8px;padding:9px;background:#fff;font-size:12px;line-height:1.45}
    .issue.blocking{border-color:#bdbdbd;background:#f3f3f3}
    .issue.warning{border-color:#c6c6c6;background:#f7f7f7}
    .issue.info{border-color:#d6d6d6;background:#f7f7f7}
    .issue button{margin-top:7px}
    .issue code{display:block;margin-top:3px;color:#707070;font-size:11px;white-space:normal}
    .inline-issue{display:none;margin-top:4px;font-size:11px;line-height:1.35}
    .field-touched .inline-issue{display:block}
    .field-highlight{outline:3px solid rgba(92,92,92,.45);outline-offset:3px;border-radius:8px}
    .draft-output{margin-top:10px;border:1px solid #d6d6d6;border-radius:8px;background:#f7f7f7;padding:10px;white-space:pre-wrap;font-size:12px;line-height:1.5}
    .preview-doc{display:grid;gap:10px}
    .preview-section{border:1px solid #d6d6d6;border-radius:8px;background:#fff;padding:10px}
    .preview-section h4{margin:0 0 8px;font-size:13px;color:#4a4a4a}
    .preview-kv{display:grid;grid-template-columns:140px minmax(0,1fr);gap:8px;padding:5px 0;border-top:1px solid #e5e5e5;font-size:12px}
    .preview-kv:first-of-type{border-top:0}
    .preview-kv span:first-child{color:var(--muted);font-weight:500}
    .preview-table{width:100%;border-collapse:collapse;font-size:12px}
    .preview-table caption{text-align:left;padding:7px 0;font-weight:600;color:#4a4a4a}
    .chat{display:grid;grid-template-rows:auto minmax(0,1fr) auto}
    .agent-dock{min-width:0;transition:opacity .18s ease,transform .18s ease}
    .panel-resizer{display:none}
    .layout.agent-hidden{grid-template-columns:minmax(0,1fr)}
    .layout.agent-hidden .agent-dock{display:none}
    .chat-head{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:12px;border-bottom:1px solid var(--line);background:#f7f7f7}
    .chat-head-actions{display:flex;align-items:center;gap:7px}
    .stage-assist{display:grid;gap:8px}
    .stage-assist-title{display:block;font-size:15px;color:#4a4a4a}
    .stage-assist-copy{margin:0;color:#707070;font-size:12.5px;line-height:1.45}
    .stage-assist-actions{display:grid;gap:6px}
    .stage-assist-action{width:100%;min-height:34px;text-align:left;background:#fff;border-color:#d6d6d6;color:#4a4a4a;font-weight:500;white-space:normal}
    .stage-assist-action:hover{border-color:#707070;background:#f7f7f7}
    .chat-log{min-height:0;overflow:auto;padding:12px;background:#eeeeee}
    .msg{max-width:92%;margin-bottom:9px;border-radius:8px;padding:9px 10px;font-size:13px;line-height:1.45;white-space:pre-wrap}
    .msg.assistant{border:1px solid #d6d6d6;background:#fff}
    .msg.user{margin-left:auto;background:var(--brand);color:#fff}
    .rec-list{display:flex;flex-direction:column;gap:6px;margin-top:8px}
    .rec-list button{text-align:left;background:#fff}
    .proposal-card{display:grid;gap:8px}
    .proposal-card strong{font-size:13px;color:#4a4a4a}
    .proposal-list{display:grid;gap:5px;margin:0;padding:0;list-style:none}
    .proposal-list li{border:1px solid #d6d6d6;border-radius:8px;background:#fff;padding:7px 8px}
    .proposal-actions{display:flex;gap:8px;flex-wrap:wrap}
    .proposal-actions button{min-width:74px}
    .quick-action-card{
       border:1px solid #d6d6d6;
      border-radius:8px;
       background:#f7f7f7;
      padding:10px;
      white-space:normal;
    }
    .quick-action-title{display:block;margin-bottom:2px;color:var(--brand-strong)}
    .quick-action-copy{line-height:1.45}
    .quick-actions button{
      min-height:34px;
      background:#fff;
       border-color:#d6d6d6;
      color:var(--brand-strong);
      font-weight:500;
    }
    .loading-message{display:flex;align-items:center;gap:8px}
    .spinner{
      width:16px;height:16px;border-radius:50%;
       border:2px solid #d6d6d6;border-top-color:var(--brand);
      animation:spin .8s linear infinite;flex:0 0 auto;
    }
    @keyframes spin{to{transform:rotate(360deg)}}
    .chat-input{border-top:1px solid var(--line);background:#f7f7f7;padding:10px}
    .chat-row{display:flex;gap:8px;align-items:flex-end}
    .chat-row textarea{min-height:64px;max-height:150px}
    .chat-row button{align-self:stretch}
    .orchestrator-readonly{margin-top:6px;border-top:1px solid #d6d6d6;padding-top:6px;color:#707070;font-size:11px;line-height:1.45}
    .orchestrator-proposal{margin-top:6px;border:1px solid #c6c6c6;border-radius:7px;background:#f7f7f7;padding:7px;color:#4a4a4a;font-size:12px;line-height:1.45}
    .submit-modal{
      position:fixed;inset:0;display:grid;place-items:center;
       background:rgba(0,0,0,.28);z-index:20;padding:20px;
    }
    .submit-dialog{
       width:min(420px,100%);border:1px solid #d6d6d6;border-radius:8px;
       background:#fff;box-shadow:0 18px 42px rgba(0,0,0,.10);
      padding:22px;text-align:center;
    }
    .submit-dialog strong{display:block;font-size:20px;color:#4a4a4a;margin-bottom:14px}
    .submit-modal[hidden]{display:none}
    .context-change-actions{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin-top:14px}
    @media (max-width:1280px) and (min-width:1040px){
      .layout{grid-template-columns:minmax(0,1fr) 320px}
    }
    @media (max-width:1180px){
      .topbar{height:auto;grid-template-columns:1fr;align-items:start}
      .hero-row,.condition-grid,.heat-exchanger-grid,.review-grid,.prep-head,.prep-quick-grid,.condition-primary-grid,.condition-environment-grid{grid-template-columns:1fr}
      .condition-primary-grid .condition-card-type-operating{width:100%}
      .grid,.grid.compact,.grid.two,.request-basic-grid,.request-detail-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
      .prep-actions{justify-content:flex-start}
    }
    @media (max-width:1039px){
      body{overflow:auto;overflow-x:hidden}
      .layout{height:auto;min-height:calc(100vh - 48px);grid-template-columns:minmax(0,1fr)}
      .agent-dock{
        position:fixed;z-index:14;right:12px;bottom:12px;width:min(340px,calc(100vw - 24px));
        height:min(620px,calc(100vh - 24px));min-height:440px;box-shadow:0 18px 42px rgba(0,0,0,.10);
      }
      .layout.agent-hidden .agent-dock{display:grid;opacity:0;pointer-events:none;transform:translateX(calc(100% + 24px));visibility:hidden}
    }
    @media (max-width:720px){
      .case-source-list li{grid-template-columns:minmax(76px,110px) minmax(0,1fr);gap:7px}
      .screen-map{grid-template-columns:repeat(3,minmax(0,1fr));min-height:0}
      .screen-map-item{min-height:82px}
      .screen-map-item:nth-child(4){padding-left:18px;border-radius:12px 0 0 12px;clip-path:polygon(0 0,calc(100% - 18px) 0,100% 50%,calc(100% - 18px) 100%,0 100%)}
      .screen-map-item:nth-child(3){padding-right:18px;border-radius:0 12px 12px 0;clip-path:polygon(0 0,100% 0,100% 100%,0 100%,18px 50%)}
      .grid,.grid.compact,.grid.two,.request-basic-grid,.request-detail-grid{grid-template-columns:1fr}
    }
    /* T2-01A: completed Shell, SCREEN-01/02, and Agent Dock share the design-lock surface system. */
    .topbar,.workspace-bar,.panel,.section,.request-prep-card,.prep-step,.prep-summary,.context-chip-bar,.context-lock-gate,.gate{border-color:var(--line);background:var(--paper)}
    .topbar{border-bottom-color:var(--line);background:var(--paper)}
    .brand-mark{background:var(--brand)}
    .workspace-bar{box-shadow:none}
    .panel{border-radius:10px;box-shadow:var(--shadow)}
    .hero,.section-head{background:var(--soft)}
    .hero h2,.prep-head h3,.prep-step-title strong,.section h3,.workspace-bar-copy strong,.screen-heading span{color:var(--ink)}
    .request-prep-card,.section{border-radius:10px}
    .prep-head{padding:11px 13px;border-bottom-color:var(--line);background:var(--soft)}
    .prep-summary,.context-chip-bar{background:#f7f7f7;border-color:#d6d6d6}
    .context-lock-gate,.gate{border-color:#d6d6d6;background:var(--soft);color:var(--ink)}
    .prep-choice,.prep-choice.selected{border-color:#d6d6d6;background:var(--paper);color:var(--ink)}
    .prep-choice.selected{border-color:var(--brand);background:#eeeeee;color:var(--brand)}
    .section-head{min-height:42px;padding:8px 11px}
    .section-body{border-top-color:var(--line);padding:11px 13px}
    .chip{border-color:var(--line);background:var(--soft);color:var(--muted)}
    .chip.info{border-color:#d6d6d6;background:#f7f7f7;color:var(--brand)}
    .chip.required{border-color:#c6c6c6;background:#f7f7f7;color:var(--warning)}
    .title-icon{border-color:#d6d6d6;border-radius:7px;background:#eeeeee;color:var(--brand)}
    .screen-heading{margin:0 0 8px;font-size:22px;font-weight:600;line-height:1.15;color:var(--muted)}
    .screen-heading-code{font-size:12px;font-weight:500;color:var(--muted)!important}
    .screen-action-bar{position:static;display:flex;justify-content:space-between;gap:10px;margin-top:16px;padding:10px 0;border-top:1px solid var(--line);background:var(--paper)}
    .screen-action-bar button{min-width:136px}
    .agent-dock{background:#eeeeee;border-color:#d6d6d6}
    .chat-head,.chat-input{background:#f7f7f7;border-color:#d6d6d6}
    .chat-log{background:#eeeeee}
    /* SCREEN-01~06 workspace-only visual surface; Agent Dock is a sibling of .workspace-shell. */
    .workspace-shell{
      --request-workspace-font:"Noto Sans KR","Malgun Gothic","Segoe UI",sans-serif;
      --request-workspace-page:#f3f3f3;
      --request-workspace-content:#eeeeee;
      --request-workspace-surface:#ffffff;
      --request-workspace-border:#d6d6d6;
      --request-workspace-ink:#4a4a4a;
      --request-workspace-muted:#707070;
      --request-workspace-accent:#707070;
      --request-workspace-radius:10px;
      --request-workspace-shadow:0 2px 8px rgba(0,0,0,.08);
      --request-workspace-card-content-padding:10px;
      --request-workspace-card-section-gap:20px;
      font-family:var(--request-workspace-font);
      color:var(--request-workspace-ink);
    }
    .workspace-shell .workspace-bar{position:relative;border-color:var(--request-workspace-border);border-radius:var(--request-workspace-radius);background:var(--request-workspace-surface);box-shadow:var(--request-workspace-shadow)}
    .workspace-shell .workspace-request-summary{display:flex;align-items:center;gap:10px;min-width:0}
    .workspace-shell .workspace-title-block,.workspace-shell .workspace-number-block{display:flex;flex-direction:column;gap:2px;min-width:0}
    .workspace-shell .workspace-title-block{flex:1}
    .workspace-shell .workspace-number-block{border-left:1px solid var(--request-workspace-border)}
    .workspace-shell .workspace-bar-label{color:var(--request-workspace-muted);font-size:12px;font-weight:500}
    .workspace-shell .workspace-bar h2,.workspace-shell .workspace-request-number{margin:0;color:var(--request-workspace-ink);font-size:15px;font-weight:600;line-height:1.2}
    .workspace-shell .workspace-request-number{font-size:12px}
    .workspace-shell .workspace-bar-status{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);clip-path:inset(50%);white-space:nowrap}
    .workspace-shell .main{border-color:var(--request-workspace-border);background:var(--request-workspace-content);box-shadow:var(--request-workspace-shadow)}
    .workspace-shell .hero[hidden]{display:none}
    .workspace-shell .workspace{background:var(--request-workspace-content)}
    .workspace-shell .workspace-form{font-family:var(--request-workspace-font)}
    .workspace-shell .workspace-form .screen-heading{color:var(--request-workspace-muted)}
    .workspace-shell .workspace-form .screen-heading span{color:var(--request-workspace-ink)}
    .workspace-shell .screen-group > .section,
    .workspace-shell .workspace-form.screen-group > .section,
    .workspace-shell .screen-group > .request-prep-card{border-color:var(--request-workspace-border);border-radius:var(--request-workspace-radius);background:var(--request-workspace-surface);box-shadow:var(--request-workspace-shadow)}
    .workspace-shell .screen-group > .section > .section-head,
    .workspace-shell .workspace-form.screen-group > .section > .section-head{background:var(--request-workspace-surface);border-color:var(--request-workspace-border)}
    .workspace-shell .screen-group > .section > .section-body,
    .workspace-shell .workspace-form.screen-group > .section > .section-body{border-color:var(--request-workspace-border)}
    .workspace-shell .condition-input-screen > #section-conditions{
      margin-bottom:0;
      border:0;
      border-radius:0;
      background:transparent;
      box-shadow:none;
      overflow:visible;
    }
    .workspace-shell .condition-input-screen > #section-conditions > .section-body{padding:0;border:0}
    .workspace-shell .screen-group > .section > .section-head h3,
    .workspace-shell .workspace-form.screen-group > .section > .section-head h3{color:var(--request-workspace-ink);font-weight:600}
    .workspace-shell .section-title-icon{width:20px;height:20px;display:inline-grid;flex:0 0 20px;place-items:center;color:var(--request-workspace-accent)}
    .workspace-shell .section-title-icon svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-linecap:round;stroke-linejoin:round;stroke-width:1.8}
    .workspace-shell .workspace-form label{color:#242424;font-weight:500}
    .workspace-shell .workspace-form input,.workspace-shell .workspace-form select,.workspace-shell .workspace-form textarea{font-family:var(--request-workspace-font);font-weight:400;color:#242424;background-color:var(--request-workspace-surface);border-color:#d6d6d6;border-radius:7px;box-shadow:none}
    .workspace-shell .screen-group:is([data-screen="SCREEN-02"],[data-screen="SCREEN-03"],[data-screen="SCREEN-04"]) :is(label,.field-label){font-family:var(--request-workspace-font);font-size:13px;font-style:normal;font-weight:400!important;line-height:1.45;letter-spacing:normal;color:#242424}
    .workspace-shell .screen-group:is([data-screen="SCREEN-02"],[data-screen="SCREEN-03"],[data-screen="SCREEN-04"]) :is(input,select,textarea,.analysis-result-guidance){font-family:var(--request-workspace-font);font-size:13px;font-style:normal;font-weight:400!important;line-height:1.45;letter-spacing:normal;color:#242424}
    .workspace-shell .workspace-form input:focus-visible,.workspace-shell .workspace-form select:focus-visible,.workspace-shell .workspace-form textarea:focus-visible{outline-color:var(--request-workspace-accent)}
    .workspace-shell .workspace-form button{font-family:var(--request-workspace-font);font-weight:500;border-color:#d6d6d6;background-color:var(--request-workspace-surface);color:var(--request-workspace-ink);box-shadow:none}
    .workspace-shell .workspace-form button.primary{border-color:var(--request-workspace-accent);background-color:var(--request-workspace-accent);color:#fff}
    .workspace-shell .workspace-form table{color:var(--request-workspace-ink);border-color:var(--request-workspace-border)}
    .workspace-shell .request-content-screen > #section-overview{background:var(--request-workspace-surface)}
    .workspace-shell .request-content-screen > #section-overview .analysis-result-guidance{border-color:#d6d6d6;background:#f7f7f7}
    .workspace-shell .screen-action-bar{border-color:var(--request-workspace-border);background:transparent}
    .workspace-shell .screen-group:is([data-screen="SCREEN-02"],[data-screen="SCREEN-03"],[data-screen="SCREEN-04"],[data-screen="SCREEN-05"]) > .screen-action-bar{margin-top:20px;padding:6px 0;border-top:0}
    .workspace-shell .screen-group:is([data-screen="SCREEN-02"],[data-screen="SCREEN-03"],[data-screen="SCREEN-04"],[data-screen="SCREEN-05"]) > .screen-action-bar button{min-height:34px}
    .workspace-shell .screen-map{gap:0}
    .workspace-shell .screen-map{background:#fff;box-shadow:var(--request-workspace-shadow)}
    .workspace-shell .screen-map-item{background:#fff;color:#707070}
    .workspace-shell .screen-map-item:hover:not([aria-disabled="true"]){background:#eeeeee;color:var(--request-workspace-ink)}
    .workspace-shell .screen-map-item[aria-current="page"]{background:var(--request-workspace-accent);color:#fff}
    .workspace-shell .screen-map-item:focus-visible{outline-color:rgba(92,92,92,.48)}
    .topbar .subtitle{display:none}
    .workspace-shell .workspace-bar{min-height:64px;padding:8px 14px}
    .workspace-shell .screen-map{min-height:64px}
    .workspace-shell .screen-map-item{padding-top:5px;padding-bottom:5px}
    .workspace-shell .screen-map-item:not(:first-child){margin-left:-18px}
    .workspace-shell .workspace{padding-top:6px;padding-bottom:6px}
    .workspace-shell .request-content-screen .screen-heading{margin-bottom:8px;padding:3px 0;font-size:21px}
    .workspace-shell .screen-heading-code{display:none}
    .workspace-shell .screen-description{margin:0 0 7px;color:var(--request-workspace-muted);font-size:13px;line-height:1.35}
    .workspace-shell .geometry-screen .screen-heading,
    .workspace-shell .stage-static-screen .screen-heading,
    .workspace-shell .workspace-form[data-screen="SCREEN-06"] .screen-heading{margin-bottom:8px;padding:3px 0;font-size:21px}
    .workspace-shell .geometry-screen .section-head h3,
    .workspace-shell .stage-static-screen .section-head h3,
    .workspace-shell .workspace-form[data-screen="SCREEN-06"] .section-head h3{color:var(--request-workspace-accent);font-size:15px;font-weight:600}
    .workspace-shell .geometry-screen .chev,
    .workspace-shell .stage-static-screen .chev,
    .workspace-shell .workspace-form[data-screen="SCREEN-06"] .chev{display:none}
    .workspace-shell .geometry-screen .section-meta,
    .workspace-shell .stage-static-screen .section-meta,
    .workspace-shell .workspace-form[data-screen="SCREEN-06"] .section-meta{display:none}
    .workspace-shell .product-panel{border-color:var(--request-workspace-border);background:#f7f7f7}
    .workspace-shell .product-panel-head strong,
    .workspace-shell .product-card-head h4,
    .workspace-shell .condition-group-head h3{color:var(--request-workspace-accent)}
    .workspace-shell .product-panel-copy{color:var(--request-workspace-muted)}
    .workspace-shell .product-card{border-color:var(--request-workspace-border);box-shadow:0 1px 3px rgba(0,0,0,.05)}
    .workspace-shell .condition-group{border-color:var(--request-workspace-border);background:var(--request-workspace-surface);box-shadow:var(--request-workspace-shadow)}
    .workspace-shell .condition-group-head{border-bottom-color:#e5e5e5;background:#f7f7f7}
    .workspace-shell .case-toolbar{border-color:var(--request-workspace-border);background:#f7f7f7}
    .workspace-shell .preview-actions{border-top:1px solid #e5e5e5;padding-top:10px}
    .workspace-shell .request-content-screen > .section{margin-bottom:var(--request-workspace-card-section-gap)}
    .workspace-shell .request-content-screen > .section > .section-head{min-height:36px;padding-top:6px;padding-bottom:6px}
    .workspace-shell .request-content-screen > .section > .section-body{padding-top:7px;padding-bottom:var(--request-workspace-card-content-padding);border-top-color:#e5e5e5}
    .workspace-shell .request-content-screen > .section > .section-head h3{font-size:15px}
    .workspace-shell .geometry-screen > .section{border-color:var(--request-workspace-border);border-radius:var(--request-workspace-radius);background:var(--request-workspace-surface);box-shadow:var(--request-workspace-shadow)}
    .workspace-shell .geometry-screen > .section{margin-bottom:var(--request-workspace-card-section-gap)}
    .workspace-shell .geometry-screen > .section > .section-head{min-height:36px;padding-top:6px;padding-bottom:6px;background:var(--request-workspace-surface);border-color:var(--request-workspace-border)}
    .workspace-shell .geometry-screen > .section > .section-body{padding-top:10px;padding-bottom:var(--request-workspace-card-content-padding);border-top:0;border-color:var(--request-workspace-border)}
    .workspace-shell .geometry-screen > .section > .section-head h3{color:var(--request-workspace-accent);font-size:15px;font-weight:600}
    /* Field-group headings use the requester-info type scale and the condition-card emphasis. */
    .workspace-shell .request-content-screen > .section > .section-head,
    .workspace-shell .geometry-screen > .section > .section-head,
    .workspace-shell .stage-static-screen[data-screen="SCREEN-05"] > .section > .section-head,
    .workspace-shell .condition-group-head{background:#f7f7f7}
    .workspace-shell .condition-group-head{min-height:36px;padding:6px 11px}
    .workspace-shell .stage-static-screen[data-screen="SCREEN-05"] > #section-case > .section-head{min-height:36px;padding:6px 11px}
    .workspace-shell .request-content-screen > .section > .section-head h3,
    .workspace-shell .geometry-screen > .section > .section-head h3,
    .workspace-shell .stage-static-screen[data-screen="SCREEN-05"] > .section > .section-head h3,
    .workspace-shell .condition-group-head h3{font-family:var(--request-workspace-font);font-size:15px;font-weight:600;color:var(--request-workspace-accent)}
    .workspace-shell .condition-group-head-actions button{min-height:24px;height:24px;padding:2px 7px}
    .workspace-shell .stage-static-screen[data-screen="SCREEN-05"] > #section-case > .section-head > .case-section-actions{display:flex;align-items:center;margin-left:auto}
    .workspace-shell .stage-static-screen[data-screen="SCREEN-05"] > #section-case > .section-head > .case-section-actions button{min-height:24px;height:24px;padding:2px 7px}
    .workspace-shell .request-content-screen input,.workspace-shell .request-content-screen select{min-height:34px}
    .workspace-shell .geometry-screen input{min-height:34px}
    .workspace-shell .request-content-screen textarea{min-height:52px}
    .layout{grid-template-areas:"workspace-bar workspace-bar" "workspace-content agent";grid-template-rows:auto minmax(0,1fr)}
    .workspace-shell{display:contents}
    .workspace-bar{grid-area:workspace-bar}
    .workspace-content{grid-area:workspace-content;min-width:0;min-height:0;display:grid;grid-template-rows:auto auto;gap:10px;overflow:visible}
    .workspace-content{align-content:start;row-gap:10px}
    .agent-dock{grid-area:agent;height:100%}
    .layout.agent-hidden{grid-template-areas:"workspace-bar" "workspace-content";grid-template-rows:auto minmax(0,1fr)}
    .workspace-shell .workspace-request-summary{display:flex;align-items:center;gap:0;width:100%}
    .workspace-shell .workspace-title-summary{display:flex;align-items:center;gap:10px;min-width:0}
    .workspace-shell .workspace-title-block{min-width:0}
    .workspace-shell .workspace-bar h2{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .workspace-shell .workspace-number-block{margin-left:16px;padding-left:16px}
    .workspace-shell .main{overflow:visible}
    .workspace-shell .main{background:var(--request-workspace-surface);border-radius:var(--request-workspace-radius);box-shadow:var(--request-workspace-shadow)}
    .workspace-shell .workspace{background:var(--request-workspace-surface);border-radius:var(--request-workspace-radius)}
    .workspace-shell .screen-map-number{font-size:24px;font-weight:600}
    .workspace-shell .screen-map-label{font-size:12px;font-weight:500;line-height:1.2}
    .workspace-shell .request-content-screen{background:var(--request-workspace-surface)}
    .workspace-shell .request-content-screen > .section{box-shadow:var(--request-workspace-shadow)}
    .workspace-shell .request-content-screen > .section > .section-body{border-top:0}
    .workspace-shell .request-content-screen > .section > .section-head h3{color:var(--request-workspace-accent);font-weight:600}
    .workspace-shell .request-content-screen .analysis-result-guidance-icon{display:none}
    .workspace-shell .screen-map{overflow:hidden;border-radius:10px}
    .workspace-shell .screen-map-item[aria-current="page"]{z-index:2}
    @media (max-width:1039px){
      .layout{grid-template-areas:"workspace-bar" "workspace-content";grid-template-rows:auto auto}
      .product-table-row{grid-template-columns:minmax(70px,.55fr) minmax(150px,1fr) minmax(220px,1.8fr) 34px}
    }
    /* Desktop height contract: SCREEN-03 with four product rows defines the common panel maximum. */
    @media (min-width:1040px){
      body{display:grid;grid-template-rows:auto minmax(0,1fr);overflow-y:hidden}
      .layout{
        --stage-panel-reference-height:742px;
        height:100%;max-height:calc(var(--stage-panel-reference-height) + 100px);min-height:0;
        grid-template-columns:minmax(0,2fr) 12px minmax(0,1fr);
        grid-template-areas:"workspace-bar workspace-bar workspace-bar" "workspace-content panel-resizer agent";
        grid-template-rows:auto minmax(0,1fr);
        column-gap:0;row-gap:12px;
      }
      .panel-resizer{
        position:relative;z-index:6;grid-area:panel-resizer;display:grid;place-items:center;
        justify-self:center;width:20px;min-width:20px;height:100%;margin:0 -4px;
        cursor:col-resize;touch-action:none;user-select:none;
      }
      .panel-resizer::before{content:"";width:2px;height:100%;border-radius:999px;background:#d6d6d6;transition:background .15s ease,width .15s ease}
      .panel-resizer:hover::before,.panel-resizer.is-dragging::before{width:4px;background:#707070}
      body.panel-resizing{cursor:col-resize;user-select:none}
      .layout.agent-hidden{grid-template-columns:minmax(0,1fr);grid-template-areas:"workspace-bar" "workspace-content"}
      .layout.agent-hidden .panel-resizer{display:none}
      .workspace-content{height:100%;grid-template-rows:auto minmax(0,1fr);overflow:hidden}
      .workspace-shell .main{min-height:0;overflow:hidden}
      .workspace-shell .workspace{height:100%;min-height:0;overflow-y:auto;overscroll-behavior:contain}
      .agent-dock{height:100%;min-height:0}
      .chat-log{min-height:0;overflow-y:auto;overscroll-behavior:contain}
      .chat-input{position:relative;z-index:1}
    }
    .msg.assistant,.proposal-card,.proposal-list li{border-color:var(--line);background:var(--paper)}
    .msg.user{background:#e5e5e5;color:var(--ink)}
    .stage-assist-title,.proposal-card strong{color:var(--ink)}
    .stage-assist-action,.quick-actions button{border-color:#d6d6d6;background:var(--paper);color:var(--ink)}
    .quick-action-card{border-color:#d6d6d6;background:#f7f7f7}
    .quick-action-title{color:var(--brand-strong)}
  </style>
</head>
<body>
  <header class="topbar" data-shell="GlobalHeader">
    <div class="brand">
      <div class="brand-mark">CAE</div>
      <div>
        <h1>해석 의뢰 Agent</h1>
        <div class="subtitle">__APP_VERSION__</div>
      </div>
    </div>
    <div class="top-actions" aria-label="request actions">
      <button class="ghost" id="agentOpenBtn" type="button" aria-controls="agentDock" aria-expanded="false" hidden>Agent 열기</button>
      <label class="rag-toggle" hidden aria-hidden="true"><input type="checkbox" id="ragToggle" /> RAG</label>
      <button class="primary" id="newRequestBtn" type="button">새 의뢰 시작</button>
    </div>
  </header>

  <main class="layout">
    <div class="workspace-shell" data-shell="MainWorkspace">
      <div class="workspace-bar" data-shell="WorkspaceBar">
        <div class="workspace-request-summary">
          <div class="workspace-title-summary">
            <div class="workspace-title-block">
              <span class="workspace-bar-label">의뢰 제목</span>
              <h2 id="heroTitle">해석 의뢰를 시작해 주세요.</h2>
            </div>
          </div>
          <div class="workspace-number-block">
            <span class="workspace-bar-label">해석 의뢰 번호</span>
            <p class="workspace-request-number" id="requestNoDisplay">해석의뢰 번호: -</p>
          </div>
        </div>
        <div class="workspace-bar-status" id="screenNavigationStatus" role="status" aria-live="polite"></div>
      </div>
      <div class="workspace-content">
      <nav class="step-navigation" data-shell="StepNavigation" aria-label="6개 화면군">
        <div class="screen-map" aria-label="화면 순서">
          <span class="screen-map-item" data-screen="SCREEN-01"><span class="screen-map-number">01</span><span class="screen-map-label"><span>의뢰 대상·시작</span></span></span>
          <span class="screen-map-item" data-screen="SCREEN-02"><span class="screen-map-number">02</span><span class="screen-map-label"><span class="screen-map-lock" aria-hidden="true"><svg viewBox="0 0 16 16"><rect x="3" y="7" width="10" height="7" rx="1.5"></rect><path d="M5 7V5a3 3 0 0 1 6 0v2"></path></svg></span><span>요청 내용</span></span></span>
          <span class="screen-map-item" data-screen="SCREEN-03"><span class="screen-map-number">03</span><span class="screen-map-label"><span class="screen-map-lock" aria-hidden="true"><svg viewBox="0 0 16 16"><rect x="3" y="7" width="10" height="7" rx="1.5"></rect><path d="M5 7V5a3 3 0 0 1 6 0v2"></path></svg></span><span>해석 제품</span></span></span>
          <span class="screen-map-item" data-screen="SCREEN-04"><span class="screen-map-number">04</span><span class="screen-map-label"><span class="screen-map-lock" aria-hidden="true"><svg viewBox="0 0 16 16"><rect x="3" y="7" width="10" height="7" rx="1.5"></rect><path d="M5 7V5a3 3 0 0 1 6 0v2"></path></svg></span><span>해석 조건</span></span></span>
          <span class="screen-map-item" data-screen="SCREEN-05"><span class="screen-map-number">05</span><span class="screen-map-label"><span class="screen-map-lock" aria-hidden="true"><svg viewBox="0 0 16 16"><rect x="3" y="7" width="10" height="7" rx="1.5"></rect><path d="M5 7V5a3 3 0 0 1 6 0v2"></path></svg></span><span>Case Matrix</span></span></span>
          <span class="screen-map-item" data-screen="SCREEN-06"><span class="screen-map-number">06</span><span class="screen-map-label"><span>전체 확인·Preview·Word</span></span></span>
        </div>
      </nav>

    <section class="panel main" data-shell="MainWorkspaceContent">
      <div class="hero" hidden>
       <div class="hero-row">
          <button id="recommendBtn" hidden aria-hidden="true" type="button">해석유형 추천</button>
        </div>
        <div class="candidate-notice" id="candidateNotice"></div>
      </div>
      <div class="workspace">
        <div class="workspace-tab active" id="tab-write">
          <div class="workspace-form" id="formView">
          <section class="screen-group" data-screen="SCREEN-01" aria-labelledby="screen01Heading">
          <h2 class="screen-heading" id="screen01Heading"><span class="screen-heading-code">SCREEN-01</span> <span>의뢰 대상·시작</span></h2>
          <section class="request-prep-card" id="requestPrepCard">
            <div class="prep-head">
              <div>
                <h3>해석 대상 제품 선택</h3>
                <p class="prep-guidance"><span class="prep-guidance-line">이번 해석이 적용될 제품의 사업부, 제품군, Platform을 선택해 주세요. 요청자의 소속 조직과 관계없이 <span class="prep-guidance-emphasis">해석 대상 제품을 기준으로 선택</span>합니다.</span><span class="prep-guidance-line prep-guidance-next"><span class="prep-guidance-emphasis">제품 분류</span>를 선택한 후 <span class="prep-guidance-emphasis">해석유형</span>을 지정합니다.</span></p>
              </div>
              <div class="prep-actions"><button class="ghost" id="contextChangeBtn" type="button" hidden>의뢰대상 변경</button><button class="primary" id="nextRequestContentBtn" type="button" data-screen-action="SCREEN-02" hidden>다음: 요청 내용</button></div>
            </div>
            <div class="prep-body">
              <div class="prep-flow" id="guidedPrepFlow">
                <div class="prep-step" data-prep-step="business_unit">
                  <div class="prep-step-title"><strong>1. 어느 사업부 제품인가요?</strong><span class="chip info" id="prepBusinessStatus">선택 필요</span></div>
                  <div class="prep-choice-grid" id="prepBusinessChoices"></div>
                </div>
                <div class="prep-step" data-prep-step="product_group">
                  <div class="prep-step-title"><strong>2. 제품군 선택</strong><span class="chip info" id="prepProductStatus">사업부 기준</span></div>
                  <div class="prep-choice-grid" id="prepProductChoices"></div>
                </div>
                <div class="prep-step" data-prep-step="platform">
                  <div class="prep-step-title"><strong>3. Platform 선택</strong><span class="chip info" id="prepPlatformStatus">제품군 기준</span></div>
                  <div class="prep-choice-grid" id="prepPlatformChoices"></div>
                </div>
                <div class="prep-step" data-prep-step="analysis_type">
                  <div class="prep-step-title"><strong>4. 해석유형 선택</strong><span class="chip info" id="prepAnalysisStatus">우선 표시</span></div>
                  <div class="prep-choice-grid" id="prepAnalysisChoices"></div>
                </div>
              </div>
              <div class="prep-flow active" id="quickPrepFlow">
                <div class="prep-quick-grid">
                  <label>사업부<select id="quickBusinessUnitSelect"></select></label>
                  <label>제품군<select id="quickProductGroupSelect"></select><span class="prep-custom-control" id="quickProductGroupCustom" hidden><input id="quickProductGroupCustomInput" aria-label="제품군 직접 입력" /><button id="quickProductGroupRestoreBtn" type="button" title="제품군 드롭다운으로 돌아가기" aria-label="제품군 드롭다운으로 돌아가기">↩</button></span></label>
                  <label>Platform<select id="quickPlatformSelect"></select><span class="prep-custom-control" id="quickPlatformCustom" hidden><input id="quickPlatformCustomInput" aria-label="Platform 직접 입력" /><button id="quickPlatformRestoreBtn" type="button" title="Platform 드롭다운으로 돌아가기" aria-label="Platform 드롭다운으로 돌아가기">↩</button></span></label>
                  <label>해석유형<select id="quickAnalysisTypeSelect"></select></label>
                </div>
              </div>
              <div class="prep-summary" id="prepSelection">
                <strong>선택한 조합</strong>
                <div class="combo">선택 대기</div>
                <div class="note">선택을 확정하면 맞춤 입력항목이 준비됩니다.</div>
                <div class="prep-summary-actions">
                  <button class="primary" id="prepStartBtn" type="button">의뢰서 작성 시작</button>
                </div>
              </div>
            </div>
          </section>

          <section class="context-chip-bar" id="contextChipBar" hidden>
            <div>
              <div class="context-chip-list" id="contextChipList"></div>
              <div class="context-chip-copy">이 조합 기준으로 입력항목이 준비되었습니다.</div>
            </div>
          </section>

          </section>

          <section class="screen-group request-content-screen" data-screen="SCREEN-02" aria-labelledby="screen02Heading">
          <h2 class="screen-heading" id="screen02Heading"><span class="screen-heading-code">SCREEN-02</span> <span>요청 내용</span></h2>
          <p class="screen-description">기본정보와 해석 요청 배경, 확인하고 싶은 내용을 작성합니다.</p>
          <section class="section open" id="section-basic" data-section="basic_info">
            <div class="section-head">
              <div class="section-title"><h3>의뢰자 정보</h3></div>
              <div class="section-meta" id="meta-basic_info" hidden aria-hidden="true"></div>
            </div>
            <div class="section-body">
              <div class="grid request-basic-grid">
                <label>사업부<select data-dropdown-path="basic_info.division"></select><span class="prep-custom-control dropdown-custom-control" data-dropdown-custom-path="basic_info.division" hidden><input class="custom-input" data-path="basic_info.division" aria-label="사업부 직접 입력" /><button type="button" data-dropdown-restore-path="basic_info.division" title="사업부 드롭다운으로 돌아가기" aria-label="사업부 드롭다운으로 돌아가기">↩</button></span></label>
                <label>부서<input data-path="basic_info.department" /></label>
                <label>요청자<input data-path="basic_info.requester_name" /></label>
                <label>직급<select data-dropdown-path="basic_info.requester_role"></select><span class="prep-custom-control dropdown-custom-control" data-dropdown-custom-path="basic_info.requester_role" hidden><input class="custom-input" data-path="basic_info.requester_role" aria-label="직급 직접 입력" /><button type="button" data-dropdown-restore-path="basic_info.requester_role" title="직급 드롭다운으로 돌아가기" aria-label="직급 드롭다운으로 돌아가기">↩</button></span></label>
              </div>
            </div>
          </section>

          <section class="section open" id="section-request-basic">
            <div class="section-head">
              <div class="section-title"><h3>의뢰 기본 정보</h3></div>
            </div>
            <div class="section-body">
              <div class="grid request-basic-grid">
                <div class="undecided-field">
                  <label for="projectNameInput">프로젝트명(PMS)</label>
                  <div class="undecided-combobox" data-undecided-combobox>
                    <input id="projectNameInput" data-path="analysis_overview.project_name" data-undecided-input role="combobox" aria-autocomplete="none" aria-haspopup="listbox" aria-controls="projectNameMenu" aria-expanded="false" autocomplete="off" />
                    <button class="undecided-combobox-toggle" type="button" data-undecided-toggle aria-label="프로젝트명 입력 방식 선택" aria-controls="projectNameMenu" aria-expanded="false"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 9 5 5 5-5"></path></svg></button>
                    <div class="undecided-combobox-menu" id="projectNameMenu" data-undecided-menu role="listbox" aria-label="프로젝트명 입력 방식" hidden>
                      <button class="undecided-combobox-option" type="button" role="option" data-undecided-mode="custom" aria-selected="true">직접 입력</button>
                      <button class="undecided-combobox-option" type="button" role="option" data-undecided-mode="undecided" aria-selected="false">미정</button>
                    </div>
                  </div>
                </div>
                <label>개발 등급<select data-dropdown-path="analysis_overview.development_grade"></select><span class="prep-custom-control dropdown-custom-control" data-dropdown-custom-path="analysis_overview.development_grade" hidden><input class="custom-input" data-path="analysis_overview.development_grade" aria-label="개발 등급 직접 입력" /><button type="button" data-dropdown-restore-path="analysis_overview.development_grade" title="개발 등급 드롭다운으로 돌아가기" aria-label="개발 등급 드롭다운으로 돌아가기">↩</button></span></label>
                <label>NPI 단계<select data-dropdown-path="analysis_overview.npi_stage"></select><span class="prep-custom-control dropdown-custom-control" data-dropdown-custom-path="analysis_overview.npi_stage" hidden><input class="custom-input" data-path="analysis_overview.npi_stage" aria-label="NPI 단계 직접 입력" /><button type="button" data-dropdown-restore-path="analysis_overview.npi_stage" title="NPI 단계 드롭다운으로 돌아가기" aria-label="NPI 단계 드롭다운으로 돌아가기">↩</button></span></label>
                <div class="undecided-field">
                  <label for="modelSuffixInput">모델명(Model Suffix)</label>
                  <div class="undecided-combobox" data-undecided-combobox>
                    <input id="modelSuffixInput" data-path="analysis_overview.model_suffix" data-undecided-input role="combobox" aria-autocomplete="none" aria-haspopup="listbox" aria-controls="modelSuffixMenu" aria-expanded="false" autocomplete="off" />
                    <button class="undecided-combobox-toggle" type="button" data-undecided-toggle aria-label="모델명 입력 방식 선택" aria-controls="modelSuffixMenu" aria-expanded="false"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 9 5 5 5-5"></path></svg></button>
                    <div class="undecided-combobox-menu" id="modelSuffixMenu" data-undecided-menu role="listbox" aria-label="모델명 입력 방식" hidden>
                      <button class="undecided-combobox-option" type="button" role="option" data-undecided-mode="custom" aria-selected="true">직접 입력</button>
                      <button class="undecided-combobox-option" type="button" role="option" data-undecided-mode="undecided" aria-selected="false">미정</button>
                    </div>
                  </div>
                </div>
                <label>의뢰 요청일<input data-path="analysis_overview.request_date" type="date" /></label>
                <label>희망 완료일<input data-path="analysis_overview.desired_completion_date" type="date" /></label>
              </div>
            </div>
          </section>

          <div class="gate" id="analysisGate">
            <strong>해석유형을 먼저 선택해 주세요.</strong>
            <p class="subtitle">제품군과 검토 목적을 먼저 선택하면 필요한 입력 항목을 채워 주세요.</p>
          </div>

          <section class="section open" id="section-overview" data-section="analysis_overview">
            <div class="section-head">
              <div class="section-title"><h3>해석 요청 내용</h3></div>
              <div class="section-meta" id="meta-analysis_overview" hidden aria-hidden="true"></div>
            </div>
            <div class="section-body">
              <div class="request-detail-grid">
                <label>해석을 요청하게 된 배경<textarea data-path="analysis_overview.request_description" rows="2" placeholder="해석을 요청하게 된 배경을 작성해 주세요."></textarea></label>
                <label>해석으로 확인하고 싶은 내용<textarea data-path="analysis_overview.additional_result_request" rows="2" placeholder="해석으로 확인하고 싶은 내용을 작성해 주세요."></textarea></label>
              </div>
            </div>
          </section>
          <div class="screen-action-bar" aria-label="요청 내용 단계 이동">
            <button class="ghost" type="button" data-screen-action="SCREEN-01">이전: 의뢰 대상·시작</button>
            <button class="primary" type="button" data-screen-action="SCREEN-03">다음: 해석 제품</button>
          </div>
          </section>

          <section class="screen-group geometry-screen" data-screen="SCREEN-03" aria-labelledby="screen03Heading">
          <h2 class="screen-heading" id="screen03Heading"><span>해석 제품</span></h2>
          <p class="screen-description">해석 대상 형상의 도면번호와 설명을 입력합니다.</p>
          <section class="section open" id="section-geometry" data-section="geometry">
            <div class="section-head">
              <div class="section-title"><h3>해석 대상 제품</h3></div>
              <p class="geometry-inline-guidance">첫 번째 형상은 Base 제품이며, 추가한 형상은 비교 제품으로 사용됩니다.</p>
              <div class="section-meta" id="meta-geometry"></div>
            </div>
            <div class="section-body">
              <div class="product-table" aria-label="해석 대상 제품 입력">
                <div class="product-table-row product-table-head" aria-hidden="true"><span class="field-label">형상</span><span class="field-label">도면번호 (NPDM MCAD)</span><span class="field-label">설명</span><span class="product-action-heading">행 작업</span></div>
                <div class="row-list" id="productRows"></div>
              </div>
            </div>
          </section>
          <div class="screen-action-bar" aria-label="해석 제품 단계 이동">
            <button class="ghost" type="button" data-screen-action="SCREEN-02">이전: 요청 내용</button>
            <button class="primary" type="button" data-screen-action="SCREEN-04">다음: 해석 조건</button>
          </div>
          </section>

          <section class="screen-group stage-static-screen condition-input-screen" data-screen="SCREEN-04" aria-labelledby="screen04Heading">
          <h2 class="screen-heading" id="screen04Heading"><span>해석 조건</span></h2>
          <p class="screen-description">각 해석 조건의 첫 번째 조건은 <strong>Base 조건</strong>이며, 우측의 <strong>추가(+)</strong> 버튼으로 추가한 조건은 <strong>비교 조건</strong>으로 사용됩니다.</p>
          <section class="section open" id="section-conditions" data-section="conditions">
            <div class="section-body" id="conditionFields"></div>
          </section>
          <div class="screen-action-bar" aria-label="해석 조건 단계 이동">
            <button class="ghost" type="button" data-screen-action="SCREEN-03">이전: 해석 제품</button>
            <button class="primary" type="button" data-screen-action="SCREEN-05">다음: Case Matrix</button>
          </div>
          </section>

          <section class="screen-group stage-static-screen" data-screen="SCREEN-05" aria-labelledby="screen05Heading">
          <h2 class="screen-heading" id="screen05Heading"><span>Case Matrix</span></h2>
          <p class="screen-description">해석 제품과 해석 조건의 조합을 Case별로 확인하고 구성합니다.</p>
          <section class="section open" id="section-case" data-section="case_matrix">
            <div class="section-head">
              <div class="section-title"><h3>Case 구성</h3></div>
              <div class="case-section-actions"><button class="primary" type="button" data-action="add-case">Case 추가</button></div>
            </div>
            <div class="section-body">
              <div id="caseCommon"></div>
              <div id="caseMatrix"></div>
            </div>
          </section>
          <div class="screen-action-bar" aria-label="Case Matrix 단계 이동">
            <button class="ghost" type="button" data-screen-action="SCREEN-04">이전: 해석 조건</button>
            <button class="primary" id="caseConfirmNextBtn" type="button" data-action="confirm-case-configuration">다음: 전체 확인</button>
          </div>
          </section>

          </div>
        </div>
        <div class="workspace-tab" id="tab-preview" hidden aria-hidden="true">
          <div class="workspace-form screen-group" data-screen="SCREEN-06" aria-labelledby="screen06Heading">
            <h2 class="screen-heading" id="screen06Heading"><span>전체 확인</span></h2>
            <p class="screen-description">입력한 의뢰 내용을 확인한 뒤 Word 의뢰서를 생성합니다.</p>
            <section class="section open" id="section-preview" data-section="preview">
              <div class="section-head">
                <div class="section-title"><span class="section-title-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M6 4h9l3 3v13H6z"></path><path d="M15 4v4h4M9 12h6M9 16h6"></path></svg></span><h3>의뢰서 미리보기</h3></div>
                <div class="section-meta" id="meta-preview"></div>
              </div>
              <div class="section-body">
                <div id="documentPreviewPanel"></div>
                <div class="preview-actions"><button class="primary" id="wordExportSlotBtn" type="button">의뢰서 생성(Word)</button></div>
              </div>
            </section>
          </div>
        </div>
      </div>
    </section>
      </div>
    </div>

    <div class="panel-resizer" id="panelResizer" role="separator" aria-label="입력 폼과 Agent 패널 너비 조절" aria-orientation="vertical" aria-valuemin="1" aria-valuenow="2" aria-valuemax="3"></div>
    <aside class="panel chat agent-dock" id="agentDock" data-shell="AgentDock" aria-labelledby="agentDockHeading">
      <div class="chat-head">
        <div id="agentDockHeading" class="title-with-icon" tabindex="-1"><span class="title-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M5 19a7 7 0 0 1 14 0"></path><circle cx="12" cy="8" r="4"></circle><path d="M4 12v3M20 12v3"></path></svg></span><strong class="stage-assist-title">Agent</strong></div>
        <div class="chat-head-actions">
          <button class="ghost" id="agentClearBtn" type="button" aria-controls="chatLog">대화창 비우기</button>
          <button class="ghost" id="agentHideBtn" type="button" aria-controls="agentDock" aria-expanded="true">Agent 숨기기</button>
        </div>
      </div>
      <div class="chat-log" id="chatLog">
        <div class="msg assistant">제품군, platform, 해석유형을 선택한 뒤 의뢰 내용을 입력해 주세요.</div>
      </div>
      <div class="chat-input">
        <div class="chat-row">
          <textarea id="chatInput" placeholder="예: 작동유체는 Air, Fan RPM은 780 / 또는 남은 입력 항목이 뭐야?"></textarea>
          <button class="primary" id="sendBtn" type="button">전송</button>
        </div>
      </div>
    </aside>
  </main>

  <div class="submit-modal" id="contextChangeModal" hidden role="dialog" aria-modal="true" aria-labelledby="contextChangeTitle">
    <div class="submit-dialog">
      <strong id="contextChangeTitle">조합을 변경할까요?</strong>
      <p class="subtitle">제품군, platform, 해석유형을 변경하면 현재 입력한 해석조건 값이 새 입력항목과 맞지 않을 수 있습니다.<br>변경하시겠습니까?</p>
      <div class="context-change-actions">
        <button class="primary" id="contextChangeContinue" type="button">변경 계속</button>
        <button class="ghost" id="contextChangeCancel" type="button">취소</button>
      </div>
    </div>
  </div>

  <script>
    const $ = (id) => document.getElementById(id);
    const basicKeys = ["division","department","requester_name","requester_role"];
    const overviewInputKeys = ["project_name","development_grade","npi_stage","model_suffix","request_date","desired_completion_date","request_description","additional_result_request"];
    const decisionUseCatalog = {
      problem_analysis:"문제·현상 분석",
      design_review:"설계·변경 검토",
      performance_validation:"성능·시험 검증",
      other:"기타",
      undecided:"아직 결정하지 못함",
    };
    const decisionUseLegacyCodes = {
      design_selection:"design_review", change_applicability:"design_review", root_cause:"problem_analysis",
      improvement_direction:"problem_analysis", phenomenon_review:"problem_analysis",
      performance_requirement:"performance_validation", other:"other", undecided:"undecided",
    };
    const prepAnalysisTypes = ["풍량","기류 패턴","이슬맺힘","열교환기 유속 프로파일","기류도달거리","PDB","실사용 해석","집진해석(먼지거동)","PCB발열","다상유동"];
    const disabledAnalysisTypes = ["기류도달거리","PDB","실사용 해석","집진해석(먼지거동)","PCB발열","다상유동"];
    const disabledAnalysisTypeReason = "추후 지원 예정";
    const disabledAnalysisTypeLockIcon = `<span class="prep-choice-lock" aria-hidden="true"><svg viewBox="0 0 16 16"><rect x="3" y="7" width="10" height="7" rx="1.5"></rect><path d="M5 7V5a3 3 0 0 1 6 0v2"></path></svg></span>`;
    const disabledAnalysisTypeLockPrefix = "🔒 ";
    const defaultBusinessUnits = ["SAC","RAC","Aircare","Chiller"];
    const defaultDisabledBusinessUnits = ["Aircare","Chiller"];
    const defaultDisabledBusinessUnitReason = "데이터 업데이트 후 제공 예정";
    const defaultPlatformFallbacks = ["미정","직접 입력"];
    const emptyProductHierarchy = {
      business_units: defaultBusinessUnits,
      disabled_business_units: defaultDisabledBusinessUnits,
      disabled_business_unit_reason: defaultDisabledBusinessUnitReason,
      hierarchy: {SAC:{}, RAC:{}, Aircare:{}, Chiller:{}},
      fallback_product_group_options: ["미정","직접 입력"],
      fallback_platform_options: defaultPlatformFallbacks,
    };
    const dropdownOptions = {
      "basic_info.division": ["SAC","RAC","Aircare","Chiller","연구소","직접 입력"],
      "basic_info.requester_role": ["책임연구원","선임연구원","연구원","직접 입력"],
      "analysis_overview.development_grade": ["A","B","Ca","Cb","Cc","선행","미정","직접 입력"],
      "analysis_overview.npi_stage": ["CP","DV","PV","MP","미정","직접 입력"],
      "conditions.material_type": ["","Air","직접 입력"],
      "conditions.working_fluid": ["air","water"],
      "conditions.outlet_condition": ["pressure outlet"],
    };
    const sectionOrder = [
      ["analysis_overview","해석 요청 내용","section-overview"],
      ["geometry","제품형상","section-geometry"],
      ["conditions","해석조건","section-conditions"],
      ["case_matrix","Case Matrix","section-case"],
    ];
    const screenOrder = [
      {id:"SCREEN-01", headingId:"screen01Heading", tab:"write", requiresContext:false},
      {id:"SCREEN-02", headingId:"screen02Heading", tab:"write", requiresContext:true},
      {id:"SCREEN-03", headingId:"screen03Heading", tab:"write", requiresContext:true},
      {id:"SCREEN-04", headingId:"screen04Heading", tab:"write", requiresContext:true},
      {id:"SCREEN-05", headingId:"screen05Heading", tab:"write", requiresContext:true},
      {id:"SCREEN-06", headingId:"screen06Heading", tab:"preview", requiresContext:false},
    ];
    const operationModeOptions = ["실내", "실외", "동시운전"];
    const excludedConditionKeys = new Set(["material_type", "pressure", "vane_or_louver", "filter_state"]);
    let requestState = {};
    let schema = {};
    let recommendMode = false;
    let activeTopTab = "write";
    let activeScreen = "SCREEN-01";
    let lastPlannerActiveFieldId = "";
    let agentOpen = true;
    let lastAgentFocus = null;
    let chatHistory = [];
    let replayingChat = false;
    let productHierarchy = emptyProductHierarchy;
    let heatExchangerCatalog = [];
    const heatExchangerCustomFields = new Set();
    const fanCountCustomCards = new Set();
    let requestContextDraft = {};
    let activePrepMode = "quick";
    let quickProductGroupCustomMode = false;
    let quickPlatformCustomMode = false;
    let prepAssistStarted = false;
    const stageAssistConfigs = {
      start: {
        title: "의뢰 시작 도움",
        description: "제품과 확인 목적을 선택하면 필요한 입력항목이 자동으로 준비됩니다.",
        actions: [
          {label:"사업부가 무엇인지 설명", prompt:"사업부가 무엇인지 설명"},
          {label:"제품명으로 사업부 추정", prompt:"제품명으로 사업부 추정"},
          {label:"처음 사용하는 방법 보기", prompt:"처음 사용하는 방법 보기"},
        ],
      },
      business_unit: {
        title: "사업부 선택 도움",
        description: "현재는 제품이 속한 사업부를 선택하는 단계입니다.",
        actions: [
          {label:"사업부가 무엇인지 설명", prompt:"사업부가 무엇인지 설명"},
          {label:"제품명으로 사업부 추정", prompt:"제품명으로 사업부 추정"},
          {label:"잘 모르겠어요", prompt:"사업부를 잘 모르겠어요"},
        ],
      },
      product_group: {
        title: "제품군 선택 도움",
        description: "선택한 사업부에 해당하는 제품군만 표시됩니다.",
        actions: [
          {label:"제품군이 뭔가요?", prompt:"제품군이 뭔가요?"},
          {label:"제품명으로 제품군 범위 확인", prompt:"제품명으로 제품군 범위 확인"},
          {label:"기존 의뢰와 비슷하게 시작", prompt:"기존 의뢰와 비슷하게 시작"},
        ],
      },
      platform: {
        title: "Platform 선택 도움",
        description: "platform을 선택하면 조건 입력항목을 더 정확하게 고를 수 있습니다. 모르면 미정으로 진행할 수 있습니다.",
        actions: [
          {label:"platform을 모르겠어요", prompt:"platform을 모르겠어요"},
          {label:"제품명으로 platform 추정", prompt:"제품명으로 platform 추정"},
          {label:"미정으로 진행해도 되나요?", prompt:"미정으로 진행해도 되나요?"},
        ],
      },
      analysis_type: {
        title: "해석유형 선택 도움",
        description: "확인하고 싶은 현상을 기준으로 해석유형을 선택합니다.",
        actions: [
          {label:"현상 설명하고 추천받기", prompt:"현상 설명하고 추천받기"},
          {label:"이슬맺힘이 맞는지 확인", prompt:"이슬맺힘이 맞는지 확인"},
          {label:"풍량 해석과 차이 보기", prompt:"풍량 해석과 차이 보기"},
        ],
      },
      conditions: {
        title: "해석조건 입력 도움",
        description: "현재 조합에 맞는 입력항목만 표시됩니다.",
        actions: [
          {label:"누락 조건 확인", prompt:"누락 조건 확인"},
          {label:"조건 의미 설명", prompt:"조건 의미 설명"},
          {label:"Case Matrix 미리보기", prompt:"Case Matrix 미리보기"},
          {label:"AI가 입력값 점검", prompt:"AI가 입력값을 점검해줘"},
        ],
      },
    };
    const touchedFields = new Set();
    const orchestratorPanelState = {conversationId:"", requestId:"", requestVersion:null, dirty:true, loading:false, caseMatrixActionLoading:false, validationActionLoading:false, previewActionLoading:false, wordExportActionLoading:false, ragGuidanceActionLoading:false, caseMatrixSyncedRequestId:"", caseMatrixSyncedRequestVersion:null, previewRenderedRequestId:"", previewRenderedRequestVersion:null, decisionIds:new Set(), refreshedProposalIds:new Set(), latestApprovedState:null};

    function esc(text){
      return String(text ?? "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;");
    }
    function asObj(value){ return value && typeof value === "object" && !Array.isArray(value) ? value : {}; }
    function asArray(value){ return Array.isArray(value) ? value : []; }
    function fieldValue(field, fallback=""){
      const src = asObj(field);
      if (src.status && src.status !== "provided") return fallback;
      const value = Object.prototype.hasOwnProperty.call(src, "value") ? src.value : fallback;
      return value === null || value === undefined ? fallback : value;
    }
    function statusDisplay(field){
      const src = asObj(field);
      return src.display_value || ({unknown:"紐⑤쫫", none:"?놁쓬", skipped:"skip"}[src.status] || "");
    }
    function fieldDisplayValue(field, fallback=""){
      if (field !== null && field !== undefined && typeof field !== "object") {
        const value = String(field);
        return value.trim() ? value : fallback;
      }
      if (asObj(asObj(field).value).primary_code) return decisionUseDisplay(field) || fallback;
      const value = fieldValue(field, "");
      if (String(value ?? "").trim()) return value;
      const display = statusDisplay(field);
      return display || fallback;
    }
    function rowValue(row){
      if (row && typeof row === "object") return asObj(row).status === "provided" ? fieldValue(row) : statusDisplay(row);
      return row ?? "";
    }
    function productField(product, key){ return asObj(product)[key]; }
    function productText(product, key){ return fieldDisplayValue(productField(product, key)); }
    function isProvided(field){ return asObj(field).status === "provided" && String(fieldValue(field,"")).trim() !== ""; }
    function pathInput(section, key){ return document.querySelector(`[data-path="${section}.${key}"]`); }
    function setStatus(text){ $("saveStatus") ? $("saveStatus").textContent = text : null; }
    function notify(text){ pushMessage("assistant", text); }

    function localDateValue(date){
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, "0");
      const day = String(date.getDate()).padStart(2, "0");
      return `${year}-${month}-${day}`;
    }

    function configureDesiredCompletionDateMinimum(){
      const input = pathInput("analysis_overview", "desired_completion_date");
      if (!input) return;
      const now = new Date();
      input.min = localDateValue(new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1));
      input.title = "희망 완료일은 내일부터 선택할 수 있습니다.";
    }

    function serializedDecisionUseValue(rawValue){
      if (typeof rawValue !== "string") return null;
      const legacy = rawValue.trim();
      if (!/^\{[\s\S]*\}$/.test(legacy) || !/(?:['"]?primary_code['"]?|['"]?custom_text['"]?)/.test(legacy)) return null;
      const read = (key) => {
        const match = legacy.match(new RegExp(`['"]?${key}['"]?\\s*:\\s*(?:['"]([^'"]*)['"]|(null|none|undefined))`, "i"));
        return match ? String(match[1] || "").trim() : "";
      };
      return {primary_code:read("primary_code"), custom_text:read("custom_text")};
    }

    function normalizeDecisionUse(field){
      const raw = asObj(field);
      const rawValue = Object.prototype.hasOwnProperty.call(raw, "value") ? raw.value : field;
      const serialized = serializedDecisionUseValue(rawValue);
      const value = serialized || asObj(rawValue);
      let primaryCode = String(value.primary_code || "").trim();
      let customText = String(value.custom_text || "").trim();
      if (!primaryCode && !serialized) {
        const legacy = typeof rawValue === "string" ? rawValue.trim() : "";
        primaryCode = decisionUseLegacyCodes[legacy] || (Object.prototype.hasOwnProperty.call(decisionUseCatalog, legacy) ? legacy : (legacy ? "other" : ""));
        if (primaryCode === "other" && legacy && !decisionUseLegacyCodes[legacy]) customText = legacy;
      }
      if (!Object.prototype.hasOwnProperty.call(decisionUseCatalog, primaryCode)) {
        customText = customText || primaryCode;
        primaryCode = customText ? "other" : "";
      }
      return {primary_code:primaryCode, custom_text:primaryCode === "other" ? customText : ""};
    }

    function decisionUseDisplay(field){
      const value = normalizeDecisionUse(field);
      return value.primary_code === "other" && value.custom_text ? `${decisionUseCatalog.other}: ${value.custom_text}` : (decisionUseCatalog[value.primary_code] || "");
    }

    function selectedDecisionUseCode(){ return $("decisionUseSelect")?.value || ""; }

    function renderDecisionUseAuxiliary(code=selectedDecisionUseCode()){
      const customWrap = $("decisionUseCustomWrap");
      const customInput = $("decisionUseCustom");
      const serializedCustom = code === "other" ? serializedDecisionUseValue(customInput?.value) : null;
      if (customInput && serializedCustom) customInput.value = serializedCustom.custom_text;
      if (customWrap) customWrap.hidden = code !== "other";
    }

    function syncDecisionUseEditor(field){
      const value = normalizeDecisionUse(field);
      if ($("decisionUseSelect")) $("decisionUseSelect").value = value.primary_code;
      if ($("decisionUseCustom")) $("decisionUseCustom").value = value.custom_text;
      renderDecisionUseAuxiliary(value.primary_code);
    }

    function collectDecisionUseField(){
      const previous = asObj(asObj(requestState.analysis_overview).decision_use);
      const primaryCode = selectedDecisionUseCode();
      const customText = $("decisionUseCustom")?.value.trim() || "";
      const validity = !primaryCode || (primaryCode === "other" && !customText) ? "invalid" : (primaryCode === "undecided" ? "unverified" : "valid");
      return {
        value:{primary_code:primaryCode, custom_text:primaryCode === "other" ? customText || null : null},
        display_value:primaryCode === "other" && customText ? `${decisionUseCatalog.other}: ${customText}` : (decisionUseCatalog[primaryCode] || ""),
        status:primaryCode ? "provided" : "missing",
        source:"user",
        validity,
        confirmation_status:previous.confirmation_status || "not_required",
        note:previous.note || "",
      };
    }

    function optionsForPath(path){
      const fromSchema = asArray(asObj(schema.ui_options)[path]);
      return fromSchema.length ? fromSchema : asArray(dropdownOptions[path]);
    }

    function dropdownOptionHtml(options){
      return [`<option value="" disabled hidden>선택</option>`, ...asArray(options).filter(option => option !== "").map(option => {
        if (option === "직접 입력") return `<option value="__custom__">직접 입력</option>`;
        return `<option value="${esc(option)}">${esc(option)}</option>`;
      })].join("");
    }

    function dropdownOptionHtmlWithSelected(options, selected){
      return [`<option value="" disabled hidden ${selected === "" ? "selected" : ""}>선택</option>`, ...asArray(options).filter(option => option !== "").map(option => {
        const value = option === "직접 입력" ? "__custom__" : option;
        const label = option;
        return `<option value="${esc(value)}" ${String(value) === String(selected) ? "selected" : ""}>${esc(label)}</option>`;
      })].join("");
    }

    function setupDropdowns(){
      document.querySelectorAll("select[data-dropdown-path]").forEach(select => {
        const path = select.dataset.dropdownPath || "";
        select.innerHTML = dropdownOptionHtml(optionsForPath(path));
      });
    }

    function syncDropdownForPath(path, value){
      const select = document.querySelector(`select[data-dropdown-path="${CSS.escape(path)}"]`);
      const input = document.querySelector(`input[data-path="${CSS.escape(path)}"]`);
      const customControl = document.querySelector(`[data-dropdown-custom-path="${CSS.escape(path)}"]`);
      if (!select || !input) return;
      const text = String(value || "");
      const values = Array.from(select.options).map(option => option.value);
      select.value = values.includes(text) ? text : (text ? "__custom__" : "");
      const customMode = select.value === "__custom__";
      select.hidden = customMode;
      if (customControl) customControl.hidden = !customMode;
      else input.hidden = !customMode;
      input.value = text;
    }

    function contextText(value){
      return String(value ?? "").trim();
    }

    function undecidedComboboxSpecialValue(combobox){
      return contextText(combobox?.dataset.undecidedValue) || "미정";
    }

    function undecidedComboboxMode(combobox){
      return combobox?.querySelector("[data-undecided-input]")?.dataset.undecidedMode === "undecided" ? "undecided" : "custom";
    }

    function setUndecidedActiveOption(combobox, activeOption, {focus=false}={}){
      combobox?.querySelectorAll("[data-undecided-mode]").forEach(option => {
        option.dataset.undecidedActive = String(option === activeOption);
      });
      if (focus) activeOption?.focus({preventScroll:true});
    }

    function setUndecidedComboboxOpen(combobox, open, {focusOption=false}={}){
      const input = combobox?.querySelector("[data-undecided-input]");
      const toggle = combobox?.querySelector("[data-undecided-toggle]");
      const menu = combobox?.querySelector("[data-undecided-menu]");
      if (!input || !toggle || !menu) return;
      if (open) {
        document.querySelectorAll("[data-undecided-combobox]").forEach(other => {
          if (other !== combobox) setUndecidedComboboxOpen(other, false);
        });
      }
      menu.hidden = !open;
      input.setAttribute("aria-expanded", String(open));
      toggle.setAttribute("aria-expanded", String(open));
      if (open && focusOption) {
        const selectedOption = menu.querySelector(`[data-undecided-mode="${undecidedComboboxMode(combobox)}"]`);
        setUndecidedActiveOption(combobox, selectedOption, {focus:true});
      } else if (!open) {
        setUndecidedActiveOption(combobox, null);
      }
    }

    function renderUndecidedComboboxMode(combobox, mode){
      const input = combobox?.querySelector("[data-undecided-input]");
      const selectedMode = mode === "undecided" ? "undecided" : "custom";
      if (!input) return;
      input.dataset.undecidedMode = selectedMode;
      input.readOnly = selectedMode === "undecided";
      const fieldLabel = input.dataset.customPlaceholder || (input.id === "modelSuffixInput" ? "모델명을 입력하세요" : "프로젝트명을 입력하세요");
      input.placeholder = selectedMode === "custom" ? fieldLabel : "";
      combobox.querySelectorAll("[data-undecided-mode]").forEach(option => {
        option.setAttribute("aria-selected", String(option.dataset.undecidedMode === selectedMode));
      });
    }

    function syncUndecidedCombobox(path, value){
      const input = document.querySelector(`[data-undecided-input][data-path="${CSS.escape(path)}"]`);
      const combobox = input?.closest("[data-undecided-combobox]");
      if (!combobox) return;
      renderUndecidedComboboxMode(combobox, contextText(value) === undecidedComboboxSpecialValue(combobox) ? "undecided" : "custom");
      setUndecidedComboboxOpen(combobox, false);
    }

    function selectUndecidedComboboxMode(combobox, mode){
      const input = combobox?.querySelector("[data-undecided-input]");
      if (!input) return;
      const previousMode = undecidedComboboxMode(combobox);
      if (mode === "undecided") {
        const specialValue = undecidedComboboxSpecialValue(combobox);
        if (specialValue === "미정") input.value = "미정";
        else input.value = specialValue;
        renderUndecidedComboboxMode(combobox, "undecided");
      } else {
        if (previousMode === "undecided") input.value = "";
        renderUndecidedComboboxMode(combobox, "custom");
      }
      touchedFields.add(input.dataset.path || "");
      setUndecidedComboboxOpen(combobox, false);
      renderScreenNavigation();
      schedulePreviewRefresh();
      window.requestAnimationFrame(() => input.focus());
    }

    function uniqueValues(items){
      const seen = new Set();
      const out = [];
      asArray(items).forEach(item => {
        const value = contextText(item);
        if (!value || seen.has(value)) return;
        seen.add(value);
        out.push(value);
      });
      return out;
    }

    function fallbackRequestContext(){
      return {
        business_unit: "",
        product_group: "",
        platform: "",
        analysis_type: "",
        operation_mode: "",
        context_locked: false,
        condition_fieldset_key: "",
        condition_fieldset_snapshot: [],
      };
    }

    function contextFromState(){
      const context = asObj(requestState.request_context);
      const basic = asObj(requestState.basic_info);
      let businessUnit = contextText(context.business_unit);
      if (businessUnit && !businessUnitOptions().includes(businessUnit)) businessUnit = "";
      return {
        ...fallbackRequestContext(),
        ...context,
        business_unit: businessUnit,
        product_group: contextText(context.product_group),
        platform: contextText(context.platform),
        analysis_type: contextText(context.analysis_type),
        operation_mode: contextText(context.operation_mode),
        context_locked: context.context_locked === true,
      };
    }

    function isContextLocked(){
      return contextFromState().context_locked === true;
    }

    function syncRequestContextDraftFromState(){
      requestContextDraft = contextFromState();
    }

    function hasAnyRequestContextValue(context){
      return ["business_unit","product_group","platform","analysis_type"].some(key => contextText(context[key]));
    }

    function currentStageAssistKey(){
      const context = collectRequestContextDraft();
      if (context.context_locked === true) return "conditions";
      if (!prepAssistStarted && !hasAnyRequestContextValue(context)) return "start";
      if (!contextText(context.business_unit)) return "business_unit";
      if (!contextText(context.product_group)) return "product_group";
      if (!contextText(context.platform)) return "platform";
      return "analysis_type";
    }

    function fillStageAssistPrompt(prompt){
      const input = $("chatInput");
      const text = String(prompt || "").trim();
      if (!input || !text) return;
      input.value = text;
      input.focus();
      input.setSelectionRange?.(text.length, text.length);
    }

    function productHierarchyPayload(){
      return {
        ...emptyProductHierarchy,
        ...asObj(productHierarchy),
        hierarchy: {...emptyProductHierarchy.hierarchy, ...asObj(asObj(productHierarchy).hierarchy)},
        fallback_product_group_options: uniqueValues(asArray(asObj(productHierarchy).fallback_product_group_options).length ? asObj(productHierarchy).fallback_product_group_options : emptyProductHierarchy.fallback_product_group_options),
        fallback_platform_options: uniqueValues(asArray(asObj(productHierarchy).fallback_platform_options).length ? asObj(productHierarchy).fallback_platform_options : defaultPlatformFallbacks),
      };
    }

    function businessUnitOptions(){
      const payload = productHierarchyPayload();
      return uniqueValues(asArray(payload.business_units).length ? payload.business_units : defaultBusinessUnits);
    }

    function productGroupOptions(unit){
      const payload = productHierarchyPayload();
      const products = asObj(asObj(payload.hierarchy)[unit]);
      return uniqueValues([...Object.keys(products).sort((a,b) => a.localeCompare(b, "ko")), ...asArray(payload.fallback_product_group_options)]);
    }

    function platformOptions(unit, productGroup){
      const payload = productHierarchyPayload();
      const products = asObj(asObj(payload.hierarchy)[unit]);
      const platforms = asArray(products[productGroup]);
      return uniqueValues([...platforms, ...asArray(payload.fallback_platform_options)]);
    }

    function renderPrepChoices(containerId, field, values, selected, disabled=false, disabledValues=[], disabledReason="", disabledSuffix="", showDisabledLock=false){
      const container = $(containerId);
      if (!container) return;
      const rows = uniqueValues(values);
      const disabledSet = new Set(uniqueValues(disabledValues));
      if (!rows.length) {
        container.innerHTML = `<div class="empty">선택 가능한 항목 없음</div>`;
        return;
      }
      container.innerHTML = rows.map(value => {
        const unavailable = disabled || disabledSet.has(value);
        const reasonAttrs = unavailable && disabledReason ? ` title="${esc(disabledReason)}" aria-label="${esc(`${value}: ${disabledReason}`)}"` : "";
        const label = disabledSet.has(value) && disabledSuffix ? `${value}${disabledSuffix}` : value;
        const lockIcon = disabledSet.has(value) && showDisabledLock ? disabledAnalysisTypeLockIcon : "";
        return `<button type="button" class="prep-choice ${value === selected ? "selected" : ""}" data-context-choice="${esc(field)}" data-context-value="${esc(value)}" ${unavailable ? "disabled" : ""}${reasonAttrs}>${lockIcon}${esc(label)}</button>`;
      }).join("");
    }

    function renderPrepSelect(selectId, values, selected, placeholder, disabled=false, disabledValues=[], disabledSuffix="", disabledPrefix=""){
      const select = $(selectId);
      if (!select) return;
      const rows = uniqueValues(values);
      const disabledSet = new Set(uniqueValues(disabledValues));
      const optionHtml = [`<option value="" disabled hidden>${esc(placeholder)}</option>`, ...rows.map(value => {
        const label = disabledSet.has(value) ? `${disabledPrefix}${value}${disabledSuffix}` : value;
        return `<option value="${esc(value)}" ${disabledSet.has(value) ? "disabled" : ""}>${esc(label)}</option>`;
      })].join("");
      select.innerHTML = optionHtml;
      select.disabled = disabled;
      select.value = rows.includes(selected) ? selected : "";
    }

    function renderQuickProductGroupControl(values, selected, disabled=false){
      const select = $("quickProductGroupSelect");
      const custom = $("quickProductGroupCustom");
      const input = $("quickProductGroupCustomInput");
      if (!select || !custom || !input) return;
      const rows = uniqueValues(values);
      const knownValues = rows.filter(value => value !== "직접 입력");
      const customMode = quickProductGroupCustomMode || (!!selected && !knownValues.includes(selected));
      select.innerHTML = [`<option value="" disabled hidden>${esc(disabled ? "사업부 먼저 선택" : "제품군 선택")}</option>`, ...rows.map(value => `<option value="${value === "직접 입력" ? "__custom__" : esc(value)}">${esc(value)}</option>`)].join("");
      select.disabled = disabled;
      select.hidden = customMode;
      custom.hidden = !customMode;
      input.disabled = disabled;
      input.value = customMode ? selected : "";
      if (!customMode) select.value = knownValues.includes(selected) ? selected : "";
    }

    function renderQuickPlatformControl(values, selected, disabled=false){
      const select = $("quickPlatformSelect");
      const custom = $("quickPlatformCustom");
      const input = $("quickPlatformCustomInput");
      if (!select || !custom || !input) return;
      const rows = uniqueValues(values);
      const knownValues = rows.filter(value => value !== "직접 입력");
      const customMode = quickPlatformCustomMode || (!!selected && !knownValues.includes(selected));
      select.innerHTML = [`<option value="" disabled hidden>${esc(disabled ? "제품군 먼저 선택" : "Platform 선택")}</option>`, ...rows.map(value => `<option value="${value === "직접 입력" ? "__custom__" : esc(value)}">${esc(value)}</option>`)].join("");
      select.disabled = disabled;
      select.hidden = customMode;
      custom.hidden = !customMode;
      input.disabled = disabled;
      input.value = customMode ? selected : "";
      if (!customMode) select.value = knownValues.includes(selected) ? selected : "";
    }

    function setPrepStatus(id, value, fallback){
      const el = $(id);
      if (!el) return;
      el.textContent = value || fallback;
      el.className = `chip ${value ? "ok" : "info"}`;
    }

    function renderRequestPrepCard(){
      const card = $("requestPrepCard");
      if (!card) return;
      const context = {...fallbackRequestContext(), ...requestContextDraft};
      const locked = context.context_locked === true;
      card.hidden = false;
      const prepBody = card.querySelector(".prep-body");
      if (prepBody) prepBody.hidden = locked;
      const changeButton = $("contextChangeBtn");
      if (changeButton) changeButton.hidden = !locked;
      const nextButton = $("nextRequestContentBtn");
      if (nextButton) nextButton.hidden = !locked;
      renderContextChip();
      if (locked) return;
      const hierarchyPayload = productHierarchyPayload();
      const unitOptions = businessUnitOptions();
      const disabledUnitOptions = uniqueValues(asArray(hierarchyPayload.disabled_business_units));
      const disabledUnitReason = contextText(hierarchyPayload.disabled_business_unit_reason) || defaultDisabledBusinessUnitReason;
      const productOptions = context.business_unit ? productGroupOptions(context.business_unit) : [];
      const platformRows = context.business_unit && context.product_group ? platformOptions(context.business_unit, context.product_group) : productHierarchyPayload().fallback_platform_options;
      const productDisabled = !context.business_unit;
      const platformDisabled = !context.product_group;

      document.querySelectorAll("button[data-prep-mode]").forEach(button => {
        const active = button.dataset.prepMode === activePrepMode;
        button.classList.toggle("active", active);
        button.classList.toggle("primary", active);
        button.classList.toggle("ghost", !active);
      });
      $("guidedPrepFlow")?.classList.toggle("active", activePrepMode === "guided");
      $("quickPrepFlow")?.classList.toggle("active", activePrepMode === "quick");

      renderPrepChoices("prepBusinessChoices", "business_unit", unitOptions, context.business_unit, false, disabledUnitOptions, disabledUnitReason);
      renderPrepChoices("prepProductChoices", "product_group", productOptions, context.product_group, productDisabled);
      renderPrepChoices("prepPlatformChoices", "platform", platformRows, context.platform, platformDisabled);
      renderPrepChoices("prepAnalysisChoices", "analysis_type", prepAnalysisTypes, context.analysis_type, false, disabledAnalysisTypes, disabledAnalysisTypeReason, " (예정)", true);

      renderPrepSelect("quickBusinessUnitSelect", unitOptions, context.business_unit, "사업부 선택", false, disabledUnitOptions);
      renderQuickProductGroupControl(productOptions, context.product_group, productDisabled);
      renderQuickPlatformControl(platformRows, context.platform, platformDisabled);
      renderPrepSelect("quickAnalysisTypeSelect", prepAnalysisTypes, context.analysis_type, "해석유형 선택", false, disabledAnalysisTypes, " (예정)", disabledAnalysisTypeLockPrefix);

      setPrepStatus("prepBusinessStatus", context.business_unit, "선택 필요");
      setPrepStatus("prepProductStatus", context.product_group, productDisabled ? "사업부 기준" : "선택 필요");
      setPrepStatus("prepPlatformStatus", context.platform, "미정 가능");
      setPrepStatus("prepAnalysisStatus", context.analysis_type, "우선 표시");

      document.querySelectorAll("[data-prep-step='product_group']").forEach(el => el.classList.toggle("disabled", productDisabled));
      document.querySelectorAll("[data-prep-step='platform']").forEach(el => el.classList.toggle("disabled", platformDisabled));

      const combo = [context.business_unit, context.product_group, context.platform, context.analysis_type].map(value => value || "미선택").join(" / ");
      const summary = $("prepSelection");
      if (summary) {
        summary.innerHTML = `<strong>선택한 조합</strong><div class="combo">${esc(combo)}</div><div class="note">선택을 확정하면 맞춤 입력항목이 준비됩니다.</div><div class="prep-summary-actions"><button class="primary" id="prepStartBtn" type="button">의뢰서 작성 시작</button></div>`;
      }
      renderContextChip();
    }

    function renderContextChip(){
      const bar = $("contextChipBar");
      const list = $("contextChipList");
      if (!bar || !list) return;
      const context = contextFromState();
      const locked = context.context_locked === true;
      bar.hidden = !locked;
      if (!locked) {
        list.innerHTML = "";
        return;
      }
      list.innerHTML = ["business_unit","product_group","platform","analysis_type"]
        .map(key => `<span class="chip ok">${esc(context[key] || "미선택")}</span>`)
        .join("");
    }

    function updateRequestContextDraft(field, value){
      prepAssistStarted = true;
      const next = {...fallbackRequestContext(), ...requestContextDraft};
      next[field] = contextText(value);
      if (field === "business_unit") {
        quickProductGroupCustomMode = false;
        quickPlatformCustomMode = false;
        next.product_group = "";
        next.platform = "";
      }
      if (field === "product_group") {
        quickPlatformCustomMode = false;
        next.platform = "";
      }
      requestContextDraft = next;
      requestState.request_context = {...asObj(requestState.request_context), ...requestContextDraft};
      touchedFields.add(`request_context.${field}`);
      renderRequestPrepCard();
      updateTopChrome();
      schedulePreviewRefresh();
    }

    function collectRequestContextDraft(){
      return {
        ...fallbackRequestContext(),
        ...asObj(requestState.request_context),
        ...requestContextDraft,
        context_locked: asObj(requestState.request_context).context_locked === true,
      };
    }

    function syncQuickPrepSelectionsToDraft(){
      const next = {...fallbackRequestContext(), ...asObj(requestState.request_context), ...requestContextDraft};
      [
        ["business_unit", "quickBusinessUnitSelect"],
        ["product_group", "quickProductGroupSelect"],
        ["platform", "quickPlatformSelect"],
        ["analysis_type", "quickAnalysisTypeSelect"],
      ].forEach(([field, id]) => {
        const select = $(id);
        if (!select) return;
        if (field === "product_group" && quickProductGroupCustomMode) {
          next[field] = contextText($("quickProductGroupCustomInput")?.value);
        } else if (field === "platform" && quickPlatformCustomMode) {
          next[field] = contextText($("quickPlatformCustomInput")?.value);
        } else {
          next[field] = contextText(select.value);
        }
      });
      requestContextDraft = next;
      requestState.request_context = {...asObj(requestState.request_context), ...requestContextDraft};
      return collectRequestContextDraft();
    }

    function collectContextConfirmState(context){
      try {
        const state = collectState();
        return {...state, request_context: {...asObj(state.request_context), ...context}};
      } catch (err) {
        console.warn("context confirm state fallback", err);
        return {...asObj(requestState), request_context: {...fallbackRequestContext(), ...context}};
      }
    }

    async function fetchProductHierarchyOptions(){
      const res = await fetch("/api/product-hierarchy");
      const data = await res.json();
      if (!res.ok || data.ok === false) throw new Error(data.message || "product hierarchy load failed");
      productHierarchy = data;
      renderRequestPrepCard();
    }

    function missingContextFields(context=null){
      context = context || collectRequestContextDraft();
      return ["business_unit","product_group","platform","analysis_type"].filter(key => !contextText(context[key]));
    }

    async function confirmRequestContext(){
      const context = syncQuickPrepSelectionsToDraft();
      const missing = missingContextFields(context);
      if (missing.length) {
        prepAssistStarted = true;
        pushMessage("assistant", "사업부, 제품군, platform, 해석유형을 모두 선택해 주세요.");
        renderRequestPrepCard();
        return;
      }
      const data = await postJson("/api/request-context/confirm", {state:collectContextConfirmState(context), request_context:context});
      adoptStateFromResponse(data);
      syncEditorFromState();
      navigateScreen("SCREEN-02");
    }


    async function updateOperationMode(value){
      const state = collectState();
      const context = {...collectRequestContextDraft(), operation_mode: contextText(value)};
      state.request_context = {...asObj(state.request_context), ...context};
      const data = await postJson("/api/request-context/fieldset", {state, request_context: context});
      adoptStateFromResponse(data);
      syncEditorFromState();
    }
    function showContextChangeWarning(){
      $("contextChangeModal").hidden = false;
      $("contextChangeCancel").focus();
    }

    function hideContextChangeWarning(){
      $("contextChangeModal").hidden = true;
    }

    function continueContextChange(){
      const current = contextFromState();
      requestContextDraft = {
        ...fallbackRequestContext(),
        ...current,
        context_locked: false,
        condition_fieldset_key: "",
        condition_fieldset_snapshot: [],
      };
      requestState.request_context = {...requestContextDraft};
      hideContextChangeWarning();
      activePrepMode = "quick";
      prepAssistStarted = true;
      syncEditorFromState();
      pushMessage("assistant", "조합 변경을 다시 진행할 수 있습니다. 기존 조건 입력값은 보존되어 있지만 조합과 맞지 않으면 다음 단계에서 사용되지 않습니다.");
    }

    function handleDropdownChange(select){
      const path = select.dataset.dropdownPath || "";
      const input = document.querySelector(`input[data-path="${CSS.escape(path)}"]`);
      const customControl = document.querySelector(`[data-dropdown-custom-path="${CSS.escape(path)}"]`);
      if (!input) return;
      if (select.value === "__custom__") {
        input.value = "";
        select.hidden = true;
        if (customControl) customControl.hidden = false;
        else input.hidden = false;
        input.focus();
      } else {
        select.hidden = false;
        if (customControl) customControl.hidden = true;
        else input.hidden = true;
        input.value = select.value;
      }
      touchedFields.add(path);
      schedulePreviewRefresh();
    }

    function restoreDropdownControl(button){
      const path = button.dataset.dropdownRestorePath || "";
      const select = document.querySelector(`select[data-dropdown-path="${CSS.escape(path)}"]`);
      const input = document.querySelector(`input[data-path="${CSS.escape(path)}"]`);
      const customControl = document.querySelector(`[data-dropdown-custom-path="${CSS.escape(path)}"]`);
      if (!select || !input) return;
      select.hidden = false;
      select.value = "";
      input.value = "";
      if (customControl) customControl.hidden = true;
      else input.hidden = true;
      touchedFields.add(path);
      renderScreenNavigation();
      schedulePreviewRefresh();
      select.focus();
    }

    function handleConditionSelectChange(select){
      const key = select.dataset.conditionSelect || "";
      const index = select.dataset.index || "0";
      const input = document.querySelector(`input[data-condition-key="${CSS.escape(key)}"][data-index="${CSS.escape(index)}"]`);
      if (!input) return;
      if (select.value === "__custom__") {
        input.hidden = false;
        input.focus();
      } else {
        input.hidden = true;
        input.value = select.value;
      }
      touchedFields.add(key);
      schedulePreviewRefresh();
    }

    function hasAnalysisType(){
      return !!contextText(contextFromState().analysis_type);
    }

    function updateTopChrome(){
      const contextLocked = isContextLocked();
      const context = collectRequestContextDraft();
      const titleValues = [context.business_unit, context.product_group, context.platform, context.analysis_type].map(contextText);
      const requestTitle = titleValues.every(Boolean) ? titleValues.join(" / ") : "해석 의뢰를 시작해 주세요.";
      const requestNo = contextText(asObj(requestState.metadata).request_no) || fieldDisplayValue(asObj(requestState.basic_info).request_no) || "-";
      if ($("heroTitle")) $("heroTitle").textContent = requestTitle;
      if ($("requestNoDisplay")) $("requestNoDisplay").textContent = requestNo;
      const ragEnabled = false;
      if ($("ragToggle")) $("ragToggle").checked = false;
      document.querySelectorAll(".workspace-tab").forEach(panel => {
        const isActivePanel = panel.id === `tab-${activeTopTab}`;
        panel.classList.toggle("active", isActivePanel);
        if (isActivePanel) {
          panel.hidden = false;
          panel.removeAttribute("aria-hidden");
        } else {
          panel.hidden = true;
          panel.setAttribute("aria-hidden", "true");
        }
      });
      const contextChangeButton = $("contextChangeBtn");
      if (contextChangeButton) contextChangeButton.hidden = !contextLocked;
      const recommend = $("recommendBtn");
      if (recommend) recommend.disabled = !contextLocked;
    }

    function switchTopTab(tab){
      activeTopTab = tab === "preview" ? "preview" : "write";
      updateTopChrome();
      renderDerivedPanels();
    }

    function screenForSection(section){
      return {
        basic_info:"SCREEN-02", analysis_overview:"SCREEN-02", geometry:"SCREEN-03",
        conditions:"SCREEN-04", case_matrix:"SCREEN-05", preview:"SCREEN-06",
      }[section] || "SCREEN-01";
    }

    function setScreenNavigationStatus(message){
      const status = $("screenNavigationStatus");
      if (status) status.textContent = message;
    }

    function renderScreenNavigation(){
      const active = screenOrder.find(screen => screen.id === activeScreen) || screenOrder[0];
      const reviewScreen = screenOrder.find(screen => screen.id === "SCREEN-06");
      const firstIncomplete = firstIncompleteScreenBefore(reviewScreen);
      const firstIncompleteIndex = firstIncomplete ? screenOrder.findIndex(screen => screen.id === firstIncomplete.screen.id) : -1;
      document.querySelectorAll(".screen-map-item[data-screen]").forEach(item => {
        const screen = screenOrder.find(candidate => candidate.id === item.dataset.screen);
        const screenIndex = screenOrder.findIndex(candidate => candidate.id === screen?.id);
        const blocked = !!screen?.requiresContext && firstIncompleteIndex >= 0 && screenIndex > firstIncompleteIndex;
        item.setAttribute("role", "button");
        item.tabIndex = blocked ? -1 : 0;
        item.setAttribute("aria-disabled", String(blocked));
        item.setAttribute("aria-current", screen?.id === active.id ? "page" : "false");
        if (blocked) item.setAttribute("aria-describedby", "screenNavigationStatus"); else item.removeAttribute("aria-describedby");
      });
      document.querySelectorAll(".workspace-tab").forEach(panel => {
        const isActive = panel.id === `tab-${active.tab}`;
        panel.classList.toggle("active", isActive);
        panel.hidden = !isActive;
        panel.setAttribute("aria-hidden", String(!isActive));
      });
      document.querySelectorAll(".screen-group[data-screen]").forEach(group => {
        group.hidden = group.dataset.screen !== active.id;
      });
      const wordButton = $("wordExportSlotBtn");
      if (wordButton) {
        wordButton.disabled = firstIncompleteIndex >= 0;
        if (firstIncompleteIndex >= 0) wordButton.title = "필수 입력을 완료하면 의뢰서를 생성할 수 있습니다.";
        else wordButton.removeAttribute("title");
      }
      setScreenNavigationStatus(firstIncomplete
        ? `현재 화면: ${active.id}. ${firstIncomplete.screen.id}의 필수 입력을 완료하면 이후 단계를 열 수 있습니다. SCREEN-06 전체 확인은 항상 열 수 있습니다.`
        : `현재 화면: ${active.id}`);
    }

    function focusScreenHeading(screen){
      const heading = $(screen.headingId);
      if (!heading) return;
      heading.tabIndex = -1;
      heading.scrollIntoView({behavior:"smooth", block:"start"});
      heading.focus({preventScroll:true});
    }

    function requiredPathControl(path){
      const select = document.querySelector(`select[data-dropdown-path="${CSS.escape(path)}"]`);
      if (select?.value === "__custom__") return document.querySelector(`input[data-path="${CSS.escape(path)}"]`) || select;
      return select || document.querySelector(`[data-path="${CSS.escape(path)}"]`);
    }

    function missingRequiredControl(screenId){
      if (screenId === "SCREEN-01") {
        if (isContextLocked()) return null;
        const context = collectRequestContextDraft();
        const controls = {
          business_unit: $("quickBusinessUnitSelect"),
          product_group: quickProductGroupCustomMode ? $("quickProductGroupCustomInput") : $("quickProductGroupSelect"),
          platform: quickPlatformCustomMode ? $("quickPlatformCustomInput") : $("quickPlatformSelect"),
          analysis_type: $("quickAnalysisTypeSelect"),
        };
        return ["business_unit", "product_group", "platform", "analysis_type"]
          .map(key => !contextText(context[key]) ? controls[key] : null)
          .find(Boolean) || $("prepStartBtn");
      }
      if (screenId === "SCREEN-02") {
        const paths = [
          "basic_info.division", "basic_info.department", "basic_info.requester_name", "basic_info.requester_role",
          "analysis_overview.project_name", "analysis_overview.development_grade", "analysis_overview.npi_stage",
          "analysis_overview.model_suffix", "analysis_overview.request_date", "analysis_overview.desired_completion_date",
          "analysis_overview.request_description", "analysis_overview.additional_result_request",
        ];
        const desiredCompletionDate = requiredPathControl("analysis_overview.desired_completion_date");
        if (desiredCompletionDate && !desiredCompletionDate.validity.valid) return desiredCompletionDate;
        return paths.map(requiredPathControl).find(control => !contextText(control?.value)) || null;
      }
      if (screenId === "SCREEN-03") {
        return Array.from(document.querySelectorAll('[data-product-field="drawing_no"], [data-product-field="description"]'))
          .find(control => !contextText(control.value)) || null;
      }
      if (screenId === "SCREEN-04") {
        return Array.from(document.querySelectorAll('#conditionFields [data-card-field]'))
          .find(control => !contextText(control.value)) || null;
      }
      if (screenId === "SCREEN-05") {
        const rows = Array.from(document.querySelectorAll('tr[data-case-row]'));
        if (!rows.length) return document.querySelector('[data-action="add-case"]');
        return rows.flatMap(row => Array.from(row.querySelectorAll('select[data-case-field]')))
          .find(control => !contextText(control.value)) || null;
      }
      return null;
    }

    function focusRequiredControl(screen, control){
      activeScreen = screen.id;
      activeTopTab = screen.tab;
      renderScreenNavigation();
      setScreenNavigationStatus(`${screen.id}의 필수 입력을 완료한 뒤 다음 단계로 이동할 수 있습니다.`);
      const target = control || $(screen.headingId);
      target?.scrollIntoView({behavior:"smooth", block:"center"});
      target?.focus?.({preventScroll:true});
      if (target?.validity && !target.validity.valid) target.reportValidity?.();
    }

    function firstIncompleteScreenBefore(targetScreen){
      const targetIndex = screenOrder.findIndex(item => item.id === targetScreen.id);
      if (targetIndex < 1) return null;
      for (let index = 0; index < targetIndex; index += 1) {
        const screen = screenOrder[index];
        const control = missingRequiredControl(screen.id);
        if (control) return {screen, control};
      }
      return null;
    }

    function navigateScreen(screenId, options={}){
      const screen = screenOrder.find(item => item.id === screenId) || screenOrder[0];
      if (screen.requiresContext && !isContextLocked()) {
        const first = firstIncompleteScreenBefore(screen) || {screen:screenOrder[0], control:missingRequiredControl("SCREEN-01")};
        focusRequiredControl(first.screen, first.control);
        return false;
      }
      const currentIndex = screenOrder.findIndex(item => item.id === activeScreen);
      const targetIndex = screenOrder.findIndex(item => item.id === screen.id);
      if (!options.bypassRequiredGate && screen.id !== "SCREEN-06" && targetIndex > currentIndex) {
        const first = firstIncompleteScreenBefore(screen);
        if (first) {
          focusRequiredControl(first.screen, first.control);
          return false;
        }
      }
      activeScreen = screen.id;
      activeTopTab = screen.tab;
      renderScreenNavigation();
      if (options.focus !== false) focusScreenHeading(screen);
      return true;
    }

    function updateGate(){
      const contextLocked = isContextLocked();
      const ready = contextLocked && hasAnalysisType();
      const contextGate = $("contextLockGate");
      if (contextGate) contextGate.hidden = contextLocked;
      $("analysisGate").style.display = ready || !contextLocked ? "none" : "";
      $("formView").style.display = "";
      ["section-overview","section-geometry","section-conditions","section-case"].forEach(id => {
        const section = $(id);
        if (section) section.style.display = contextLocked ? "" : "none";
      });
      if (!contextLocked) $("section-basic")?.classList.add("open");
      if (!contextLocked && screenOrder.find(screen => screen.id === activeScreen)?.requiresContext) activeScreen = "SCREEN-01";
      renderScreenNavigation();
      renderCandidateNotice();
      renderContextChip();
      updateTopChrome();
    }

    function valuesFromRows(selector){
      return Array.from(document.querySelectorAll(selector)).map(input => input.value);
    }

    function productDescription(product, comparison=false){
      if (!comparison) return "Base";
      return productText(product, "difference_from_base") || productText(product, "display_name");
    }
    function productRow(product, index, comparison=false){
      const id = esc(product.geometry_id || `${comparison ? "comparison" : "base"}_${index + 1}`);
      const geometryNumber = comparison ? index + 2 : 1;
      const description = productDescription(product, comparison);
      const descriptionField = comparison
        ? `<label><input aria-label="형상 ${geometryNumber} 설명" data-product-field="description" value="${esc(description)}" placeholder="기존 형상과의 차이를 설명해주세요. (예시 : C/Box 구조 변경, 베인 각도 변경 등)" /></label>`
        : `<div class="base-product-description" aria-label="형상 1 설명" aria-readonly="true">Base</div>`;
      const action = comparison
        ? `<button class="condition-row-action remove" type="button" data-action="remove-comparison" data-index="${index}" title="해석 대상 제품 행 삭제" aria-label="형상 ${geometryNumber} 행 삭제">−</button>`
        : `<button class="primary condition-row-action" type="button" data-action="add-comparison" title="해석 대상 제품 행 추가" aria-label="해석 대상 제품 행 추가">+</button>`;
      return `<div class="product-table-row" data-product-id="${id}" data-product-index="${index}" data-product-role="${comparison ? "comparison" : "base"}">
        <div class="product-geometry-name" data-geometry-name>형상 ${geometryNumber}</div>
        <label><input aria-label="형상 ${geometryNumber} 도면번호 (NPDM MCAD)" data-product-field="drawing_no" value="${esc(productText(product, "drawing_no"))}" pattern="[A-Za-z0-9-]+" title="영문, 숫자, 하이픈(-)만 입력" /></label>
        ${descriptionField}
        <div class="condition-row-actions">${action}</div>
      </div>`;
    }
    function renderProductCards(baseProduct, comparisons){
      const list = asArray(comparisons);
      $("productRows").innerHTML = productRow(asObj(baseProduct), 0, false) + list.map((product, index) => productRow(asObj(product), index, true)).join("");
    }
    function reindexProductRows(){
      Array.from(document.querySelectorAll('#productRows [data-product-role="comparison"]')).forEach((row, index) => {
        row.dataset.productIndex = String(index);
        const geometryNumber = index + 2;
        const geometryName = row.querySelector("[data-geometry-name]");
        if (geometryName) geometryName.textContent = `형상 ${geometryNumber}`;
        const removeButton = row.querySelector('[data-action="remove-comparison"]');
        if (removeButton) {
          removeButton.dataset.index = String(index);
          removeButton.setAttribute("aria-label", `형상 ${geometryNumber} 행 삭제`);
        }
      });
    }
    function collectProductCards(){
      return Array.from(document.querySelectorAll("#productRows [data-product-id]")).map(row => {
        const value = key => row.querySelector(`[data-product-field="${key}"]`)?.value || "";
        const role = row.dataset.productRole || "comparison";
        const description = role === "base" ? "Base" : value("description");
        return {geometry_id:row.dataset.productId, drawing_no:value("drawing_no"), display_name:description, display_name_custom:true, difference_from_base:role === "comparison" ? description : "", role};
      });
    }

    function conditionSnapshotGroups(){
      return asArray(asObj(requestState.request_context).condition_fieldset_snapshot);
    }

    function conditionGroupsForUi(groups){ return asArray(groups); }

    function conditionFieldByKey(){
      const out = {};
      asArray(asObj(requestState.conditions).fields).forEach(field => { if (field && field.key) out[field.key] = field; });
      return out;
    }

    function conditionValuesMap(){
      return {};
    }

    function conditionOptionsMap(){
      return asObj(asObj(requestState.conditions).condition_options);
    }

    function conditionGroupOptionKey(group){
      const key = contextText(asObj(group).key);
      return key ? `${key}_enabled` : "";
    }

    function conditionGroupEnabled(group){
      const row = asObj(group);
      if (row.optional_section !== true) return true;
      const storageKey = conditionGroupOptionKey(row);
      const checkbox = storageKey ? document.querySelector(`input[data-condition-option="${CSS.escape(storageKey)}"]`) : null;
      if (checkbox) return checkbox.checked;
      const options = conditionOptionsMap();
      if (storageKey && Object.prototype.hasOwnProperty.call(options, storageKey)) return options[storageKey] === true;
      const optionKey = contextText(row.option_key);
      if (optionKey && Object.prototype.hasOwnProperty.call(options, optionKey)) return options[optionKey] === true;
      return false;
    }

    function conditionValueRows(key){
      const rawField = conditionFieldByKey()[key];
      const fieldRows = asArray(asObj(rawField).values);
      if (fieldRows.length) return fieldRows;
      const raw = conditionValuesMap()[key];
      const values = Array.isArray(raw) ? raw : (raw === undefined || raw === null || raw === "" ? [] : [raw]);
      return values.map((value, index) => {
        const text = rowValue(value);
        return {id:`${key}_value_${index+1}`, value:text, status:String(text || "").trim() ? "provided" : "missing", source:"user", display_value:String(text || "")};
      });
    }

    function conditionRowsForRender(key){
      const rows = conditionValueRows(key);
      return rows.length ? rows : [{value:""}];
    }

    function conditionRequirementChip(field){
      const level = contextText(asObj(field).required_level);
      if (level === "conditional_required") return `<span class="chip required">조건부 필수</span>`;
      if (level === "required" || asObj(field).required === true) return `<span class="chip required">필수</span>`;
      return "";
    }

    function hasCandidateRows(field){
      return asArray(field.values).some(row => asObj(row).source === "ai_suggested");
    }

    function isIntegratedProductGroup(value){
      const token = contextText(value).replace(/\s+/g, "").toLowerCase();
      return token.includes("통합형") || token.includes("integrated");
    }

    function shouldShowOperationModeControl(){
      return isContextLocked() && isIntegratedProductGroup(contextFromState().product_group);
    }

    function operationModeControlHtml(){
      if (!shouldShowOperationModeControl()) return "";
      const selected = contextText(contextFromState().operation_mode) || "실내";
      const options = operationModeOptions.map(value => `<option value="${esc(value)}" ${value === selected ? "selected" : ""}>${esc(value)}</option>`).join("");
      return `<label class="operation-mode-control">운전 구분<select id="operationModeSelect">${options}</select></label>`;
    }

    const heatExchangerTypes = ["Fin&Tube", "Micro-Channel"];
    const heatExchangerCascadeKeys = ["tube_diameter", "fin_type", "row_count", "fpi"];

    function heatExchangerType(cards){
      const explicit = contextText(asObj(asArray(cards)[0]).heat_exchanger_type);
      if (heatExchangerTypes.includes(explicit)) return explicit;
      const tubeDiameter = fieldDisplayValue(asObj(asObj(asArray(cards)[0]).fields).tube_diameter);
      return tubeDiameter.toUpperCase().startsWith("W") ? "Micro-Channel" : "Fin&Tube";
    }

    function heatExchangerFieldLabels(type){
      return type === "Micro-Channel"
        ? {tube_diameter:"채널 폭 (Witdth)", fin_type:"Fin type", row_count:"열 수", fpi:"FPDM"}
        : {tube_diameter:"관 직경(Pi)", fin_type:"Fin type", row_count:"열 수", fpi:"FPI"};
    }

    function heatExchangerCatalogValue(row, key, type){
      if (type === "Micro-Channel" && key === "fin_type") return "Flat";
      return contextText(asObj(row)[key]);
    }

    function heatExchangerCatalogRows(type){
      return heatExchangerCatalog.filter(row => {
        const microChannel = contextText(asObj(row).tube_diameter).toUpperCase().startsWith("W");
        return microChannel === (type === "Micro-Channel");
      });
    }

    function heatExchangerOptions(key, selections, type){
      const keyIndex = heatExchangerCascadeKeys.indexOf(key);
      if (keyIndex < 0) return [];
      const filtered = heatExchangerCatalogRows(type).filter(row => heatExchangerCascadeKeys
        .slice(0, keyIndex)
        .every(parentKey => heatExchangerCatalogValue(row, parentKey, type) === contextText(asObj(selections)[parentKey])));
      return uniqueValues(filtered.map(row => heatExchangerCatalogValue(row, key, type)));
    }

    function heatExchangerCustomFieldId(cardId, key){
      return `${contextText(cardId)}:${contextText(key)}`;
    }

    function clearHeatExchangerCustomFields(cardId, keys){
      asArray(keys).forEach(key => heatExchangerCustomFields.delete(heatExchangerCustomFieldId(cardId, key)));
    }

    function heatExchangerSelectHtml(cardId, key, fields, showLabel, fieldLabels, type){
      const selections = Object.fromEntries(heatExchangerCascadeKeys.map(fieldKey => [fieldKey, fieldDisplayValue(fields[fieldKey])]));
      if (type === "Micro-Channel") selections.fin_type = "Flat";
      const keyIndex = heatExchangerCascadeKeys.indexOf(key);
      const parentKeys = heatExchangerCascadeKeys.slice(0, keyIndex);
      const missingParentKey = parentKeys.find(parentKey => !contextText(selections[parentKey])) || "";
      const disabled = key === "fin_type" && type === "Micro-Channel"
        ? true
        : (keyIndex === 0 ? false : !!missingParentKey);
      const options = key === "fin_type" && type === "Micro-Channel" ? ["Flat"] : (disabled ? [] : heatExchangerOptions(key, selections, type));
      const selected = options.includes(contextText(selections[key])) ? contextText(selections[key]) : "";
      const customFieldId = heatExchangerCustomFieldId(cardId, key);
      const customAllowed = !(key === "fin_type" && type === "Micro-Channel");
      const customMode = !disabled && customAllowed && (heatExchangerCustomFields.has(customFieldId) || (!!contextText(selections[key]) && !options.includes(contextText(selections[key]))));
      if (customMode) {
        heatExchangerCustomFields.add(customFieldId);
        const customInput = `<span class="prep-custom-control heat-exchanger-custom-control"><input data-card-id="${esc(cardId)}" data-card-field="${esc(key)}" data-heat-exchanger-custom-field="${esc(key)}" value="${esc(selections[key])}" aria-label="${esc(fieldLabels[key])} 직접 입력" /><button type="button" data-heat-exchanger-restore="${esc(key)}" data-card-id="${esc(cardId)}" title="${esc(fieldLabels[key])} 드롭다운으로 돌아가기" aria-label="${esc(fieldLabels[key])} 드롭다운으로 돌아가기">↩</button></span>`;
        return showLabel ? `<label>${esc(fieldLabels[key])}${customInput}</label>` : customInput;
      }
      const placeholder = disabled && missingParentKey ? `${fieldLabels[missingParentKey]} 먼저 선택` : `${fieldLabels[key]} 선택`;
      const attributes = `data-card-id="${esc(cardId)}" data-card-field="${esc(key)}" data-heat-exchanger-field="${esc(key)}" aria-label="${esc(fieldLabels[key])}"`;
      const customOption = customAllowed && !disabled ? `<option value="__custom__">직접 입력</option>` : "";
      const optionHtml = [`<option value="" disabled hidden ${selected ? "" : "selected"}>${esc(placeholder)}</option>`, ...options.map(value => `<option value="${esc(value)}" ${value === selected ? "selected" : ""}>${esc(value)}</option>`), customOption].join("");
      const select = `<select ${attributes} ${disabled ? "disabled" : ""}>${optionHtml}</select>`;
      return showLabel ? `<label>${esc(fieldLabels[key])}${select}</label>` : select;
    }

    function handleHeatExchangerCascadeChange(select){
      const changedKey = select.dataset.heatExchangerField || "";
      const changedIndex = heatExchangerCascadeKeys.indexOf(changedKey);
      if (changedIndex < 0) return;
      const cards = collectConditionSets();
      const card = cards.find(item => contextText(asObj(item).id) === select.dataset.cardId);
      if (!card) return;
      const downstreamKeys = heatExchangerCascadeKeys.slice(changedIndex + 1);
      clearHeatExchangerCustomFields(card.id, downstreamKeys);
      if (select.value === "__custom__") {
        heatExchangerCustomFields.add(heatExchangerCustomFieldId(card.id, changedKey));
        card.fields[changedKey] = "";
      } else {
        heatExchangerCustomFields.delete(heatExchangerCustomFieldId(card.id, changedKey));
      }
      downstreamKeys.forEach(key => { card.fields[key] = ""; });
      if (heatExchangerType([card]) === "Micro-Channel") card.fields.fin_type = "Flat";
      requestState.conditions = {...asObj(requestState.conditions), condition_sets:cards};
      renderConditionFields();
      const focusKey = select.value === "__custom__" ? changedKey : heatExchangerCascadeKeys[Math.min(changedIndex + 1, heatExchangerCascadeKeys.length - 1)];
      window.requestAnimationFrame(() => document.querySelector(`[data-card-id="${CSS.escape(contextText(card.id))}"][data-heat-exchanger-custom-field="${CSS.escape(focusKey)}"], [data-card-id="${CSS.escape(contextText(card.id))}"][data-heat-exchanger-field="${CSS.escape(focusKey)}"]`)?.focus());
      schedulePreviewRefresh();
    }

    function handleHeatExchangerCustomInput(input){
      const changedKey = input.dataset.heatExchangerCustomField || "";
      const changedIndex = heatExchangerCascadeKeys.indexOf(changedKey);
      if (changedIndex < 0) return;
      const cards = collectConditionSets();
      const card = cards.find(item => contextText(asObj(item).id) === input.dataset.cardId);
      if (!card) return;
      const downstreamKeys = heatExchangerCascadeKeys.slice(changedIndex + 1);
      clearHeatExchangerCustomFields(card.id, downstreamKeys);
      downstreamKeys.forEach(key => { card.fields[key] = ""; });
      if (heatExchangerType([card]) === "Micro-Channel") card.fields.fin_type = "Flat";
      requestState.conditions = {...asObj(requestState.conditions), condition_sets:cards};
      renderConditionFields();
      const focusKey = heatExchangerCascadeKeys[Math.min(changedIndex + 1, heatExchangerCascadeKeys.length - 1)];
      window.requestAnimationFrame(() => document.querySelector(`[data-card-id="${CSS.escape(contextText(card.id))}"][data-heat-exchanger-custom-field="${CSS.escape(focusKey)}"], [data-card-id="${CSS.escape(contextText(card.id))}"][data-heat-exchanger-field="${CSS.escape(focusKey)}"]`)?.focus());
      schedulePreviewRefresh();
    }

    function restoreHeatExchangerDropdown(button){
      const key = button.dataset.heatExchangerRestore || "";
      const keyIndex = heatExchangerCascadeKeys.indexOf(key);
      if (keyIndex < 0) return;
      const cards = collectConditionSets();
      const card = cards.find(item => contextText(asObj(item).id) === button.dataset.cardId);
      if (!card) return;
      const resetKeys = heatExchangerCascadeKeys.slice(keyIndex);
      clearHeatExchangerCustomFields(card.id, resetKeys);
      resetKeys.forEach(fieldKey => { card.fields[fieldKey] = ""; });
      if (heatExchangerType([card]) === "Micro-Channel") card.fields.fin_type = "Flat";
      requestState.conditions = {...asObj(requestState.conditions), condition_sets:cards};
      renderConditionFields();
      window.requestAnimationFrame(() => document.querySelector(`[data-card-id="${CSS.escape(contextText(card.id))}"][data-heat-exchanger-field="${CSS.escape(key)}"]`)?.focus());
      schedulePreviewRefresh();
    }

    function handleHeatExchangerTypeChange(select){
      const selectedType = heatExchangerTypes.includes(select.value) ? select.value : heatExchangerTypes[0];
      const cards = collectConditionSets();
      const card = cards.find(item => contextText(asObj(item).id) === select.dataset.cardId);
      if (!card || contextText(asObj(card).type) !== "heat_exchanger") return;
      clearHeatExchangerCustomFields(card.id, heatExchangerCascadeKeys);
      card.heat_exchanger_type = selectedType;
      card.fields.tube_diameter = "";
      card.fields.fin_type = selectedType === "Micro-Channel" ? "Flat" : "";
      card.fields.row_count = "";
      card.fields.fpi = "";
      requestState.conditions = {...asObj(requestState.conditions), condition_sets:cards};
      renderConditionFields();
      window.requestAnimationFrame(() => document.querySelector(`[data-card-id="${CSS.escape(contextText(card.id))}"][data-heat-exchanger-field="tube_diameter"]`)?.focus());
      schedulePreviewRefresh();
    }

    function heatExchangerTypeSelectHtml(cardId, card, showLabel){
      const selected = heatExchangerType([card]);
      const options = heatExchangerTypes.map(value => `<option value="${esc(value)}" ${value === selected ? "selected" : ""}>${esc(value)}</option>`).join("");
      const select = `<select data-card-id="${esc(cardId)}" data-heat-exchanger-type aria-label="HEX type">${options}</select>`;
      return showLabel ? `<label>HEX type${select}</label>` : select;
    }

    function resizeFanRpmInputs(cardId, rawCount){
      preserveEditorDraftBeforeRerender();
      const count = Math.max(1, Number.parseInt(String(rawCount || "1"), 10) || 1);
      const cards = collectConditionSets();
      const card = cards.find(item => contextText(asObj(item).id) === cardId && contextText(asObj(item).type) === "operating");
      if (!card) return;
      const current = asArray(card.fans);
      card.fans = Array.from({length:count}, (_, index) => {
        const fan = asObj(current[index]);
        return {
          id:`fan_${index + 1}`,
          name:"",
          location:contextText(fan.location),
          running:true,
          values:{fan_rpm:contextText(asObj(fan.values).fan_rpm)},
        };
      });
      requestState.conditions = {...asObj(requestState.conditions), condition_sets:cards};
      renderConditionFields();
      const focusIndex = Math.min(current.length, count - 1);
      const focusField = count >= 2 ? "fan_location" : "fan_rpm";
      window.requestAnimationFrame(() => document.querySelector(`[data-card-id="${CSS.escape(cardId)}"][data-fan-index="${focusIndex}"][data-card-field="${focusField}"]`)?.focus());
      schedulePreviewRefresh();
    }

    function handleFanCountChange(select){
      const cardId = contextText(select.dataset.cardId);
      if (select.value === "__custom__") {
        preserveEditorDraftBeforeRerender();
        fanCountCustomCards.add(cardId);
        renderConditionFields();
        window.requestAnimationFrame(() => document.querySelector(`[data-card-id="${CSS.escape(cardId)}"][data-fan-count-custom]`)?.focus());
        return;
      }
      fanCountCustomCards.delete(cardId);
      resizeFanRpmInputs(cardId, select.value);
    }

    function restoreFanCountDropdown(button){
      const cardId = contextText(button.dataset.cardId);
      fanCountCustomCards.delete(cardId);
      resizeFanRpmInputs(cardId, 1);
      window.requestAnimationFrame(() => document.querySelector(`[data-card-id="${CSS.escape(cardId)}"][data-fan-count]`)?.focus());
    }

    function renderConditionFields(){
      if (!isContextLocked()) {
        $("conditionFields").innerHTML = `<div class="empty">조합 확정 후 조건 입력항목을 표시합니다.</div>`;
        return;
      }
      const cards = asArray(asObj(requestState.conditions).condition_sets);
      const types = uniqueValues(cards.map(card => contextText(asObj(card).type)));
      const temperatureAnalysisTypes = new Set(["풍량", "기류 패턴", "열교환기 유속 프로파일"]);
      const temperatureFieldKeys = new Set(["room_temp", "heat_exchanger_temp"]);
      const temperatureChoiceEnabled = temperatureAnalysisTypes.has(contextText(contextFromState().analysis_type));
      const typeLabels = {operating:"운전 조건",heat_exchanger:"열교환기 사양",supply_air:"취출 공기 조건",space_environment:"공간 환경 조건"};
      const fieldLabels = {name:"사양",fan:"운전",fan_count:"개수",fan_location:"위치",fan_rpm:"팬 회전수(RPM)",fin_type:"Fin type",tube_diameter:"관 직경(Pi)",row_count:"열 수",fpi:"FPI",heat_exchanger_temp:"취출 온도 (°C)",heat_exchanger_rh:"취출 상대습도 (%)",room_temp:"공간 온도 (°C)",room_rh:"공간 상대습도 (%)"};
      const fieldKeysFor = (type, fields) => {
        const orderedKeys = {
          operating: [],
          heat_exchanger: ["name", "tube_diameter", "fin_type", "row_count", "fpi"],
          supply_air: ["heat_exchanger_temp", "heat_exchanger_rh"],
          space_environment: ["room_temp", "room_rh"],
        };
        return (orderedKeys[type] || Object.keys(fields)).filter(key => Object.prototype.hasOwnProperty.call(fields, key));
      };
      const inputHtml = (cardId, key, value, showLabel, fanIndex) => {
        const attributes = fanIndex === undefined
          ? `data-card-id="${esc(cardId)}" data-card-field="${esc(key)}"`
          : `data-card-id="${esc(cardId)}" data-fan-index="${fanIndex}" data-card-field="${esc(key)}"`;
        if (fanIndex === undefined && temperatureChoiceEnabled && temperatureFieldKeys.has(key)) {
          const unavailable = contextText(value) === "없음";
          const menuId = `condition-${cardId}-${key}-mode`;
          const input = `<input ${attributes} value="${esc(value)}" data-undecided-input data-undecided-mode="${unavailable ? "undecided" : "custom"}" data-custom-placeholder="온도를 입력하세요" role="combobox" aria-autocomplete="none" aria-haspopup="listbox" aria-controls="${esc(menuId)}" aria-expanded="false" autocomplete="off" ${unavailable ? "readonly" : ""} aria-label="${esc(fieldLabels[key] || key)}" />`;
          const control = `<div class="undecided-combobox condition-temperature-combobox" data-undecided-combobox data-undecided-value="없음">${input}<button class="undecided-combobox-toggle" type="button" data-undecided-toggle aria-label="${esc(fieldLabels[key] || key)} 입력 방식 선택" aria-controls="${esc(menuId)}" aria-expanded="false"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 9 5 5 5-5"></path></svg></button><div class="undecided-combobox-menu" id="${esc(menuId)}" data-undecided-menu role="listbox" aria-label="${esc(fieldLabels[key] || key)} 입력 방식" hidden><button class="undecided-combobox-option" type="button" role="option" data-undecided-mode="custom" aria-selected="${String(!unavailable)}">직접 입력</button><button class="undecided-combobox-option" type="button" role="option" data-undecided-mode="undecided" aria-selected="${String(unavailable)}">없음</button></div></div>`;
          return showLabel ? `<label>${esc(fieldLabels[key] || key)}${control}</label>` : control;
        }
        const input = `<input ${attributes} value="${esc(value)}" aria-label="${esc(fieldLabels[key] || key)}" />`;
        return showLabel ? `<label>${esc(fieldLabels[key] || key)}${input}</label>` : input;
      };
      const fixedTextHtml = (key, value, showLabel) => {
        const text = `<div class="product-geometry-name condition-spec-name" data-spec-name aria-label="${esc(fieldLabels[key] || key)}" aria-readonly="true">${esc(value)}</div>`;
        return showLabel ? `<label>${esc(fieldLabels[key] || key)}${text}</label>` : text;
      };
      const fanCountControlHtml = (cardId, fans, showLabel) => {
        const count = Math.max(1, fans.length);
        const customMode = fanCountCustomCards.has(cardId) || count > 4;
        let control = "";
        if (customMode) {
          fanCountCustomCards.add(cardId);
          control = `<span class="prep-custom-control fan-count-custom-control"><input type="number" min="1" step="1" inputmode="numeric" data-card-id="${esc(cardId)}" data-fan-count-custom value="${count}" aria-label="개수 직접 입력" /><button type="button" data-fan-count-restore data-card-id="${esc(cardId)}" title="개수 목록으로 돌아가기" aria-label="개수 목록으로 돌아가기">↩</button></span>`;
        } else {
          const options = [1,2,3,4].map(value => `<option value="${value}" ${value === count ? "selected" : ""}>${value}</option>`).join("");
          control = `<select data-card-id="${esc(cardId)}" data-fan-count aria-label="개수">${options}<option value="__custom__">직접 입력</option></select>`;
        }
        return showLabel ? `<label>${esc(fieldLabels.fan_count)}${control}</label>` : control;
      };
      const fanConfigurationInputsHtml = (cardId, fans, showLabel) => {
        const multiple = fans.length >= 2;
        const inputs = fans.map((rawFan, fanIndex) => {
          const fan = asObj(rawFan);
          const label = key => showLabel ? `<span>${esc(fieldLabels[key])}</span>` : "";
          const location = multiple
            ? `<label class="fan-input-column">${label("fan_location")}<input data-card-id="${esc(cardId)}" data-fan-index="${fanIndex}" data-card-field="fan_location" value="${esc(fan.location)}" placeholder="예 : 상/중/하" aria-label="${esc(fieldLabels.fan_location)} ${fanIndex + 1}" /></label>`
            : "";
          const rpm = `<label class="fan-input-column">${label("fan_rpm")}<input data-card-id="${esc(cardId)}" data-fan-index="${fanIndex}" data-card-field="fan_rpm" value="${esc(asObj(fan.values).fan_rpm)}" aria-label="${esc(fieldLabels.fan_rpm)} ${fanIndex + 1}" /></label>`;
          return `<span class="fan-input-set" data-fan-set="${fanIndex + 1}">${location}${rpm}</span>`;
        }).join("");
        return `<span class="fan-configuration-inputs${multiple ? " multiple" : ""}">${inputs}</span>`;
      };
      const rowHtml = (card, isFirst, rowIndex) => {
        const row = asObj(card), cardId = contextText(row.id), type = contextText(row.type), fields = asObj(row.fields);
        const fieldKeys = fieldKeysFor(type, fields);
        const exchangerType = type === "heat_exchanger" ? heatExchangerType([row]) : "";
        const rowFieldLabels = type === "heat_exchanger" ? {...fieldLabels, ...heatExchangerFieldLabels(exchangerType)} : fieldLabels;
        const fans = type === "operating" ? (asArray(row.fans).length ? asArray(row.fans) : [{id:"fan_1",name:"",location:"",running:true,values:{fan_rpm:""}}]) : [];
        const inputs = type === "operating"
          ? `${fixedTextHtml("fan", `운전 ${rowIndex}`, isFirst)}${fanCountControlHtml(cardId, fans, isFirst)}${fanConfigurationInputsHtml(cardId, fans, isFirst)}`
          : fieldKeys.map(key => type === "heat_exchanger" && key === "name"
            ? `${fixedTextHtml(key, `사양 ${rowIndex}`, isFirst)}${heatExchangerTypeSelectHtml(cardId, row, isFirst)}`
            : (type === "heat_exchanger" && heatExchangerCascadeKeys.includes(key)
              ? heatExchangerSelectHtml(cardId, key, fields, isFirst, rowFieldLabels, exchangerType)
              : inputHtml(cardId, key, fieldDisplayValue(fields[key]), isFirst))).join("");
        const remove = `<button class="condition-row-action remove" type="button" data-action="remove-condition-card" data-card-id="${esc(cardId)}" title="조건 행 삭제" aria-label="조건 행 삭제">−</button>`;
        const action = isFirst
          ? `<div class="condition-row-actions"><button class="primary condition-row-action" type="button" data-action="add-condition-card" data-card-type="${esc(type)}" title="${esc(typeLabels[type])} 추가" aria-label="${esc(typeLabels[type])} 추가">+</button></div>`
          : `<div class="condition-row-actions">${remove}</div>`;
        return `<div class="condition-card-row" data-condition-card="${esc(cardId)}" style="--field-count:${type === "operating" ? 3 : fieldKeys.length}">${inputs}${action}</div>`;
      };
      const groupHtml = type => {
        const list = cards.filter(card => contextText(asObj(card).type) === type);
        if (!list.length) return "";
        const body = `<div class="condition-card-rows">${list.map((card, index) => rowHtml(card, index === 0, index + 1)).join("")}</div>`;
        const operatingFanCount = type === "operating" ? Math.max(1, ...list.map(card => Math.max(1, asArray(asObj(card).fans).length))) : 1;
        const operatingExtraWidth = operatingFanCount > 1 ? 78 + ((operatingFanCount - 1) * 186) : 0;
        const widthStyle = type === "operating" ? ` style="--operating-extra-width:${operatingExtraWidth}px"` : "";
        return `<article class="condition-group condition-card-type condition-card-type-${esc(type)}"${widthStyle}><div class="condition-group-head"><h3>${esc(typeLabels[type])}</h3></div>${body}</article>`;
      };
      const primary = types.filter(type => type !== "supply_air" && type !== "space_environment").map(groupHtml).join("");
      const environment = ["space_environment", "supply_air"].filter(type => types.includes(type)).map(groupHtml).join("");
      $("conditionFields").innerHTML = `<div class="condition-card-layout">${primary ? `<div class="condition-primary-grid">${primary}</div>` : ""}${environment ? `<div class="condition-environment-grid">${environment}</div>` : ""}</div>`;
      wireUndecidedComboboxes($("conditionFields"));
    }

    function syncEditorFromState(){
      syncRequestContextDraftFromState();
      const basic = asObj(requestState.basic_info);
      basicKeys.forEach(key => {
        const input = pathInput("basic_info", key);
        const value = fieldDisplayValue(basic[key]);
        if (input) input.value = value;
        syncDropdownForPath(`basic_info.${key}`, value);
      });
      const overview = asObj(requestState.analysis_overview);
      overviewInputKeys.forEach(key => {
        const input = pathInput("analysis_overview", key);
        const value = fieldDisplayValue(overview[key]);
        if (input) input.value = value;
        syncDropdownForPath(`analysis_overview.${key}`, value);
        syncUndecidedCombobox(`analysis_overview.${key}`, value);
      });
      const geometry = asObj(requestState.geometry);
      renderProductCards(geometry.base_product, geometry.comparison_products);
      renderConditionFields();
      renderRequestPrepCard();
      refreshAnalysisResultGuidance();
      updateGate();
      renderDerivedPanels();
      updateTopChrome();
    }
    function collectConditionSets(){
      let heatExchangerIndex = 0;
      let operatingIndex = 0;
      return asArray(asObj(requestState.conditions).condition_sets).map(raw => {
        const card = JSON.parse(JSON.stringify(raw));
        const id = contextText(card.id);
        if (contextText(card.type) === "heat_exchanger") {
          const typeSelect = document.querySelector(`select[data-card-id="${CSS.escape(id)}"][data-heat-exchanger-type]`);
          card.heat_exchanger_type = heatExchangerTypes.includes(typeSelect?.value) ? typeSelect.value : heatExchangerType([card]);
        }
        asArray(card.fans).forEach((fan, index) => {
          const locationInput = document.querySelector(`[data-card-id="${CSS.escape(id)}"][data-fan-index="${index}"][data-card-field="fan_location"]`);
          const rpmInput = document.querySelector(`[data-card-id="${CSS.escape(id)}"][data-fan-index="${index}"][data-card-field="fan_rpm"]`) || (card.fans.length === 1 ? document.querySelector(`[data-card-id="${CSS.escape(id)}"][data-card-field="fan_rpm"]`) : null);
          fan.location = locationInput ? locationInput.value.trim() : "";
          if (rpmInput) fan.values = {fan_rpm: rpmInput.value.trim()};
        });
        Object.keys(asObj(card.fields)).forEach(key => { const input = document.querySelector(`[data-card-id="${CSS.escape(id)}"][data-card-field="${key}"]`); if (input) card.fields[key] = input.value.trim(); });
        if (contextText(card.type) === "operating") {
          card.name = `운전 ${++operatingIndex}`;
          card.fan_count = asArray(card.fans).length;
          card.fan_locations = asArray(card.fans).map(fan => contextText(asObj(fan).location));
          card.fan_rpms = asArray(card.fans).map(fan => contextText(asObj(asObj(fan).values).fan_rpm));
        }
        if (contextText(card.type) === "heat_exchanger") card.fields.name = `사양 ${++heatExchangerIndex}`;
        return card;
      });
    }

    async function refreshAnalysisResultGuidance(){
      const root = $("analysisResultGuidance");
      if (!root) return;
      const analysisType = contextText(contextFromState().analysis_type);
      const label = $("analysisResultGuidanceLabel");
      if (label) label.textContent = `해석 결과 안내${analysisType ? ` - ${analysisType}` : ""}`;
      const panel = message => `<span class="analysis-result-guidance-icon" aria-hidden="true">i</span><p>${message}</p>`;
      if (!analysisType) {
        root.innerHTML = panel("해석유형을 선택하면 결과 안내를 표시합니다.");
        return;
      }
      root.innerHTML = panel("해석 결과 안내를 불러오는 중입니다.");
      try {
        const response = await fetch(`/api/analysis-type-guidance?analysis_type=${encodeURIComponent(analysisType)}`);
        const data = await response.json();
        if (!response.ok || data.ok === false) throw new Error(data.message || "결과 안내를 조회하지 못했습니다.");
        root.innerHTML = panel(esc(data.guidance || ""));
      } catch (err) {
        root.innerHTML = `<span class="analysis-result-guidance-icon" aria-hidden="true">i</span><div><p>해석 결과 안내를 불러오지 못했습니다.</p><button class="ghost" type="button" id="retryAnalysisResultGuidance">다시 시도</button></div>`;
      }
    }


    function collectCaseRows(){
      return asArray(asObj(requestState.case_matrix).rows).map(raw => {
        const row = JSON.parse(JSON.stringify(raw));
        const id = contextText(row.case_id);
        const geometry = document.querySelector(`select[data-case-row-id="${CSS.escape(id)}"][data-case-field="geometry_id"]`);
        if (geometry) row.geometry_id = geometry.value;
        const values = {...asObj(row.condition_values)};
        document.querySelectorAll(`select[data-case-row-id="${CSS.escape(id)}"][data-case-field]`).forEach(select => {
          const key = select.dataset.caseField;
          if (key && key !== "geometry_id") values[key] = select.value;
        });
        row.condition_values = values;
        return row;
      });
    }

    function collectState(){
      const products = collectProductCards();
      const next = {
        metadata: {
          ...asObj(requestState.metadata),
          rag_enabled: false,
          rag_scope: "LG CFD Reports 2025 해석보고서",
          rag_ranking: "product_first",
          active_top_tab: "write",
          touched_fields: Array.from(touchedFields),
          chat_history: chatHistory,
        },
        request_context: collectRequestContextDraft(),
        basic_info: {},
        analysis_overview: {},
        geometry: {
          base_product: products[0] || asObj(requestState.geometry).base_product,
          comparison_products: products.slice(1),
        },
        conditions: {
          mode: asObj(requestState.conditions).mode || "standard",
          condition_sets: collectConditionSets(),
        },
        case_matrix: { ...asObj(requestState.case_matrix), rows: collectCaseRows() },
      };
      basicKeys.forEach(key => { const input = pathInput("basic_info", key); next.basic_info[key] = input ? input.value : ""; });
      overviewInputKeys.forEach(key => { const input = pathInput("analysis_overview", key); next.analysis_overview[key] = input ? input.value : ""; });
      return next;
    }

    function preserveEditorDraftBeforeRerender(){
      // Condition row actions rebuild the whole editor. Capture every visible
      // screen first so geometry and overview edits are not replaced by an
      // older asynchronous preview response still stored in requestState.
      requestState = collectState();
    }

    async function postJson(url, payload){
      const res = await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload || {})});
      const text = await res.text();
      let data = {};
      try {
        data = text ? JSON.parse(text) : {};
      } catch (err) {
        throw new Error(`서버 응답을 읽지 못했습니다 (${res.status}). ${text.slice(0, 120)}`);
      }
      if (!res.ok || data.ok === false) {
        const missing = asArray(data.missing_fields).length ? ` 누락: ${asArray(data.missing_fields).join(", ")}` : "";
        throw new Error((data.assistant || data.message || `Request failed: ${res.status}`) + missing);
      }
      return data;
    }

    async function postState(url, extra={}){
      return postJson(url, {state:collectState(), ...extra});
    }

    async function startNewRequest(){
      const data = await postJson("/api/request/new", {});
      Object.assign(orchestratorPanelState, {conversationId:"", requestId:"", requestVersion:null, dirty:true, loading:false, caseMatrixSyncedRequestId:"", caseMatrixSyncedRequestVersion:null, previewRenderedRequestId:"", previewRenderedRequestVersion:null, latestApprovedState:null});
      orchestratorPanelState.decisionIds.clear();
      orchestratorPanelState.refreshedProposalIds.clear();
      touchedFields.clear();
      heatExchangerCustomFields.clear();
      fanCountCustomCards.clear();
      chatHistory = [];
      requestContextDraft = fallbackRequestContext();
      activeTopTab = "write";
      activePrepMode = "quick";
      quickProductGroupCustomMode = false;
      quickPlatformCustomMode = false;
      prepAssistStarted = false;
      recommendMode = false;
      lastPlannerActiveFieldId = "";
      adoptStateFromResponse(data);
      resetCaseImpactBaseline();
      restoreChatHistoryFromState();
      syncEditorFromState();
    }

    function adoptStateFromResponse(data){
      requestState = asObj(data).state || requestState;
      if (Object.prototype.hasOwnProperty.call(asObj(data), "candidate_conditions")) {
        requestState.candidate_conditions = data.candidate_conditions || {};
      }
    }

    function schedulePreviewRefresh(){
      renderScreenNavigation();
      orchestratorPanelState.dirty = true;
      classifyCaseImpact(collectState());
      window.setTimeout(() => refreshPreview(), 650);
    }

    async function refreshPreview(){
      const data = await postState("/api/preview");
      adoptStateFromResponse(data);
      renderDerivedPanels();
    }

    const CASE_REVIEW_REQUIRED = "CASE_REVIEW_REQUIRED";
    const CASE_REBUILD_REQUIRED = "CASE_REBUILD_REQUIRED";
    let caseImpactBaseline = null;
    let caseImpactSideState = {status:"", reasons:[]};
    let caseConfigurationWarning = "";

    function sourceFieldValue(value){
      return contextText(asObj(value).value ?? value);
    }

    function caseImpactSources(state){
      const geometry = new Map();
      const allProducts = [asObj(asObj(state).geometry).base_product, ...asArray(asObj(asObj(state).geometry).comparison_products)];
      allProducts.forEach(product => {
        const row = asObj(product), id = contextText(row.geometry_id);
        if (id) geometry.set(id, sourceFieldValue(row.drawing_no));
      });
      const conditions = new Map();
      asArray(asObj(asObj(state).conditions).condition_sets).forEach(card => {
        const row = asObj(card), cardId = contextText(row.id);
        Object.entries(asObj(row.fields)).forEach(([key, value]) => conditions.set(`${cardId}:${key}`, sourceFieldValue(value)));
        asArray(row.fans).forEach((fan, index) => conditions.set(`${cardId}:fan_${index + 1}_rpm`, sourceFieldValue(asObj(fan).values?.fan_rpm)));
      });
      return {geometry, conditions};
    }

    function resetCaseImpactBaseline(){
      caseImpactBaseline = {sources:caseImpactSources(requestState), rows:asArray(asObj(requestState.case_matrix).rows).map(row => JSON.parse(JSON.stringify(row)))};
      caseImpactSideState = {status:"", reasons:[]};
      caseConfigurationWarning = "";
    }

    function hasConditionReference(rows, value){
      return rows.some(row => Object.values(asObj(row).condition_values).some(item => contextText(item) === value));
    }

    function classifyCaseImpact(state){
      if (!caseImpactBaseline) return false;
      const current = caseImpactSources(state), baseline = caseImpactBaseline.sources, rows = caseImpactBaseline.rows;
      const rebuildReasons = [], reviewReasons = [];
      baseline.geometry.forEach((drawingNo, id) => {
        const referenced = rows.some(row => contextText(asObj(row).geometry_id) === id);
        if (!current.geometry.has(id)) {
          (referenced ? rebuildReasons : reviewReasons).push(`geometry:${id}:deleted`);
        } else if (current.geometry.get(id) !== drawingNo) {
          (referenced ? rebuildReasons : reviewReasons).push(`geometry:${id}:identifier_changed`);
          if (!current.geometry.get(id) && referenced) rebuildReasons.push(`geometry:${id}:required_value_invalid`);
        }
      });
      current.geometry.forEach((_drawingNo, id) => { if (!baseline.geometry.has(id)) reviewReasons.push(`geometry:${id}:added`); });
      baseline.conditions.forEach((value, key) => {
        const referenced = value && hasConditionReference(rows, value);
        if (!current.conditions.has(key)) {
          (referenced ? rebuildReasons : reviewReasons).push(`condition:${key}:deleted`);
        } else if (current.conditions.get(key) !== value) {
          (referenced ? rebuildReasons : reviewReasons).push(`condition:${key}:identifier_changed`);
          if (!current.conditions.get(key) && referenced) rebuildReasons.push(`condition:${key}:required_value_invalid`);
        }
      });
      current.conditions.forEach((_value, key) => { if (!baseline.conditions.has(key)) reviewReasons.push(`condition:${key}:added`); });
      caseImpactSideState = rebuildReasons.length
        ? {status:CASE_REBUILD_REQUIRED, reasons:rebuildReasons}
        : reviewReasons.length ? {status:CASE_REVIEW_REQUIRED, reasons:reviewReasons} : {status:"", reasons:[]};
      return Boolean(caseImpactSideState.status);
    }

    function caseImpactNoticeHtml(){
      const notices = [];
      if (caseImpactSideState.status === CASE_REBUILD_REQUIRED) {
        const message = "참조된 소스가 삭제·식별값 변경·필수값 무효화되었습니다. Case 행은 자동으로 변경하지 않았습니다.";
        notices.push(`<div class="case-impact-notice" data-case-impact-status="${CASE_REBUILD_REQUIRED}"><strong>${CASE_REBUILD_REQUIRED}</strong><span>${message}</span></div>`);
      }
      if (caseConfigurationWarning) notices.push(`<div class="case-impact-notice" data-case-configuration-warning><strong>Case 구성 확인</strong><span>${caseConfigurationWarning}</span></div>`);
      return notices.join("");
    }

    function caseSourceReferenceHtml(){
      const matrix = asObj(requestState.case_matrix);
      const options = asObj(matrix.dropdown_options);
      const geometry = asObj(requestState.geometry);
      const products = [asObj(geometry.base_product), ...asArray(geometry.comparison_products)];
      const productsById = new Map(products.map(product => [contextText(product.geometry_id), product]));
      const conditionSets = asArray(asObj(requestState.conditions).condition_sets);
      const operatingByName = new Map(conditionSets
        .filter(card => contextText(asObj(card).type) === "operating")
        .map(card => [contextText(asObj(card).name), asObj(card)]));
      const specificationByName = new Map(conditionSets
        .filter(card => contextText(asObj(card).type) === "heat_exchanger")
        .map(card => [fieldDisplayValue(asObj(asObj(card).fields).name), asObj(card)]));
      const listHtml = (items, detailsFor) => {
        const rows = asArray(items).map(raw => {
          const item = asObj(raw), value = contextText(item.value), label = contextText(item.label) || value;
          return `<li><strong class="case-source-name">${esc(label)}</strong><span class="case-source-details">${esc(detailsFor(value))}</span></li>`;
        }).join("");
        return rows || `<li><strong class="case-source-name">입력값 없음</strong><span class="case-source-details">-</span></li>`;
      };
      const geometryList = listHtml(options.geometry_id, value => {
        const product = asObj(productsById.get(value));
        const description = contextText(product.role) === "base" ? "Base" : productDescription(product, true) || "-";
        return `도면번호: ${productText(product, "drawing_no") || "-"} · 설명: ${description}`;
      });
      const operatingList = listHtml(options.fan, value => {
        const card = asObj(operatingByName.get(value));
        const fans = asArray(card.fans);
        const fanSets = fans.map(rawFan => {
          const fan = asObj(rawFan), location = contextText(fan.location), rpm = contextText(asObj(fan.values).fan_rpm) || "-";
          return fans.length >= 2 && location ? `${location}: ${rpm}` : rpm;
        });
        return `개수: ${Math.max(1, fans.length)} · 팬 위치/회전수(RPM): ${fanSets.join(", ") || "-"}`;
      });
      const specificationList = listHtml(options.heat_exchanger, value => {
        const card = asObj(specificationByName.get(value)), fields = asObj(card.fields);
        const type = heatExchangerType([card]), labels = heatExchangerFieldLabels(type);
        const detail = key => fieldDisplayValue(fields[key]) || "-";
        return `HEX type: ${type} · ${labels.tube_diameter}: ${detail("tube_diameter")} · ${labels.fin_type}: ${detail("fin_type")} · ${labels.row_count}: ${detail("row_count")} · ${labels.fpi}: ${detail("fpi")}`;
      });
      return `<div class="case-source-reference" aria-label="Case 선택 기준 입력값"><p class="case-source-guidance">아래 입력값을 확인하고 Case별 형상·운전·사양을 선택해 주세요.</p><ul class="case-source-list">${geometryList}${operatingList}${specificationList}</ul></div>`;
    }

    function caseTableHtml(){
      const matrix = asObj(requestState.case_matrix);
      const columns = asArray(matrix.visible_columns);
      const rows = asArray(matrix.rows);
      const optionMap = asObj(matrix.dropdown_options);
      if (!columns.length || !rows.length) return `<div class="empty">형상 또는 Case 추가 후 직접 매핑해 주세요.</div>`;
      const select = (rowId, key, selected, options) => `<select data-case-row-id="${esc(rowId)}" data-case-field="${esc(key)}"><option value="">선택</option>${asArray(options).map(option => { const item = asObj(option); const value = contextText(item.value); return `<option value="${esc(value)}" ${value === contextText(selected) ? "selected" : ""}>${esc(item.label || value)}</option>`; }).join("")}</select>`;
      const head = columns.map(column => `<th>${esc(asObj(column).label || asObj(column).key)}</th>`).join("");
      const body = rows.map((raw, index) => {
        const row = asObj(raw), id = contextText(row.case_id), values = asObj(row.condition_values);
        return `<tr data-case-row="${esc(id)}">${columns.map(column => {
          const item = asObj(column), key = contextText(item.key);
          if (key === "case_no") return `<td>${index + 1}</td>`;
          if (key === "remove") return `<td><button class="icon" data-action="remove-case" data-case-id="${esc(id)}" title="Case 제거" aria-label="Case 제거">-</button></td>`;
          const selected = key === "geometry_id" ? row.geometry_id : values[key];
          return `<td>${select(id, key, selected, optionMap[key])}</td>`;
        }).join("")}</tr>`;
      }).join("");
      return `<div class="matrix-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
    }

    function renderCasePreview(){
      $("caseCommon").innerHTML = caseImpactNoticeHtml();
      $("caseMatrix").innerHTML = `${caseSourceReferenceHtml()}${caseTableHtml()}`;
    }

    function focusCaseValidationIssue(issue){
      const path = contextText(asObj(issue).path);
      const rowIndex = Number.parseInt((path.match(/case_matrix\.rows\[(\d+)\]/) || [])[1] || "-1", 10);
      const row = asArray(asObj(requestState.case_matrix).rows)[rowIndex];
      const fieldKey = contextText(asObj(issue).field_key) || (path.endsWith(".geometry_id") ? "geometry_id" : "");
      const target = row && fieldKey
        ? document.querySelector(`select[data-case-row-id="${CSS.escape(contextText(asObj(row).case_id))}"][data-case-field="${CSS.escape(fieldKey)}"]`)
        : document.querySelector('[data-action="add-case"]');
      (target || $("section-case"))?.scrollIntoView({behavior:"smooth", block:"center"});
      if (target) {
        target.classList.add("field-highlight");
        target.focus();
        window.setTimeout(() => target.classList.remove("field-highlight"), 1800);
      }
    }

    async function confirmCaseConfiguration(){
      const action = $("caseConfirmNextBtn");
      if (action?.disabled) return;
      if (action) action.disabled = true;
      try {
        await refreshPreview();
        const blocking = asArray(asObj(asObj(requestState.review).validator).blocking)
          .filter(issue => contextText(asObj(issue).section) === "case_matrix");
        if (blocking.length) {
          caseConfigurationWarning = blocking.some(issue => contextText(asObj(issue).code) === "case_matrix.duplicate")
            ? "동일한 형상과 해석 조건을 가진 Case가 있습니다. 중복 Case를 수정하거나 제거해 주세요."
            : "Case 구성에 오류가 있습니다. 표시된 Case 행을 수정해 주세요.";
          renderCasePreview();
          focusCaseValidationIssue(blocking[0]);
          return;
        }
        resetCaseImpactBaseline();
        renderCasePreview();
        navigateScreen("SCREEN-06");
      } finally {
        if (action) action.disabled = false;
      }
    }

    function renderDerivedPanels(){
      renderCasePreview();
      renderDocumentPreviewPanel();
      renderCandidateNotice();
    }

    function renderDocumentPreviewPanel(sourceState, previewReceipt){
      const panel = $("documentPreviewPanel");
      if (!panel) return;
      const state = asObj(sourceState === undefined ? requestState : sourceState);
      const value = field => (field && typeof field === "object" ? fieldDisplayValue(field, "-") : String(field ?? "").trim()) || "-";
      const kv = (label, field) => `<div class="preview-kv" data-preview-field="${esc(label)}"><span data-preview-label>${esc(label)}</span><span data-preview-value>${esc(value(field))}</span></div>`;
      const section = (key, title, body) => `<section class="preview-section" id="preview-section-${esc(key)}" data-preview-section="${esc(key)}"><h4 data-preview-section-title>${esc(title)}</h4>${body}</section>`;
      const overview = asObj(state.analysis_overview);
      const context = asObj(state.request_context);
      const products = [asObj(asObj(state.geometry).base_product), ...asArray(asObj(state.geometry).comparison_products)].filter(product => Object.keys(product).length);
      const productRows = products.length ? products.map((product, index) => `<tr data-preview-product="${esc(product.role || (index ? "comparison" : "base"))}"><td>${esc(`형상 ${index + 1}`)}</td><td>${esc(productText(product, "drawing_no") || "-")}</td><td>${esc(index ? productDescription(product, true) || "-" : "Base")}</td></tr>`).join("") : `<tr><td colspan="3">등록된 제품이 없습니다.</td></tr>`;
      const conditionLabels = {operating:"운전 조건",heat_exchanger:"열교환기 사양",supply_air:"취출 공기 조건",space_environment:"공간 환경 조건",name:"사양",fan:"운전",fan_rpm:"팬 회전수(RPM)",fin_type:"Fin type",tube_diameter:"관 직경(Pi)",row_count:"열 수",fpi:"FPI",heat_exchanger_temp:"취출 온도 (°C)",heat_exchanger_rh:"취출 상대습도 (%)",room_temp:"공간 온도 (°C)",room_rh:"공간 상대습도 (%)"};
      const previewFieldKeysFor = (type, fields) => {
        const orderedKeys = {
          operating: [],
          heat_exchanger: ["tube_diameter", "fin_type", "row_count", "fpi"],
          supply_air: ["heat_exchanger_temp", "heat_exchanger_rh"],
          space_environment: ["room_temp", "room_rh"],
        };
        return (orderedKeys[type] || Object.keys(fields)).filter(key => Object.prototype.hasOwnProperty.call(fields, key));
      };
      const previewConditionName = (row, cardType) => {
        if (cardType === "operating") return contextText(row.name);
        if (cardType === "heat_exchanger") return contextText(fieldDisplayValue(asObj(row.fields).name));
        return "";
      };
      const previewConditionTitle = (row, cardType) => {
        const title = conditionLabels[cardType] || row.label || row.id || "조건";
        const name = previewConditionName(row, cardType);
        return name ? `${title} (${name})` : title;
      };
      const previewConditionOrder = {operating: 10, heat_exchanger: 20, space_environment: 30, supply_air: 40};
      const conditionRows = asArray(asObj(state.conditions).condition_sets)
        .slice()
        .sort((left, right) => (previewConditionOrder[contextText(asObj(left).type)] || 99) - (previewConditionOrder[contextText(asObj(right).type)] || 99))
        .map(card => {
        const row = asObj(card);
        const cardType = contextText(row.type);
        const cardLabels = cardType === "heat_exchanger" ? {...conditionLabels, ...heatExchangerFieldLabels(heatExchangerType([row]))} : conditionLabels;
        const fields = previewFieldKeysFor(contextText(row.type), asObj(row.fields)).map(key => `${cardLabels[key] || key}: ${value(asObj(row.fields)[key])}`);
        const rowFans = asArray(row.fans);
        const fanSets = rowFans.map(rawFan => {
          const fan = asObj(rawFan), location = value(fan.location), rpm = value(asObj(fan.values).fan_rpm);
          return rowFans.length >= 2 && location !== "-" ? `${location}: ${rpm}` : rpm;
        });
        const fans = cardType === "operating" ? [`개수: ${Math.max(1, fanSets.length)} · 팬 위치/회전수(RPM): ${fanSets.join(", ") || "-"}`] : [];
        return `<tr data-preview-condition-card="${esc(row.id || "")}"><td>${esc(previewConditionTitle(row, cardType))}</td><td>${esc([...fans, ...fields].join(" / ") || "-")}</td></tr>`;
      }).join("") || `<tr><td colspan="2">해석 조건이 없습니다.</td></tr>`;
      const matrix = asObj(state.case_matrix);
      const matrixColumns = asArray(matrix.visible_columns).filter(column => asObj(column).key !== "remove");
      const matrixRows = asArray(matrix.rows).map(item => { const row = asObj(item); const cells = asObj(row.visible_cells); return `<tr data-preview-case="${esc(row.case_id || "")}">${matrixColumns.map(column => `<td>${esc(cells[asObj(column).key] || "-")}</td>`).join("")}</tr>`; }).join("");
      const matrixTable = matrixColumns.length && matrixRows ? `<div class="matrix-wrap"><table class="preview-table" data-preview-table="case_matrix"><thead><tr>${matrixColumns.map(column => `<th>${esc(asObj(column).label || asObj(column).key)}</th>`).join("")}</tr></thead><tbody>${matrixRows}</tbody></table></div>` : `<div class="empty" data-preview-matrix-empty>생성된 Case가 없습니다.</div>`;
      panel.innerHTML = `<div class="preview-doc" data-preview-document="current-state">
        ${section("overview", "해석개요", kv("프로젝트명(PMS)", overview.project_name) + kv("모델명(Model Suffix)", overview.model_suffix) + kv("개발 등급", overview.development_grade) + kv("NPI 단계", overview.npi_stage) + kv("의뢰 요청일", overview.request_date) + kv("희망 완료일", overview.desired_completion_date) + kv("해석을 요청하게 된 배경", overview.request_description) + kv("해석으로 확인하고 싶은 내용", overview.additional_result_request) + kv("해석유형", context.analysis_type))}
        ${section("geometry", "해석 제품", `<div class="matrix-wrap"><table class="preview-table" data-preview-table="geometry"><thead><tr><th>형상</th><th>도면번호 (NPDM MCAD)</th><th>설명</th></tr></thead><tbody>${productRows}</tbody></table></div>`)}
        ${section("conditions", "해석 조건", `<div class="matrix-wrap"><table class="preview-table" data-preview-table="conditions"><thead><tr><th>조건</th><th>입력값</th></tr></thead><tbody>${conditionRows}</tbody></table></div>`)}
        ${section("case-matrix", "Case Matrix", matrixTable)}
      </div>`;
      const renderedDocument = panel.querySelector('[data-preview-document="current-state"]');
      const receipt = asObj(previewReceipt);
      if (renderedDocument && receipt.requestId && Number.isFinite(receipt.requestVersion)) {
        renderedDocument.dataset.orchestratorPreviewRequestId = receipt.requestId;
        renderedDocument.dataset.orchestratorPreviewRequestVersion = String(receipt.requestVersion);
      } else {
        orchestratorPanelState.previewRenderedRequestId = "";
        orchestratorPanelState.previewRenderedRequestVersion = null;
      }
    }

    function renderCandidateNotice(){
      const candidate = asObj(requestState.candidate_conditions || {});
      const count = candidate.count ?? countCandidateRows();
      const el = $("candidateNotice");
      if (count > 0) {
        el.style.display = "none";
        el.innerHTML = "";
      } else {
        el.style.display = "none";
        el.innerHTML = "";
      }
    }

    function countCandidateRows(){
      return asArray(asObj(requestState.conditions).fields).reduce((sum, field) => sum + asArray(field.values).filter(row => asObj(row).source === "ai_suggested").length, 0);
    }

    function defaultChatHistory(){
      return [{role:"assistant", content:"제품군, platform, 해석유형을 선택한 뒤 의뢰 내용을 입력해 주세요.", html:""}];
    }

    function normalizeChatHistory(items){
      const normalized = asArray(items)
        .map(item => {
          const row = asObj(item);
          const role = row.role === "user" ? "user" : "assistant";
          const content = String(row.content ?? "");
          const html = String(row.html ?? "");
          if (!content.trim() && !html.trim()) return null;
          return {role, content, html};
        })
        .filter(Boolean)
        .slice(-200);
      return normalized.length ? normalized : defaultChatHistory();
    }

    function isAgentOverlay(){
      return window.matchMedia("(max-width: 1039px)").matches;
    }

    function setPanelRatio(ratio){
      const layout = document.querySelector(".layout");
      const resizer = $("panelResizer");
      if (!layout || !resizer) return;
      const clamped = Math.min(3, Math.max(1, Number(ratio) || 2));
      layout.style.gridTemplateColumns = `minmax(0,${clamped}fr) 12px minmax(0,1fr)`;
      resizer.setAttribute("aria-valuenow", String(Math.round(clamped * 100) / 100));
    }

    function resetPanelRatio(){
      document.querySelector(".layout")?.style.removeProperty("grid-template-columns");
      $("panelResizer")?.setAttribute("aria-valuenow", "2");
    }

    function initPanelResizer(){
      const resizer = $("panelResizer");
      const workspace = document.querySelector(".workspace-content");
      const dock = $("agentDock");
      if (!resizer || !workspace || !dock) return;
      let drag = null;
      const finishDrag = event => {
        if (!drag) return;
        if (event?.pointerId === drag.pointerId && resizer.hasPointerCapture?.(event.pointerId)) resizer.releasePointerCapture(event.pointerId);
        drag = null;
        resizer.classList.remove("is-dragging");
        document.body.classList.remove("panel-resizing");
      };
      resizer.addEventListener("pointerdown", event => {
        if (event.button !== 0 || isAgentOverlay() || !agentOpen) return;
        const leftWidth = workspace.getBoundingClientRect().width;
        const rightWidth = dock.getBoundingClientRect().width;
        const totalWidth = leftWidth + rightWidth;
        if (totalWidth <= 0) return;
        drag = {pointerId:event.pointerId, startX:event.clientX, startLeft:leftWidth, totalWidth};
        resizer.setPointerCapture?.(event.pointerId);
        resizer.classList.add("is-dragging");
        document.body.classList.add("panel-resizing");
        event.preventDefault();
      });
      resizer.addEventListener("pointermove", event => {
        if (!drag || event.pointerId !== drag.pointerId) return;
        const nextLeft = Math.min(drag.totalWidth * .75, Math.max(drag.totalWidth * .5, drag.startLeft + event.clientX - drag.startX));
        setPanelRatio(nextLeft / (drag.totalWidth - nextLeft));
      });
      resizer.addEventListener("pointerup", finishDrag);
      resizer.addEventListener("pointercancel", finishDrag);
    }

    function agentRestoreFocusTarget(){
      if (lastAgentFocus && document.contains(lastAgentFocus) && !lastAgentFocus.disabled) return lastAgentFocus;
      if ($("chatInput")?.value.trim()) return $("chatInput");
      return $("agentDockHeading");
    }

    function renderAgentDock(){
      const layout = document.querySelector(".layout");
      const dock = $("agentDock");
      const openButton = $("agentOpenBtn");
      const hideButton = $("agentHideBtn");
      if (!layout || !dock || !openButton || !hideButton) return;
      layout.classList.toggle("agent-hidden", !agentOpen);
      dock.setAttribute("aria-hidden", String(!agentOpen));
      openButton.hidden = agentOpen;
      openButton.setAttribute("aria-expanded", String(agentOpen));
      hideButton.setAttribute("aria-expanded", String(agentOpen));
    }

    function setAgentOpen(open, options={}){
      const nextOpen = Boolean(open);
      if (nextOpen === agentOpen) return;
      const dock = $("agentDock");
      if (!nextOpen && dock?.contains(document.activeElement)) lastAgentFocus = document.activeElement;
      agentOpen = nextOpen;
      resetPanelRatio();
      renderAgentDock();
      if (!nextOpen) {
        $("agentOpenBtn")?.focus();
        return;
      }
      if (options.restoreFocus !== false) window.requestAnimationFrame(() => agentRestoreFocusTarget()?.focus());
    }

    function syncChatMetadata(){
      requestState.metadata = {...asObj(requestState.metadata), chat_history: chatHistory};
    }

    function renderChatHistory(){
      $("chatLog").innerHTML = "";
      replayingChat = true;
      normalizeChatHistory(chatHistory).forEach(item => pushMessage(item.role, item.content, item.html));
      replayingChat = false;
      $("chatLog").scrollTop = $("chatLog").scrollHeight;
    }

    function restoreChatHistoryFromState(){
      chatHistory = normalizeChatHistory(asObj(requestState.metadata).chat_history);
      syncChatMetadata();
      renderChatHistory();
    }

    function resetChatHistory(){
      chatHistory = defaultChatHistory();
      syncChatMetadata();
      renderChatHistory();
    }

    async function clearAgentConversation(){
      if (orchestratorPanelState.loading) return;
      const conversationId = orchestratorPanelState.conversationId;
      orchestratorPanelState.conversationId = "";
      orchestratorPanelState.dirty = true;
      recommendMode = false;
      lastPlannerActiveFieldId = "";
      chatHistory = [];
      syncChatMetadata();
      $("chatLog").replaceChildren();
      $("chatInput").value = "";
      if (!conversationId) {
        $("chatInput").focus();
        return;
      }
      setOrchestratorLoading(true);
      try {
        await fetch(`/api/conversations/${encodeURIComponent(conversationId)}/close`, {
          method:"POST", headers:{"Content-Type":"application/json"}, body:"{}",
        });
      } catch (_err) {
        // The local chat remains cleared and the next message starts a new conversation.
      } finally {
        setOrchestratorLoading(false);
        $("chatInput").focus();
      }
    }

    function pushMessage(role, content, html=""){
      const msg = document.createElement("div");
      msg.className = `msg ${role}`;
      if (html) msg.innerHTML = html; else msg.textContent = content;
      $("chatLog").appendChild(msg);
      $("chatLog").scrollTop = $("chatLog").scrollHeight;
      if (!replayingChat) {
        chatHistory = normalizeChatHistory([...chatHistory, {role, content:String(content ?? ""), html:String(html ?? "")}]);
        syncChatMetadata();
      }
      return msg;
    }

    function pushTransientMessage(role, content, html=""){
      const msg = document.createElement("div");
      msg.className = `msg ${role}`;
      if (html) msg.innerHTML = html; else msg.textContent = content;
      $("chatLog").appendChild(msg);
      $("chatLog").scrollTop = $("chatLog").scrollHeight;
      return msg;
    }

    function loadingHtml(text){
      return `<div class="loading-message"><span class="spinner" aria-hidden="true"></span><span>${esc(text)}</span></div>`;
    }

    function startLoadingMessage(text){
      const node = pushTransientMessage("assistant", text, loadingHtml(text));
      return () => node.remove();
    }

    function delay(ms){
      return new Promise(resolve => window.setTimeout(resolve, ms));
    }

    function showLoadingFor(text, ms=2000){
      const stopLoading = startLoadingMessage(text);
      return new Promise(resolve => {
        window.setTimeout(() => {
          stopLoading();
          resolve();
        }, ms);
      });
    }

    function renderRecommendations(recommendations){
      const html = `<div>${esc("AI 추천을 선택하면 해석유형만 확정하고, 조건 추천은 별도로 받을 수 있습니다.")}</div><div class="rec-list">${
        asArray(recommendations).map((item,index) => `<button data-recommend-choice="${esc(item.analysis_type)}">${index+1}. ${esc(item.analysis_type)} · Confidence ${esc(item.confidence)}<br><small>${esc(item.reason || "")}</small></button>`).join("")
      }</div>`;
      pushMessage("assistant", "", html);
    }

    function renderCandidateMessage(candidateConditions){
      const items = asArray(asObj(candidateConditions).items);
      if (!items.length) return;
      const html = `<div><strong>AI 추천 ${esc(items.length)}개</strong></div><div class="rec-list">${
        items.map(item => `<div class="issue info"><span class="chip candidate">AI 異붿쿇</span> ${esc(item.field_label || item.field_key)}: ${esc(item.value)}</div>`).join("")
      }</div>`;
      pushMessage("assistant", "", html);
    }

    function renderQuickActionMessage(message, actions){
      const buttons = asArray(actions).map(action => {
        const row = asObj(action);
        const id = String(row.id || "");
        const label = String(row.label || id || "?ㅽ뻾");
        if (!id) return "";
        return `<button class="ghost" data-chat-quick-action="${esc(id)}">${esc(label)}</button>`;
      }).filter(Boolean).join("");
      if (!buttons) {
        if (message) pushMessage("assistant", message);
        return;
      }
      const html = `<div class="proposal-card quick-action-card">
        <strong class="quick-action-title">빠른 실행</strong>
        <div class="quick-action-copy">${esc(message || "필요한 작업을 선택할 수 있습니다.").replaceAll("\n","<br>")}</div>
        <div class="proposal-actions quick-actions">${buttons}</div>
      </div>`;
      pushMessage("assistant", "", html);
    }

    function proposalValueText(operation){
      const op = asObj(operation);
      if (["list_values","condition_values","append_unique","remove_list_values"].includes(op.op)) {
        return asArray(op.values).map(item => String(item ?? "").trim()).filter(Boolean).join(", ");
      }
      if (typeof op.value === "boolean") return op.value ? "예" : "아니오";
      return String(op.value ?? "").trim();
    }

    function proposalValueNote(operation){
      const op = asObj(operation);
      if (op.interpretation_note) return String(op.interpretation_note);
      const count = asArray(op.values).map(item => String(item ?? "").trim()).filter(Boolean).length;
      return count > 1 ? `${count}개 값으로 해석했습니다` : "";
    }

    function renderProposalMessage(proposal, assistantText=""){
      const row = asObj(proposal);
      pushMessage("assistant", assistantText || row.summary || "이 기능의 변경 제안은 Agent 대화에서 다시 요청해 주세요.");
    }

    async function requestConditionRecommendation(){
      pushMessage("assistant", "AI 조건 추천은 h3_v0에서 비활성화되어 있습니다.");
      return;
      const loading = showLoadingFor("AI가 현재 의뢰서에 맞는 조건 후보를 찾고 있습니다.");
      const data = await postState("/api/conditions/recommend");
      await loading;
      if (asObj(data.proposal).status === "pending") renderProposalMessage(data.proposal, data.assistant || "");
      else if (data.assistant) pushMessage("assistant", data.assistant);
    }

    async function runChatQuickAction(actionId){
      const action = String(actionId || "");
      recommendMode = false;
      if (action === "condition_recommend") {
        await requestConditionRecommendation();
        return;
      }
      const text = action === "condition_example"
        ? "조건 입력 예시 알려줘"
        : action === "missing_items"
          ? "누락된 정보가 뭐야?"
          : "";
      if (!text) return;
      $("chatInput").value = text;
      await sendChatMessage();
    }

    async function requestRecommendationFromChat(text){
      pushMessage("assistant", "해석유형 추천은 h3_v0에서 비활성화되어 있습니다. 해석유형을 직접 선택해 주세요.");
      recommendMode = false;
      return;
      const loading = showLoadingFor("AI가 알맞는 해석유형을 찾고 있습니다.");
      const data = await postJson("/api/analysis-type/recommend", {message:text, state:collectState()});
      await loading;
      renderRecommendations(data.recommendations);
      recommendMode = false;
    }

    async function selectAnalysisType(analysisType){
      if (!analysisType) return;
      const loading = showLoadingFor("해석유형을 확정하고 다음 입력 단계를 정리하고 있습니다.");
      const data = await postJson("/api/analysis-type/select", {analysis_type:analysisType, state:collectState()});
      await loading;
      adoptStateFromResponse(data);
      syncEditorFromState();
      $("section-basic")?.classList.remove("open");
      ["section-geometry","section-conditions","section-case"].forEach(id => $(id)?.classList.remove("open"));
      $("section-overview")?.classList.add("open");
      activeTopTab = "write";
      updateTopChrome();
      pushMessage("assistant", data.assistant || `${analysisType}을 선택했습니다.`);
      if (asObj(data.action_proposal).status === "pending") renderProposalMessage(data.action_proposal, "AI가 자주 쓰이는 조건을 추천해드릴까요?");
    }

    function orchestratorMessage(role, content, detail=""){
      const node = pushMessage(role, content);
      if (detail) {
        const readOnly = document.createElement("div");
        readOnly.className = "orchestrator-readonly";
        readOnly.textContent = detail;
        node.appendChild(readOnly);
      }
      return node;
    }

    function renderNextQuestion(data){
      const nextQuestion = asObj(asObj(data).next_question);
      const responseAction = String(asObj(data).action || "");
      const nextActiveFieldId = String(nextQuestion.active_field_id || "").trim();
      if (nextQuestion.kind === "field_question" && nextActiveFieldId) {
        const activeFieldChanged = nextActiveFieldId !== lastPlannerActiveFieldId;
        lastPlannerActiveFieldId = nextActiveFieldId;
        if (activeFieldChanged && responseAction !== "answer" && responseAction !== "clarify") {
          const targetScreen = screenForSection(nextActiveFieldId.split(".", 1)[0]);
          if (targetScreen !== activeScreen) navigateScreen(targetScreen, {focus:false});
        }
      }
      if (nextQuestion.message) pushMessage("assistant", String(nextQuestion.message));
    }

    function setOrchestratorLoading(loading){
      orchestratorPanelState.loading = loading;
      $("chatInput").disabled = loading;
      $("sendBtn").disabled = loading;
      $("agentClearBtn").disabled = loading;
    }

    function hasSyncedCaseMatrixRequest(){
      return !!orchestratorPanelState.requestId
        && !!orchestratorPanelState.latestApprovedState
        && orchestratorPanelState.caseMatrixSyncedRequestId === orchestratorPanelState.requestId
        && Number.isFinite(orchestratorPanelState.caseMatrixSyncedRequestVersion)
        && orchestratorPanelState.caseMatrixSyncedRequestVersion === orchestratorPanelState.requestVersion;
    }

    function invalidateCaseMatrixSync(){
      // A newer approved Request write is not eligible until H5-020 adopts its GET.
      orchestratorPanelState.caseMatrixSyncedRequestId = "";
      orchestratorPanelState.caseMatrixSyncedRequestVersion = null;
      // A Preview DOM rendered for an older server snapshot is not a Word source.
      orchestratorPanelState.previewRenderedRequestId = "";
      orchestratorPanelState.previewRenderedRequestVersion = null;
    }

    function hasPreviewDomForWord(){
      const documentNode = document.querySelector('[data-preview-document="current-state"]');
      return hasSyncedCaseMatrixRequest()
        && orchestratorPanelState.previewRenderedRequestId === orchestratorPanelState.requestId
        && orchestratorPanelState.previewRenderedRequestVersion === orchestratorPanelState.requestVersion
        && documentNode?.dataset.orchestratorPreviewRequestId === orchestratorPanelState.requestId
        && Number(documentNode?.dataset.orchestratorPreviewRequestVersion) === orchestratorPanelState.requestVersion;
    }

    async function runOrchestratorCaseMatrixAction(){
      if (orchestratorPanelState.loading || orchestratorPanelState.caseMatrixActionLoading) return;
      const action = $("orchestratorCaseMatrixAction");
      orchestratorPanelState.caseMatrixActionLoading = true;
      action.disabled = true;
      try {
        await createOrchestratorConversation();
        if (!hasSyncedCaseMatrixRequest()) throw new Error("request_not_synced");
        const response = await fetch("/api/orchestrator/case-matrix/action", {
          method:"POST", headers:{"Content-Type":"application/json"},
          body:JSON.stringify({request_id:orchestratorPanelState.requestId}),
        });
        const data = await response.json();
        if (data.kind === "case_matrix_blocked") {
          orchestratorMessage("assistant", "Case Matrix 준비 차단", asArray(data.blocking_reasons).join("\n") || "기존 Validator 준비 조건이 충족되지 않았습니다.");
        } else if (!(response.ok && data.kind === "case_matrix_ready" && data.request_id === orchestratorPanelState.requestId)) {
          orchestratorMessage("assistant", "Case Matrix 확인 불가", "서버 최신 의뢰서를 변경하지 않았습니다.");
        }
      } catch (_err) {
        orchestratorMessage("assistant", "Case Matrix 확인 오류", "폼과 기존 Matrix는 변경되지 않았습니다.");
      } finally {
        orchestratorPanelState.caseMatrixActionLoading = false;
        action.disabled = false;
      }
    }

    async function runOrchestratorValidationAction(){
      if (orchestratorPanelState.loading || orchestratorPanelState.validationActionLoading) return;
      const action = $("orchestratorValidationAction");
      orchestratorPanelState.validationActionLoading = true;
      action.disabled = true;
      try {
        await createOrchestratorConversation();
        if (!hasSyncedCaseMatrixRequest()) throw new Error("request_not_synced");
        const response = await fetch("/api/orchestrator/validation/action", {
          method:"POST", headers:{"Content-Type":"application/json"},
          body:JSON.stringify({request_id:orchestratorPanelState.requestId}),
        });
        const data = await response.json();
        if (response.ok && ["validation_ready", "validation_blocked"].includes(data.kind) && data.request_id === orchestratorPanelState.requestId) {
          const validation = asObj(data.validation);
          const issues = [...asArray(validation.blocking), ...asArray(validation.warning)];
          const lines = issues.map(issue => {
            const row = asObj(issue);
            return String(row.message || row.label || row.code || "확인이 필요한 입력 항목이 있습니다.");
          });
          orchestratorMessage("assistant", "오류·누락 확인 결과", lines.length ? lines.join("\n") : "오류 또는 누락 항목이 없습니다.");
        } else {
          orchestratorMessage("assistant", "Validation 확인 불가", "서버 최신 의뢰서를 변경하지 않았습니다.");
        }
      } catch (_err) {
        orchestratorMessage("assistant", "Validation 확인 오류", "기존 의뢰서와 검증 화면은 변경되지 않았습니다.");
      } finally {
        orchestratorPanelState.validationActionLoading = false;
        action.disabled = false;
      }
    }

    async function runOrchestratorPreviewAction(){
      if (orchestratorPanelState.loading || orchestratorPanelState.previewActionLoading) return;
      const action = $("orchestratorPreviewAction");
      orchestratorPanelState.previewActionLoading = true;
      action.disabled = true;
      try {
        await createOrchestratorConversation();
        if (!hasSyncedCaseMatrixRequest()) throw new Error("request_not_synced");
        const response = await fetch("/api/orchestrator/preview/action", {
          method:"POST", headers:{"Content-Type":"application/json"},
          body:JSON.stringify({request_id:orchestratorPanelState.requestId}),
        });
        const data = await response.json();
        if (response.ok && data.kind === "preview_ready"
          && data.request_id === orchestratorPanelState.requestId
          && data.request_version === orchestratorPanelState.requestVersion
          && hasApprovedLatestStateShape(data)) {
          // The one existing Preview entry receives only this fenced server
          // snapshot.  It does not adopt, normalize, validate, or persist it.
          renderDocumentPreviewPanel(data.state, {requestId:data.request_id, requestVersion:data.request_version});
          orchestratorPanelState.previewRenderedRequestId = data.request_id;
          orchestratorPanelState.previewRenderedRequestVersion = data.request_version;
        } else {
          orchestratorMessage("assistant", "Preview 확인 불가", "서버 최신 의뢰서와 기존 Preview는 변경하지 않았습니다.");
        }
      } catch (_err) {
        orchestratorMessage("assistant", "Preview 확인 오류", "서버 최신 의뢰서와 기존 Preview는 변경하지 않았습니다.");
      } finally {
        orchestratorPanelState.previewActionLoading = false;
        action.disabled = false;
      }
    }

    async function runOrchestratorWordExportAction(){
      if (orchestratorPanelState.loading || orchestratorPanelState.wordExportActionLoading) return;
      if (orchestratorPanelState.dirty) {
        orchestratorMessage("assistant", "Word 출력 불가", "최신 입력으로 의뢰서 미리보기를 먼저 확인해 주세요.");
        return;
      }
      if (!hasPreviewDomForWord()) {
        orchestratorMessage("assistant", "Word 출력 불가", "같은 최신 의뢰서의 Preview 확인이 먼저 필요합니다.");
        return;
      }
      const action = $("orchestratorWordExportAction");
      orchestratorPanelState.wordExportActionLoading = true;
      action.disabled = true;
      try {
        // H5-028 may only serialize the DOM produced by the fenced H5-027
        // Preview action; it must not collect or render client state.
        await exportWordFromPreview({useExistingPreviewDom:true});
      } catch (_err) {
        orchestratorMessage("assistant", "Word 출력 불가", "기존 Preview와 서버 의뢰서는 변경하지 않았습니다.");
      } finally {
        orchestratorPanelState.wordExportActionLoading = false;
        action.disabled = false;
      }
    }

    async function runOrchestratorRagGuidanceAction(){
      if (orchestratorPanelState.loading || orchestratorPanelState.ragGuidanceActionLoading) return;
      const question = $("chatInput").value.trim();
      if (!question) {
        orchestratorMessage("assistant", "RAG 근거 확인 불가", "Agent 입력창에 문서 검색 질문을 입력해 주세요.");
        return;
      }
      const action = $("orchestratorRagGuidanceAction");
      orchestratorPanelState.ragGuidanceActionLoading = true;
      action.disabled = true;
      try {
        await createOrchestratorConversation();
        const response = await fetch("/api/orchestrator/rag-guidance/action", {
          method:"POST", headers:{"Content-Type":"application/json"},
          body:JSON.stringify({request_id:orchestratorPanelState.requestId, question}),
        });
        const data = await response.json();
        const qa = asObj(data.qa);
        if (data.request_id !== orchestratorPanelState.requestId || !["rag_guidance_ready", "rag_guidance_no_result", "rag_guidance_disabled", "rag_guidance_error"].includes(data.kind)) {
          orchestratorMessage("assistant", "RAG 근거 안내 불가", "서버 문서 검색 결과를 표시하지 않았습니다. 폼과 기존 UI는 변경되지 않았습니다.");
          return;
        }
        const title = data.kind === "rag_guidance_ready" ? "RAG 근거 확인" : data.kind === "rag_guidance_no_result" ? "RAG 검색 결과 없음" : data.kind === "rag_guidance_disabled" ? "RAG Off" : "RAG 검색 오류";
        orchestratorMessage("assistant", title, String(qa.answer_text || ""));
        const sources = asArray(qa.sources).map(source => String(asObj(source).source_name || asObj(source).title || "근거 문서")).filter(Boolean);
        const limitations = asArray(qa.limitations).map(String).filter(Boolean);
        orchestratorMessage("assistant", "근거 요약", `${sources.length ? sources.join("\n") : "표시할 근거 문서가 없습니다."}${limitations.length ? `\n제한사항: ${limitations.join(" · ")}` : ""}`);
      } catch (_err) {
        orchestratorMessage("assistant", "RAG 근거 안내 오류", "폼, Request, Fieldset, Matrix, Proposal, Preview, Word 및 기존 채팅은 변경되지 않았습니다.");
      } finally {
        orchestratorPanelState.ragGuidanceActionLoading = false;
        action.disabled = false;
      }
    }

    async function createOrchestratorConversation(){
      const draft = collectState();
      const hasRequest = !!orchestratorPanelState.requestId;
      let requestBody = {request_id:orchestratorPanelState.requestId, request_version:orchestratorPanelState.requestVersion, state:orchestratorPanelState.latestApprovedState};
      if (!hasRequest || orchestratorPanelState.dirty) {
        const requestResponse = await fetch(hasRequest
          ? `/api/request/versioned/${encodeURIComponent(orchestratorPanelState.requestId)}`
          : "/api/request/versioned", {
          method:hasRequest ? "PUT" : "POST", headers:{"Content-Type":"application/json"},
          body:JSON.stringify(hasRequest
            ? {expected_version:orchestratorPanelState.requestVersion, state:draft}
            : {state:draft}),
        });
        requestBody = await requestResponse.json();
        if (!requestResponse.ok || !requestBody.request_id) throw new Error(requestBody.error || "request_sync_failed");
        if (hasRequest && requestBody.request_id !== orchestratorPanelState.requestId) throw new Error("request_identity_mismatch");
        orchestratorPanelState.requestId = requestBody.request_id;
        orchestratorPanelState.requestVersion = requestBody.request_version;
        orchestratorPanelState.latestApprovedState = snapshotApprovedLatestState(requestBody.state);
        orchestratorPanelState.caseMatrixSyncedRequestId = requestBody.request_id;
        orchestratorPanelState.caseMatrixSyncedRequestVersion = requestBody.request_version;
        orchestratorPanelState.previewRenderedRequestId = "";
        orchestratorPanelState.previewRenderedRequestVersion = null;
        orchestratorPanelState.dirty = false;
      }
      if (orchestratorPanelState.conversationId) return orchestratorPanelState.conversationId;
      const conversationResponse = await fetch("/api/conversations", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({request_id:requestBody.request_id}),
      });
      const conversationBody = await conversationResponse.json();
      if (!conversationResponse.ok || !conversationBody.conversation_id) throw new Error(conversationBody.error || "conversation_bootstrap_failed");
      orchestratorPanelState.conversationId = conversationBody.conversation_id;
      return orchestratorPanelState.conversationId;
    }

    function orchestratorResponseDetail(data){
      const reasons = asArray(data.reasons).map(String).filter(Boolean);
      const parts = [];
      if (data.route_category) parts.push(`경로: ${data.route_category}`);
      if (reasons.length) parts.push(`사유: ${reasons.join(" · ")}`);
      const planner = asObj(data.planner_decision);
      if (Object.keys(planner).length) parts.push(`다음 입력 안내: ${planner.kind || "read-only"}`);
      return parts.join("\n");
    }

    function proposalStatusText(status){
      const labels = {pending:"대기", approved:"승인됨", rejected:"거절됨", conflicted:"충돌", failed:"실패", expired:"만료", unknown:"알 수 없음", error:"오류"};
      return labels[String(status || "unknown")] || String(status || "unknown");
    }

    function setOrchestratorProposalControls(card, disabled){
      asArray(card?.children).forEach(node => {
        if (node?.dataset?.orchestratorProposalControl) node.disabled = disabled;
        asArray(node?.children).forEach(child => { if (child?.dataset?.orchestratorProposalControl) child.disabled = disabled; });
      });
    }

    // H5-ORCH-021 deliberately consumes the server-produced Fieldset snapshot.
    // It only reads its active/required flags; it does not reproduce Fieldset,
    // Registry, validation, or condition-normalization rules in the client.
    function approvedConditionFieldset(state){
      const source = asObj(state);
      const groups = asArray(asObj(source.request_context).condition_fieldset_snapshot);
      const cards = asArray(asObj(source.conditions).condition_sets);
      const fields = new Map();
      const valuesFor = (groupKey, fieldKey) => cards.filter(card => String(asObj(card).type || "") === groupKey).flatMap(card => {
        const row = asObj(card);
        if (groupKey === "operating") {
          return asArray(row.fans).filter(fan => asObj(fan).running !== false).map(fan => asObj(asObj(fan).values)[fieldKey]);
        }
        const field = asObj(asObj(row.fields)[fieldKey]);
        return [field.value ?? asObj(row.fields)[fieldKey]];
      }).map(value => String(value ?? "").trim()).filter(Boolean);
      groups.forEach(group => {
        const groupRow = asObj(group);
        const groupKey = String(groupRow.key || "").trim();
        if (!groupKey) return;
        asArray(groupRow.fields).forEach(field => {
          const fieldRow = asObj(field);
          const fieldKey = String(fieldRow.key || "").trim();
          if (!fieldKey) return;
          const id = `${groupKey}.${fieldKey}`;
          fields.set(id, {
            id,
            label:String(fieldRow.label || fieldKey),
            active:groupRow.active === true && fieldRow.active !== false,
            required:fieldRow.required === true,
            values:valuesFor(groupKey, fieldKey),
          });
        });
      });
      return fields;
    }

    function renderApprovedConditionalImpact(beforeState, latestState){
      if (!beforeState) return;
      const before = approvedConditionFieldset(beforeState);
      const after = approvedConditionFieldset(latestState);
      const ids = new Set([...before.keys(), ...after.keys()]);
      const lines = [];
      ids.forEach(id => {
        const previous = before.get(id) || {active:false, required:false, values:[]};
        const current = after.get(id) || {active:false, required:false, values:[], label:id};
        const label = current.label || previous.label || id;
        if (!previous.active && current.active) lines.push(`활성화: ${label}`);
        if (current.active && current.required && (!previous.active || !previous.required)) lines.push(`새 필수 입력: ${label}`);
        if (previous.active && !current.active) {
          lines.push(`비활성화: ${label}`);
          if (previous.values.length) lines.push(`값 보존 안내: ${label} — 기존 값 ${previous.values.join(", ")}은 자동으로 삭제하거나 정리하지 않습니다.`);
        }
      });
      if (lines.length) orchestratorMessage("assistant", "조건부 필드 영향 안내", lines.join("\n"));
    }

    function snapshotApprovedLatestState(state){
      // Keep an immutable server-read baseline so later client draft edits cannot
      // become impact authority.
      return JSON.parse(JSON.stringify(state));
    }

    function hasApprovedLatestStateShape(latest){
      const response = asObj(latest);
      const state = response.state;
      const requiredSections = ["metadata", "request_context", "basic_info", "analysis_overview", "geometry", "conditions", "case_matrix", "review", "legacy_internal"];
      return response.request_id === orchestratorPanelState.requestId
        && Number.isFinite(response.request_version)
        && state && typeof state === "object" && !Array.isArray(state)
        && requiredSections.every(section => state[section] && typeof state[section] === "object" && !Array.isArray(state[section]));
    }

    async function refreshApprovedOrchestratorRequest(proposalId){
      if (!proposalId || !orchestratorPanelState.requestId || orchestratorPanelState.refreshedProposalIds.has(proposalId)) return false;
      // Consume this server-approved Proposal before the read: a replay or retry must not refresh twice.
      invalidateCaseMatrixSync();
      orchestratorPanelState.refreshedProposalIds.add(proposalId);
      const response = await fetch(`/api/request/versioned/${encodeURIComponent(orchestratorPanelState.requestId)}`);
      const latest = await response.json();
      if (!response.ok || !hasApprovedLatestStateShape(latest)) {
        throw new Error(asObj(latest).error || "request_refresh_failed");
      }
      const previousApprovedState = orchestratorPanelState.latestApprovedState;
      // Only the canonical latest-read is allowed to replace the legacy form state.
      requestState = latest.state;
      orchestratorPanelState.requestVersion = latest.request_version;
      syncEditorFromState();
      renderDerivedPanels();
      renderApprovedConditionalImpact(previousApprovedState, latest.state);
      orchestratorPanelState.latestApprovedState = snapshotApprovedLatestState(latest.state);
      orchestratorPanelState.dirty = false;
      // The Action gate is a display-only receipt of this exact H5-020 latest GET.
      orchestratorPanelState.caseMatrixSyncedRequestId = latest.request_id;
      orchestratorPanelState.caseMatrixSyncedRequestVersion = latest.request_version;
      return true;
    }

    async function decideOrchestratorProposal(proposalId, decision, card, statusNode){
      if (!proposalId || !["approve", "reject"].includes(decision) || orchestratorPanelState.decisionIds.has(proposalId)) return;
      orchestratorPanelState.decisionIds.add(proposalId);
      setOrchestratorProposalControls(card, true);
      statusNode.textContent = "상태: 처리 중";
      try {
        await createOrchestratorConversation();
        const response = await fetch("/api/orchestrator/proposals/decision", {
          method:"POST", headers:{"Content-Type":"application/json"},
          body:JSON.stringify({proposal_id:proposalId, decision}),
        });
        const data = await response.json();
        const status = String(data.status || (data.error === "proposal_not_found" ? "unknown" : "error"));
        statusNode.textContent = `상태: ${proposalStatusText(status)}`;
        if (response.ok && data.ok === true && data.proposal_id === proposalId && status === "approved") {
          try {
            await refreshApprovedOrchestratorRequest(proposalId);
          } catch (_err) {
            statusNode.textContent = "상태: 승인됨 · 최신 의뢰서 동기화 오류";
            orchestratorMessage("assistant", "변경은 승인되었지만 최신 의뢰서를 화면에 동기화하지 못했습니다.");
          }
          renderNextQuestion(data);
        } else if (response.ok && data.ok === true && data.proposal_id === proposalId && status === "rejected") {
          renderNextQuestion(data);
        }
      } catch (_err) {
        statusNode.textContent = "상태: 오류";
      } finally {
        // Terminal/read-only only: H5-020 owns any later refresh or synchronization.
        orchestratorPanelState.decisionIds.delete(proposalId);
      }
    }

    function renderOrchestratorProposal(proposal, detail){
      const proposalId = String(proposal.proposal_id || "");
      const node = orchestratorMessage("assistant", detail || "다음 변경 내용을 의뢰서에 반영할까요?");
      const card = document.createElement("div");
      card.className = "proposal-card orchestrator-proposal";
      const title = document.createElement("strong");
      title.textContent = "변경 제안";
      card.appendChild(title);
      const changes = asArray(proposal.changes).map(asObj);
      if (changes.length) {
        const diffList = document.createElement("ul");
        diffList.className = "proposal-list";
        changes.forEach(change => {
          const item = document.createElement("li");
          item.textContent = `${change.label || "변경 항목"}: ${change.current_value || "입력 없음"} → ${change.new_value || "입력 없음"}`;
          diffList.appendChild(item);
        });
        card.appendChild(diffList);
      }
      if (proposal.status === "pending") {
        const actions = document.createElement("div");
        actions.className = "proposal-actions";
        const status = document.createElement("span");
        status.textContent = "상태: 대기";
        for (const [decision, label] of [["approve", "반영"], ["reject", "반영하지 않음"]]) {
          const button = document.createElement("button");
          button.type = "button";
          button.textContent = label;
          button.dataset.orchestratorProposalControl = proposalId;
          button.addEventListener("click", () => decideOrchestratorProposal(proposalId, decision, card, status));
          actions.appendChild(button);
        }
        actions.appendChild(status);
        card.appendChild(actions);
      }
      node.appendChild(card);
    }

    function renderOrchestratorResponse(data){
      const proposal = asObj(data.proposal);
      if (proposal.proposal_id) {
        renderOrchestratorProposal(proposal, String(data.assistant || ""));
        return;
      }
      const kind = String(data.kind || "read_only");
      const message = kind === "clarification"
        ? String(data.question || "변경할 항목과 값을 구체적으로 다시 알려주세요.")
        : kind === "next_field"
        ? "다음 입력 항목 안내를 받았습니다."
        : "요청 내용을 확인했습니다.";
      orchestratorMessage("assistant", message);
    }

    async function sendChatMessage(){
      const text = $("chatInput").value.trim();
      if (!text || orchestratorPanelState.loading) return;
      $("chatInput").value = "";
      pushMessage("user", text);
      let stopLoading = null;
      let minLoading = Promise.resolve();
      try{
        setOrchestratorLoading(true);
        if (recommendMode) {
          await requestRecommendationFromChat(text);
          return;
        }
        stopLoading = startLoadingMessage("답변 생성 중입니다.");
        minLoading = delay(1000);
        const conversationId = await createOrchestratorConversation();
        const data = await postJson("/api/chat/send", {message:text, conversation_id:conversationId, mode:"auto"});
        await minLoading;
        stopLoading();
        stopLoading = null;
        adoptStateFromResponse(data);
        if (asObj(data).state) {
          syncEditorFromState();
          renderDerivedPanels();
        }
        if (asObj(data.proposal).status === "pending") {
          renderOrchestratorProposal(data.proposal, String(data.assistant || ""));
        } else {
          pushMessage("assistant", data.assistant || "답변을 생성했습니다.");
        }
        renderNextQuestion(data);
      }catch(err){
        await minLoading;
        if (typeof stopLoading === "function") stopLoading();
        const errorMessage = String(err?.message || "");
        pushMessage("assistant", errorMessage === "LLM이 정상 작동하지 않습니다."
          ? errorMessage
          : "처리 중 통신 오류가 발생했습니다. 입력 내용을 복원했습니다.");
        $("chatInput").value = text;
      } finally {
        setOrchestratorLoading(false);
      }
    }

    function triggerDownload(download){
      const info = asObj(download);
      if (!info.auto_download || !info.download_url) return;
      const link = document.createElement("a");
      link.href = info.download_url;
      link.download = info.filename || "";
      link.style.display = "none";
      document.body.appendChild(link);
      link.click();
      window.setTimeout(() => link.remove(), 1000);
    }

    function previewDomForWord(){
      const documentNode = document.querySelector('[data-preview-document="current-state"]');
      const clean = value => String(value || "").trim();
      if (!documentNode) return {sections:[]};
      return {sections:Array.from(documentNode.querySelectorAll('[data-preview-section]')).map(section => {
        const blocks = Array.from(section.querySelectorAll('[data-preview-label], table[data-preview-table]'))
          .map(node => {
            if (node.matches('[data-preview-label]')) {
              const row = node.closest('.preview-kv');
              return {type:"field", label:clean(node.textContent), value:clean(row?.querySelector('[data-preview-value]')?.textContent)};
            }
            const rows = Array.from(node.querySelectorAll('tbody tr')).map(row => Array.from(row.querySelectorAll('td')).map(cell => clean(cell.textContent)));
            return {type:"table", caption:clean(node.querySelector('caption')?.textContent), headers:Array.from(node.querySelectorAll('thead th')).map(cell => clean(cell.textContent)), rows};
          });
        return {title:clean(section.querySelector('[data-preview-section-title]')?.textContent), blocks};
      })};
    }

    async function exportWordFromPreview({useExistingPreviewDom=false}={}){
      if (!useExistingPreviewDom) {
        const reviewScreen = screenOrder.find(screen => screen.id === "SCREEN-06");
        const firstIncomplete = firstIncompleteScreenBefore(reviewScreen);
        if (firstIncomplete) {
          focusRequiredControl(firstIncomplete.screen, firstIncomplete.control);
          setScreenNavigationStatus(`${firstIncomplete.screen.id}의 필수 입력을 완료한 뒤 의뢰서를 생성할 수 있습니다.`);
          return false;
        }
        requestState = collectState();
        renderDocumentPreviewPanel();
      }
      const response = await fetch('/api/export/word', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(previewDomForWord())});
      if (!response.ok) throw new Error('Word export failed');
      const file = await response.blob();
      const link = document.createElement('a');
      link.href = URL.createObjectURL(file);
      link.download = 'analysis_request.docx';
      link.style.display = 'none';
      document.body.appendChild(link);
      link.click();
      window.setTimeout(() => { URL.revokeObjectURL(link.href); link.remove(); }, 1000);
      return true;
    }

    function mutateRows(listName, action, index){
      if (listName !== "comparison_products") return;
      const products = collectProductCards();
      const baseProduct = products.find(product => product.role === "base") || asObj(requestState.geometry).base_product;
      const state = {...requestState, geometry:{...asObj(requestState.geometry), base_product:baseProduct, comparison_products:products.filter(product => product.role === "comparison")}};
      const values = [...asArray(state.geometry.comparison_products)];
      let focusSelector = "";
      if (action === "add") {
        values.push({geometry_id:`comparison_${Date.now()}_${values.length + 1}`, role:"comparison", drawing_no:"", display_name:"", difference_from_base:""});
        const added = values[values.length - 1];
        $("productRows").insertAdjacentHTML("beforeend", productRow(added, values.length - 1, true));
        focusSelector = `#productRows [data-product-role="comparison"][data-product-index="${values.length - 1}"] [data-product-field="drawing_no"]`;
      }
      if (action === "remove") {
        values.splice(index, 1);
        document.querySelector(`#productRows [data-product-role="comparison"][data-product-index="${index}"]`)?.remove();
        reindexProductRows();
        focusSelector = values.length
          ? `#productRows [data-product-role="comparison"][data-product-index="${Math.min(index, values.length - 1)}"] [data-product-field="drawing_no"]`
          : '[data-action="add-comparison"]';
      }
      requestState = {...state, geometry:{...asObj(state.geometry), comparison_products:values}};
      if (focusSelector) window.requestAnimationFrame(() => document.querySelector(focusSelector)?.focus());
      schedulePreviewRefresh();
    }
    function mutateConditionValues(fieldKey, action, index){
      const state = collectState();
      const field = asArray(state.conditions.fields).find(item => item.key === fieldKey);
      if (!field) return;
      if (!Array.isArray(field.values)) field.values = [{value:""}];
      if (action === "add") field.values.push({value:"", status:"missing", source:"user"});
      if (action === "remove" && field.values.length > 1) field.values.splice(index,1);
      requestState = state;
      renderConditionFields();
      schedulePreviewRefresh();
    }

    function mutateCaseRows(action, caseId=""){
      const state = collectState();
      const matrix = asObj(state.case_matrix);
      const rows = asArray(matrix.rows);
      if (action === "add") {
        rows.push({case_id:`case_${Date.now()}`, geometry_id:"", auto_geometry_id:"", condition_values:{}});
      } else if (action === "remove") {
        if (rows.length <= 1) {
          notify("최소 1개 Case는 유지해야 합니다.");
          return;
        }
        const nextRows = rows.filter(row => contextText(asObj(row).case_id) !== caseId);
        requestState = {...state, case_matrix:{...matrix, rows:nextRows}};
        renderCasePreview();
        schedulePreviewRefresh();
        return;
      }
      requestState = {...state, case_matrix:{...matrix, rows}};
      renderCasePreview();
      schedulePreviewRefresh();
    }

    function jumpToIssue(section, fieldKey){
      const sectionId = {
        basic_info: "section-basic",
        analysis_overview: "section-overview",
        geometry: "section-geometry",
        conditions: "section-conditions",
        case_matrix: "section-case",
      }[section] || "section-basic";
      navigateScreen(screenForSection(section), {focus:false});
      const sectionEl = $(sectionId);
      if (sectionEl) sectionEl.classList.add("open");
      let target = null;
      if (section === "basic_info" || section === "analysis_overview") {
        target = pathInput(section, fieldKey);
      } else if (section === "geometry") {
        const indexMatch = String(fieldKey || "").match(/comparison_products\[(\d+)\]/);
        const productIndex = indexMatch ? Number.parseInt(indexMatch[1], 10) : 0;
        const productRole = indexMatch ? "comparison" : "base";
        const productField = String(fieldKey || "").includes("difference_from_base") ? "description" : "drawing_no";
        target = document.querySelector(`[data-product-role="${productRole}"][data-product-index="${productIndex}"] [data-product-field="${productField}"]`);
      } else if (section === "conditions") {
        target = document.querySelector(`input[data-condition-key="${CSS.escape(fieldKey || "")}"], input[data-condition-checkbox="${CSS.escape(fieldKey || "")}"]`);
      }
      (target || sectionEl)?.scrollIntoView({behavior:"smooth", block:"center"});
      if (target) {
        target.classList.add("field-highlight");
        target.focus?.();
        window.setTimeout(() => target.classList.remove("field-highlight"), 1800);
      }
    }

    function wireUndecidedComboboxes(root=document){
      root.querySelectorAll("[data-undecided-combobox]").forEach(combobox => {
        if (combobox.dataset.undecidedWired === "true") return;
        combobox.dataset.undecidedWired = "true";
        const input = combobox.querySelector("[data-undecided-input]");
        const toggle = combobox.querySelector("[data-undecided-toggle]");
        const menu = combobox.querySelector("[data-undecided-menu]");
        toggle?.addEventListener("click", () => {
          setUndecidedComboboxOpen(combobox, Boolean(menu?.hidden), {focusOption:Boolean(menu?.hidden)});
        });
        menu?.addEventListener("click", event => {
          const option = event.target.closest("[data-undecided-mode]");
          if (option) selectUndecidedComboboxMode(combobox, option.dataset.undecidedMode || "custom");
        });
        menu?.querySelectorAll("[data-undecided-mode]").forEach(option => {
          option.addEventListener("mouseenter", () => setUndecidedActiveOption(combobox, option, {focus:true}));
          option.addEventListener("focus", () => setUndecidedActiveOption(combobox, option));
        });
        input?.addEventListener("keydown", event => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setUndecidedComboboxOpen(combobox, true, {focusOption:true});
          } else if (event.key === "Escape") {
            setUndecidedComboboxOpen(combobox, false);
          }
        });
        menu?.addEventListener("keydown", event => {
          const options = Array.from(combobox.querySelectorAll("[data-undecided-mode]"));
          const index = options.indexOf(document.activeElement);
          if (event.key === "Escape") {
            event.preventDefault();
            setUndecidedComboboxOpen(combobox, false);
            toggle?.focus();
          } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            const direction = event.key === "ArrowDown" ? 1 : -1;
            setUndecidedActiveOption(combobox, options[(index + direction + options.length) % options.length], {focus:true});
          }
        });
      });
    }

    function wireEvents(){
      initPanelResizer();
      configureDesiredCompletionDateMinimum();
      pathInput("analysis_overview", "desired_completion_date")?.addEventListener("focus", configureDesiredCompletionDateMinimum);
      wireUndecidedComboboxes();
      document.addEventListener("click", event => {
        document.querySelectorAll("[data-undecided-combobox]").forEach(combobox => {
          if (!combobox.contains(event.target)) setUndecidedComboboxOpen(combobox, false);
        });
      });
      document.addEventListener("focusin", event => {
        document.querySelectorAll("[data-undecided-combobox]").forEach(combobox => {
          if (!combobox.contains(event.target)) setUndecidedComboboxOpen(combobox, false);
        });
      });
      $("ragToggle").addEventListener("change", () => { requestState = collectState(); renderDerivedPanels(); });
      $("newRequestBtn").addEventListener("click", () => {
        startNewRequest().catch(err => pushMessage("assistant", `새 의뢰 시작 실패: ${err.message}`));
      });
      $("agentClearBtn").addEventListener("click", clearAgentConversation);
      $("agentHideBtn").addEventListener("click", () => setAgentOpen(false));
      $("agentOpenBtn").addEventListener("click", () => setAgentOpen(true));
      $("wordExportSlotBtn").addEventListener("click", () => {
        exportWordFromPreview().catch(err => console.error(err));
      });
      $("recommendBtn").addEventListener("click", () => {
        recommendMode = true;
        pushMessage("assistant", "제품군과 검토하고 싶은 내용을 입력해 주세요. 예: RAC 제품군에서 압력 손실을 보고 싶습니다.");
        $("chatInput").focus();
      });
      $("sendBtn").addEventListener("click", sendChatMessage);
      $("chatInput").addEventListener("keydown", event => {
        if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
          event.preventDefault();
          sendChatMessage();
        }
      });
      $("contextChangeBtn").addEventListener("click", showContextChangeWarning);
      $("contextChangeContinue").addEventListener("click", continueContextChange);
      $("contextChangeCancel").addEventListener("click", hideContextChangeWarning);
      document.addEventListener("focusin", event => {
        if (agentOpen && $("agentDock")?.contains(event.target)) lastAgentFocus = event.target;
      });
      document.body.addEventListener("keydown", event => {
        if (event.key === "Escape" && agentOpen && isAgentOverlay()) {
          event.preventDefault();
          setAgentOpen(false);
          return;
        }
        const screen = event.target.closest(".screen-map-item[data-screen]");
        if (!screen || (event.key !== "Enter" && event.key !== " ")) return;
        event.preventDefault();
        if (screen.getAttribute("aria-disabled") !== "true") navigateScreen(screen.dataset.screen || "SCREEN-01");
      });
      document.body.addEventListener("click", event => {
        const retryGuidance = event.target.closest("#retryAnalysisResultGuidance");
        if (retryGuidance) { refreshAnalysisResultGuidance(); return; }
        const stageAssist = event.target.closest("button[data-stage-assist-prompt]");
        if (stageAssist) { fillStageAssistPrompt(stageAssist.dataset.stageAssistPrompt || stageAssist.textContent || ""); return; }
        const prepStart = event.target.closest("#prepStartBtn");
        if (prepStart) {
          confirmRequestContext().catch(err => pushMessage("assistant", `조합 확정 실패: ${err.message}`));
          return;
        }
        const prepMode = event.target.closest("button[data-prep-mode]");
        if (prepMode) {
          activePrepMode = prepMode.dataset.prepMode || "quick";
          prepAssistStarted = true;
          renderRequestPrepCard();
          return;
        }
        const prepChoice = event.target.closest("button[data-context-choice]");
        if (prepChoice) {
          if (prepChoice.dataset.contextChoice === "product_group" && prepChoice.dataset.contextValue === "직접 입력") {
            quickProductGroupCustomMode = true;
            activePrepMode = "quick";
            updateRequestContextDraft("product_group", "");
            window.requestAnimationFrame(() => $("quickProductGroupCustomInput")?.focus());
            return;
          }
          if (prepChoice.dataset.contextChoice === "platform" && prepChoice.dataset.contextValue === "직접 입력") {
            quickPlatformCustomMode = true;
            activePrepMode = "quick";
            updateRequestContextDraft("platform", "");
            window.requestAnimationFrame(() => $("quickPlatformCustomInput")?.focus());
            return;
          }
          if (prepChoice.dataset.contextChoice === "product_group") quickProductGroupCustomMode = false;
          if (prepChoice.dataset.contextChoice === "platform") quickPlatformCustomMode = false;
          updateRequestContextDraft(prepChoice.dataset.contextChoice || "", prepChoice.dataset.contextValue || "");
          return;
        }
        if (event.target.closest("#quickProductGroupRestoreBtn")) {
          quickProductGroupCustomMode = false;
          updateRequestContextDraft("product_group", "");
          return;
        }
        if (event.target.closest("#quickPlatformRestoreBtn")) {
          quickPlatformCustomMode = false;
          updateRequestContextDraft("platform", "");
          return;
        }
        const dropdownRestore = event.target.closest("button[data-dropdown-restore-path]");
        if (dropdownRestore) { restoreDropdownControl(dropdownRestore); return; }
        const proposalRefresh = event.target.closest("button[data-chat-proposal-refresh]");
        if (proposalRefresh) { fillStageAssistPrompt(proposalRefresh.dataset.chatProposalRefresh || ""); return; }
        const quickAction = event.target.closest("button[data-chat-quick-action]");
        if (quickAction) { runChatQuickAction(quickAction.dataset.chatQuickAction || "").catch(err => pushMessage("assistant", `빠른 실행 실패: ${err.message}`)); return; }
        const rec = event.target.closest("button[data-recommend-choice]");
        if (rec) { selectAnalysisType(rec.dataset.recommendChoice).catch(err => pushMessage("assistant", `추천 선택 실패: ${err.message}`)); return; }
        const screenAction = event.target.closest("button[data-screen-action]");
        if (screenAction) { navigateScreen(screenAction.dataset.screenAction || "SCREEN-01"); return; }
        const screen = event.target.closest(".screen-map-item[data-screen]");
        if (screen && screen.getAttribute("aria-disabled") !== "true") { navigateScreen(screen.dataset.screen || "SCREEN-01"); return; }
        const issue = event.target.closest("button[data-issue-jump]");
        if (issue) { jumpToIssue(issue.dataset.section || "", issue.dataset.field || ""); return; }
        const toggle = event.target.closest("[data-toggle-section]");
        if (toggle) { $(toggle.dataset.toggleSection)?.classList.toggle("open"); return; }
        const heatExchangerRestore = event.target.closest("button[data-heat-exchanger-restore]");
        if (heatExchangerRestore) { restoreHeatExchangerDropdown(heatExchangerRestore); return; }
        const fanCountRestore = event.target.closest("button[data-fan-count-restore]");
        if (fanCountRestore) { restoreFanCountDropdown(fanCountRestore); return; }
        const button = event.target.closest("button[data-action]");
        if (!button) return;
        const action = button.dataset.action;
        if (action === "confirm-case-configuration") { confirmCaseConfiguration().catch(err => console.error(err)); return; }
        if (action === "add-case") { mutateCaseRows("add"); return; }
        if (action === "remove-case") { mutateCaseRows("remove", button.dataset.caseId || ""); return; }
        if (action === "condition-recommend-request") { requestConditionRecommendation().catch(err => pushMessage("assistant", `조건 추천 실패: ${err.message}`)); return; }
        if (action === "add-comparison") mutateRows("comparison_products", "add", 0);
        if (action === "remove-comparison") mutateRows("comparison_products", "remove", Number.parseInt(button.dataset.index || "0",10));
        if (action === "add-condition-card") {
          preserveEditorDraftBeforeRerender();
          const type = button.dataset.cardType;
          const cards = collectConditionSets();
          const base = cards.find(card => contextText(asObj(card).type) === type);
          if (!base) return;
          const card = JSON.parse(JSON.stringify(base));
          const number = cards.filter(item => contextText(asObj(item).type) === type).length + 1;
          card.id = `${type}_${number}`; card.is_default = false;
          Object.keys(asObj(card.fields)).forEach(key => { card.fields[key] = ""; });
          if (type === "operating") {
            card.name = `운전 ${number}`;
            card.fans = [{id:"fan_1", name:"", location:"", running:true, values:{fan_rpm:""}}];
          }
          if (type === "heat_exchanger") card.fields.name = `사양 ${number}`;
          if (type === "heat_exchanger" && heatExchangerType([card]) === "Micro-Channel") card.fields.fin_type = "Flat";
          requestState.conditions = {...asObj(requestState.conditions), condition_sets:[...cards, card]}; syncEditorFromState();
          window.requestAnimationFrame(() => document.querySelector(`[data-condition-card="${CSS.escape(card.id)}"] input:not([disabled]), [data-condition-card="${CSS.escape(card.id)}"] select:not([disabled])`)?.focus());
          schedulePreviewRefresh(); return;
        }
        if (action === "remove-condition-card") {
          preserveEditorDraftBeforeRerender();
          const cardId = button.dataset.cardId;
          const cards = collectConditionSets();
          const target = cards.find(card => contextText(asObj(card).id) === cardId);
          if (!target) return;
          if (target.is_default === true) {
            clearHeatExchangerCustomFields(target.id, heatExchangerCascadeKeys);
            Object.keys(asObj(target.fields)).forEach(key => { target.fields[key] = ""; });
            if (contextText(target.type) === "heat_exchanger" && heatExchangerType([target]) === "Micro-Channel") target.fields.fin_type = "Flat";
            if (contextText(target.type) === "operating") {
              fanCountCustomCards.delete(contextText(target.id));
              target.fans = [{id:"fan_1", name:"", location:"", running:true, values:{fan_rpm:""}}];
            }
            requestState.conditions = {...asObj(requestState.conditions), condition_sets:cards}; syncEditorFromState();
            window.requestAnimationFrame(() => document.querySelector(`[data-condition-card="${CSS.escape(cardId)}"] input:not([disabled]), [data-condition-card="${CSS.escape(cardId)}"] select:not([disabled])`)?.focus());
            schedulePreviewRefresh(); return;
          }
          const typeCards = cards.filter(card => contextText(asObj(card).type) === contextText(asObj(target).type));
          const targetIndex = typeCards.indexOf(target);
          clearHeatExchangerCustomFields(target.id, heatExchangerCascadeKeys);
          fanCountCustomCards.delete(contextText(target.id));
          const remaining = cards.filter(card => contextText(asObj(card).id) !== cardId);
          const remainingTypeCards = remaining.filter(card => contextText(asObj(card).type) === contextText(asObj(target).type));
          const focusCard = remainingTypeCards[Math.min(targetIndex, remainingTypeCards.length - 1)];
          requestState.conditions = {...asObj(requestState.conditions), condition_sets:remaining}; syncEditorFromState();
          if (focusCard) window.requestAnimationFrame(() => document.querySelector(`[data-condition-card="${CSS.escape(focusCard.id)}"] input:not([disabled]), [data-condition-card="${CSS.escape(focusCard.id)}"] select:not([disabled])`)?.focus());
          schedulePreviewRefresh(); return;
        }
        if (action === "add-condition-value" || action === "remove-condition-value") mutateConditionValues(button.dataset.fieldKey, action === "add-condition-value" ? "add" : "remove", Number.parseInt(button.dataset.index || "0",10));
      });
      $("formView").addEventListener("input", event => {
        if (event.target.matches("input, textarea, select") && !event.target.matches("select[data-case-field]")) {
          const path = event.target.dataset.path || event.target.dataset.conditionKey || event.target.dataset.productField || event.target.dataset.rowList || event.target.dataset.cardField || "";
          if (path) touchedFields.add(path);
          schedulePreviewRefresh();
        }
      });
      $("formView").addEventListener("change", event => {
        if (event.target.matches("input, textarea, select")) renderScreenNavigation();
        if (event.target.matches('[data-product-field="drawing_no"]')) schedulePreviewRefresh();
        else if (event.target.matches("select[data-heat-exchanger-type]")) handleHeatExchangerTypeChange(event.target);
        else if (event.target.matches("select[data-heat-exchanger-field]")) handleHeatExchangerCascadeChange(event.target);
        else if (event.target.matches("input[data-heat-exchanger-custom-field]")) handleHeatExchangerCustomInput(event.target);
        else if (event.target.matches("select[data-fan-count]")) handleFanCountChange(event.target);
        else if (event.target.matches("input[data-fan-count-custom]")) resizeFanRpmInputs(contextText(event.target.dataset.cardId), event.target.value);
        else if (event.target.matches("#operationModeSelect")) updateOperationMode(event.target.value).catch(err => pushMessage("assistant", `운전 구분 변경 실패: ${err.message}`));
        else if (event.target.matches("input[data-condition-option]")) { requestState = collectState(); renderConditionFields(); schedulePreviewRefresh(); }
        else if (event.target.matches("#quickBusinessUnitSelect")) updateRequestContextDraft("business_unit", event.target.value);
        else if (event.target.matches("#quickProductGroupSelect")) {
          if (event.target.value === "__custom__") {
            quickProductGroupCustomMode = true;
            updateRequestContextDraft("product_group", "");
            window.requestAnimationFrame(() => $("quickProductGroupCustomInput")?.focus());
          } else {
            quickProductGroupCustomMode = false;
            updateRequestContextDraft("product_group", event.target.value);
          }
        }
        else if (event.target.matches("#quickProductGroupCustomInput")) updateRequestContextDraft("product_group", event.target.value);
        else if (event.target.matches("#quickPlatformSelect")) {
          if (event.target.value === "__custom__") {
            quickPlatformCustomMode = true;
            updateRequestContextDraft("platform", "");
            window.requestAnimationFrame(() => $("quickPlatformCustomInput")?.focus());
          } else {
            quickPlatformCustomMode = false;
            updateRequestContextDraft("platform", event.target.value);
          }
        }
        else if (event.target.matches("#quickPlatformCustomInput")) updateRequestContextDraft("platform", event.target.value);
        else if (event.target.matches("#quickAnalysisTypeSelect")) updateRequestContextDraft("analysis_type", event.target.value);
        else if (event.target.matches("#decisionUseSelect")) { renderDecisionUseAuxiliary(event.target.value); schedulePreviewRefresh(); }
        else if (event.target.matches("select[data-dropdown-path]")) handleDropdownChange(event.target);
        else if (event.target.matches("select[data-condition-select]")) handleConditionSelectChange(event.target);
        else if (event.target.matches("input[type='checkbox']")) schedulePreviewRefresh();
      });
    }

    async function loadBootstrap(){
      const res = await fetch("/api/bootstrap");
      const data = await res.json();
      adoptStateFromResponse(data);
      resetCaseImpactBaseline();
      schema = data.schema || {};
      heatExchangerCatalog = asArray(asObj(data.heat_exchanger_catalog).rows);
      activeTopTab = "write";
      requestState.metadata = {...asObj(requestState.metadata), active_top_tab: activeTopTab};
      asArray(asObj(requestState.metadata).touched_fields).forEach(item => touchedFields.add(String(item)));
      renderAgentDock();
      setupDropdowns();
      restoreChatHistoryFromState();
      syncEditorFromState();
      fetchProductHierarchyOptions().catch(err => pushMessage("assistant", `제품군/platform 목록 불러오기 실패: ${err.message}`));
    }

    wireEvents();
    loadBootstrap().catch(err => pushMessage("assistant", `불러오기 실패: ${err.message}`));
  </script>
</body>
</html>
"""
