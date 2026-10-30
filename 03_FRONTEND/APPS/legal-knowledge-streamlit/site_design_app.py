"""Legal Knowledge UI R3. Synthetic design only; no backend/model calls.
Upload this entire Python file into a Streamlit webapp. No other UI files needed.
The embedded UI is derived from the verified Sites v2 source; see SOURCE_ASSETS.
"""
import os
if os.environ.get('GENOS_RAG_ONTOLOGY_CONFIG'):
    import runpy
    from pathlib import Path
    runpy.run_path(str(Path(__file__).with_name('app.py')),run_name='__main__')
    import streamlit as st
    st.stop()
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="법률 지식 운영실", page_icon="📚", layout="wide",
                   initial_sidebar_state="collapsed")
st.markdown("""<style>
html, body, [data-testid="stAppViewContainer"], .stApp {background:#f7f8fb;}
[data-testid="stHeader"], [data-testid="stToolbar"], #MainMenu, footer {display:none!important;}
.block-container {max-width:none!important;padding:0!important;}
[data-testid="stMainBlockContainer"] {max-width:none!important;padding:0!important;}
[data-testid="stVerticalBlock"] {gap:0!important;}
iframe[title="streamlit.components.v1.html"] {border:0;display:block;}
</style>""", unsafe_allow_html=True)

SOURCE_ASSETS = {'style.css': '175c96bcaeaf162973bf69ccb3cf6820cf82ae93b93e7c0afd76065cbbeebfe3', 'workspaces.css': 'a67693632a6078bc7d46f25b62684f20d42a591855f1a3cf4ef279dedd337510', 'fixtures.js': '9a7f5b071ff4f17aa0bd5166f4ff592490e775df0042bfbe24fa6d3e4576bf3e', 'graph.js': 'c8bb0013c561901bb5eba99e312571166a0a323cb16b0a0bc501c3232cd50fd8', 'workspaces.js': '4ff80edbb229ad38036fb8e35742e526a81b8a5c148134cab3f36dc0357ec4de', 'app.js': '96c765a13bf32b44db59b5e055e3d99f052595aa1c386725b95d9d6ba77e7335', 'index.html': 'eecee2fff82676b2efe301a40c666ae1facf538017979ebc321d9ff667cc95ac'}
HTML = r"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="description" content="법률 지식 운영실 — 배치부터 온톨로지 검증까지 연결하는 예시 데이터 기반 UI 프로토타입">
  <meta name="theme-color" content="#132c38"><title>법률 지식 운영실 · Knowledge Operations</title>
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 40 40'%3E%3Crect width='40' height='40' rx='10' fill='%230c817f'/%3E%3Cpath d='M10 11v18m0-8 17-10M10 21l17 8' stroke='white' stroke-width='3' fill='none'/%3E%3C/svg%3E">
  <style>
@charset "UTF-8";
:root{--ink:#203740;--muted:#7a8b94;--line:#e3e9ed;--teal:#087e80;--navy:#132c38;--bg:#f5f7f9;--amber:#a67224;--red:#b95b53;--green:#298979;font-family:"Malgun Gothic","Apple SD Gothic Neo","Noto Sans KR",system-ui,sans-serif;color:var(--ink);background:var(--bg);font-size:13px;font-synthesis:none}
*{box-sizing:border-box}body{margin:0}button,input,select,textarea{font:inherit}button,a,input,textarea,select{-webkit-tap-highlight-color:transparent}button{cursor:pointer}a{color:inherit;text-decoration:none}button{color:inherit}button:disabled{opacity:.45;cursor:not-allowed}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible,canvas:focus-visible{outline:3px solid #4ab4b8;outline-offset:3px}input,select,textarea{border:1px solid #dce4e9;border-radius:7px;background:white;padding:10px 12px;color:var(--ink);min-width:0}textarea{width:100%;resize:vertical;line-height:1.9}input[type=checkbox]{accent-color:var(--teal);width:16px;height:16px;flex-shrink:0}h1,h2,h3,h4,p{margin:0}h1{font-size:28px;letter-spacing:-1.15px;line-height:1.6}h2{font-size:18px;letter-spacing:-.5px}h3{font-size:15px;letter-spacing:-.35px}p{line-height:1.85}small{font-size:11px}svg{display:block}.skip{position:fixed;top:-100px;z-index:50;background:white;padding:15px}.skip:focus{top:0}
#sidebar{position:fixed;inset:0 auto 0 0;width:236px;background:var(--navy);color:#b8cdd7;display:flex;flex-direction:column;z-index:20;padding:29px 17px 0}.brand{display:flex;align-items:center;gap:12px;color:#f5fafb;font-size:16px;font-weight:700;padding:0 4px;white-space:nowrap}.brand-icon{font-family:Georgia,serif;font-size:30px;line-height:42px;border:1px solid #557783;border-radius:10px;width:40px;text-align:center;font-weight:400;color:#b4ebe1}.brand-icon span{color:#65c4b4}.brand small{display:block;font-size:8px;letter-spacing:1.2px;margin-top:6px;color:#89aab9}.workspace-tag{border:1px solid #34505d;border-radius:7px;margin:25px 0 29px;padding:11px 10px;display:flex;gap:8px;align-items:center;font-size:11px;color:#a7bfcb}.workspace-tag>span:last-child{margin-left:auto}.status-dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:#5ab9a5}.nav-label{color:#7295a5;font-size:10px;letter-spacing:1.2px;margin:0 12px 12px}nav{display:grid;gap:5px}.nav-item{border:1px solid transparent;border-radius:7px;width:100%;display:flex;align-items:center;gap:11px;padding:13px 11px;font-size:12px;background:transparent;color:#bbced6;text-align:left}.nav-item:hover{background:#203f4b;color:white}.nav-item.active{background:#24505a;color:#eefcf9;border-color:#37636b}.nav-item .icon{opacity:.8}.nav-item .count{font-size:10px;background:#304b58;color:#a5c4cc;border-radius:5px;min-width:21px;padding:3px 5px;text-align:center;margin-left:auto}.nav-item.active .count{background:#4c7475;color:white}.side-note{margin:auto 11px 36px;padding-top:28px}.side-note .orbit{display:block;font-size:31px;color:#78afa7;margin-bottom:12px}.side-note b{color:#b8cfd8;font-size:14px;line-height:1.8;letter-spacing:-.3px}.side-note p{color:#7498a7;font-size:10px;margin-top:12px}.side-foot{display:flex;align-items:center;gap:10px;border-top:1px solid #2c4653;padding:19px 0;color:#c0d1d9;font-size:11px}.avatar{width:30px;height:30px;background:#375562;border:1px solid #526b77;border-radius:50%;display:grid;place-items:center;font-family:serif;color:#d8e6ec}.side-foot small{font-size:9px;color:#7697a7;display:block;margin-top:4px}.foot-mark{font-size:9px;color:#7996a2;margin-left:auto}.shell{margin-left:236px;min-height:100vh}.topbar{height:68px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);background:#fff;padding:0 33px}.breadcrumb{font-size:11px;color:#8a9ba4;display:flex;gap:14px;align-items:center}.breadcrumb b{font-weight:500;color:#506875}.top-right{display:flex;gap:17px;align-items:center}.demo-pill{font-size:9px;color:#6b9292;letter-spacing:1.3px;display:flex;gap:6px;align-items:center}.icon-btn{border:0;background:none;min-width:30px;min-height:30px;font-size:19px;color:#76909b;border-radius:5px}.icon-btn:hover{background:#eef4f5}.mobile-menu{display:none}.shell main{padding:28px 33px 25px;max-width:1700px;margin:auto;min-height:calc(100vh - 115px)}footer{padding:15px 33px 22px;line-height:1.8;color:#8a9aa3;font-size:10px}.heading{display:flex;align-items:center;justify-content:space-between;gap:15px;margin-bottom:21px}.eyebrow{display:block;color:#8297a1;font-size:9px;letter-spacing:1.8px;margin-bottom:8px;font-weight:600}.heading p{font-size:12px;color:#81929b;margin-top:3px}.heading-actions{display:flex;gap:8px;align-items:center;flex-shrink:0}.btn{min-height:37px;padding:9px 14px;border:1px solid #d9e3e8;background:white;border-radius:7px;font-size:11px;font-weight:600;display:inline-flex;align-items:center;justify-content:center;gap:8px;white-space:nowrap}.btn:hover{background:#f0f6f6;border-color:#bad3d4}.btn.primary{background:var(--teal);border-color:var(--teal);color:white}.btn.primary:hover{background:#096d70}.btn.danger{color:var(--red)}.btn.small{min-height:30px;font-size:10px;padding:6px 10px}.btn.text{border:0;background:transparent;padding-left:0;color:var(--teal)}.muted{color:var(--muted)}.subtext{font-size:11px;color:var(--muted);line-height:1.9}.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:10px;letter-spacing:.2px}.badge{font-size:10px;line-height:1.4;padding:4px 7px;border-radius:4px;white-space:nowrap;background:#e9f4ef;color:#358372;display:inline-flex;align-items:center;gap:5px}.badge.amber{background:#fff2db;color:#a2752f}.badge.red{background:#faeae7;color:#b56459}.badge.gray{background:#eef2f5;color:#7b8d98}.badge.blue{background:#edf3fa;color:#6486a5}.panel{background:white;border:1px solid var(--line);border-radius:10px;overflow:hidden}.panel-pad{padding:22px}.panel-header{padding:20px 22px 16px;display:flex;align-items:center;justify-content:space-between;gap:10px}.panel-header p{font-size:10px;color:#8d9da6;margin-top:6px}.row{display:flex;align-items:center;gap:9px}.spread{display:flex;justify-content:space-between;align-items:center;gap:12px}.stack{display:grid;gap:18px}.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:15px;margin-bottom:22px}.metric{padding:19px 21px;background:white;border:1px solid var(--line);border-radius:9px;position:relative}.metric .metric-icon{position:absolute;right:18px;top:19px;color:#8da5af}.metric .label{color:#7f919c;font-size:11px}.metric strong{font-size:29px;font-weight:600;display:block;letter-spacing:-1px;margin:10px 0 7px}.metric strong small{color:#92a0a7;font-size:11px;font-weight:400;margin-left:6px;letter-spacing:0}.metric .foot{font-size:10px;color:#8e9da6}.metric .foot.attention{color:#b78c42}.two-col{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:20px;align-items:start}.flow{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px;padding:8px 22px 22px}.flow-node{position:relative;border:1px solid #e2ebe9;background:#fbfdfd;border-radius:8px;padding:17px 12px}.flow-node.warn{background:#fffdf5;border-color:#ead9b1}.flow-node:after{content:'›';position:absolute;right:-10px;top:45%;color:#92aab3;z-index:1;background:white}.flow-node:last-child:after{display:none}.flow-node .flow-index{font-size:9px;color:#8fa6b1;letter-spacing:1px;display:flex;justify-content:space-between}.flow-node b{display:block;font-size:12px;margin:15px 0 10px}.flow-node strong{font-size:22px;font-weight:500}.flow-node small{display:block;color:#8b9da5;font-size:9px;line-height:1.8;margin-top:10px}.panel-bottom{border-top:1px solid #edf1f4;background:#fcfdfd;padding:12px 22px;display:flex;align-items:center;justify-content:space-between;font-size:10px;color:#90a1aa}.tabs{display:flex;gap:25px;border-bottom:1px solid var(--line);padding:0 22px}.tab{padding:13px 0;border:0;background:none;color:#81949e;font-size:11px;border-bottom:2px solid transparent}.tab.active{color:var(--teal);border-color:var(--teal);font-weight:600}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;text-align:left;font-size:11px;white-space:nowrap}th{font-weight:400;font-size:10px;color:#8c9ba5;padding:14px 20px;background:#fcfdfd;border-bottom:1px solid #edf1f4}td{padding:17px 20px;border-bottom:1px solid #edf1f4;line-height:1.7}tbody tr:last-child td{border-bottom:0}tbody tr.clickable{cursor:pointer}tbody tr.clickable:hover,tbody tr.selected{background:#f0f8f7}td small{color:#91a2ab;display:block;font-size:9px}.inbox-row{display:flex;gap:12px;padding:16px 20px;border-top:1px solid #edf1f4;align-items:center;width:100%;background:transparent;text-align:left;border-left:0;border-right:0;border-bottom:0}.inbox-row:hover{background:#f6faf9}.inbox-symbol{width:30px;height:30px;border-radius:7px;background:#fff4df;color:#bb9550;display:grid;place-items:center}.inbox-row b{font-size:11px;font-weight:500}.inbox-row small{display:block;color:#94a4ad;font-size:9px;margin-top:6px}.inbox-row .number{margin-left:auto;color:#a47a37;font-size:16px}.next-step{padding:20px;background:#edf5f4;border:1px solid #dce9e6;border-radius:9px}.next-step .eyebrow{color:#7da49e}.next-step h3{font-size:14px;color:#386b68;line-height:1.8}.next-step p{font-size:11px;color:#7b9a97;margin:10px 0}.next-step .btn{background:white;color:#467e79;border-color:#cfdfdb}.review-layout{display:grid;grid-template-columns:285px minmax(0,1fr);gap:19px;align-items:start}.queue-head{padding:18px;border-bottom:1px solid var(--line)}.queue-head input{width:100%;margin-top:15px;font-size:11px;background:#f9fbfc}.queue-item{width:100%;text-align:left;border:0;border-bottom:1px solid var(--line);border-left:3px solid transparent;padding:19px 17px;background:white}.queue-item:last-child{border-bottom:0}.queue-item.active{border-left-color:var(--teal);background:#f1f8f7}.queue-item:hover{background:#f6faf9}.queue-item b{display:block;font-size:12px;margin:12px 0 8px;font-weight:600}.queue-item small{font-size:10px;line-height:1.9;color:#8a9ca5}.detail-top{padding:23px;border-bottom:1px solid var(--line)}.detail-top h2{margin:12px 0 7px}.detail-body{padding:23px}.source-grid{display:grid;grid-template-columns:1fr 1fr;gap:17px}.source-title{font-size:10px;color:#8397a1;margin-bottom:10px;display:flex;justify-content:space-between}.source{padding:18px;background:#f7f9fb;border:1px solid #e3e9ed;border-radius:7px;font-size:12px;line-height:2;white-space:pre-wrap;min-height:156px;word-break:keep-all;overflow-wrap:anywhere}.source.highlight{background:#f0f8f4;border-color:#d7e9de}.addition{border-left:3px solid #71b496;background:#f0f8f3;padding:14px 17px;margin:18px 0;color:#54866c;font-size:11px;line-height:1.9}.callout{background:#fffaf0;border:1px solid #efe2c9;border-radius:7px;padding:13px 16px;font-size:11px;color:#ab8a51;line-height:1.85}.callout.blue{background:#eff6f8;border-color:#dde9ee;color:#6a8a9a}.form-group{margin:19px 0}.form-group label.field-label{display:block;color:#65808b;font-size:11px;margin-bottom:9px}.form-group input[type=text],.form-group select{width:100%}.checkbox-label{display:flex;align-items:flex-start;gap:8px;font-size:11px;line-height:1.8;color:#6c838e}.actions{border-top:1px solid var(--line);padding:17px 23px;display:flex;gap:9px;align-items:center}.actions .subtext{margin-right:auto;font-size:10px}.route-path{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:18px 0}.route-path span{background:#eff5f7;border:1px solid #e1e9ec;border-radius:7px;padding:12px;font-size:11px;color:#63838f}.route-path i{font-style:normal;color:#9daeb6}.wiki-body{line-height:2;color:#57727f;font-size:12px;white-space:pre-wrap}.wiki-body h3{color:#334e5b;margin:18px 0 10px}.reference{background:#f8fafb;border:1px solid #e2e9ed;border-radius:7px;padding:14px 16px;margin:12px 0;font-size:11px;line-height:1.9;color:#72909c}.reference b{color:#526f7c;display:block}.timeline{padding-left:18px;border-left:2px solid #e3ecef;font-size:11px;line-height:1.8;color:#708b97;margin:14px 0}.timeline b{display:block;color:#506d79}.timeline small{color:#9aabb4}.section-gap{margin-top:23px}
/* The graph is a navigation surface; all editing stays in the inspector. */
.ontology-bar{display:flex;justify-content:space-between;align-items:center;padding:16px 20px;border-bottom:1px solid var(--line);gap:15px;flex-wrap:wrap}.ontology-bar select{min-width:200px;font-size:12px;border:0;padding:0;font-weight:600}.legend{display:flex;flex-wrap:wrap;gap:6px}.legend button{display:flex;align-items:center;gap:6px;padding:6px 9px;background:#f6f8fa;border:1px solid #e8edf0;border-radius:5px;font-size:10px;color:#7b929f}.legend button.off{opacity:.4;text-decoration:line-through}.legend-dot{width:7px;height:7px;border-radius:50%;display:inline-block;background:var(--node-color)}.ontology-layout{display:grid;grid-template-columns:minmax(0,1fr) 305px}.graph-area{position:relative;background:#111e2b;min-height:572px;overflow:hidden}.graph-toolbar{position:absolute;top:18px;left:18px;right:18px;display:flex;align-items:center;justify-content:space-between;z-index:2;gap:12px}.graph-toolbar input{color:#c2d7e1;background:#1b2c3d;border:1px solid #314657;border-radius:6px;font-size:10px;width:210px;height:33px}.graph-toolbar input::placeholder{color:#7894a6}.graph-toggle{display:flex;background:#1b2c3d;border:1px solid #314657;border-radius:6px;padding:3px}.graph-toggle button{font-size:10px;background:transparent;color:#88a6b5;border:0;border-radius:3px;padding:5px 10px}.graph-toggle button.active{background:#355367;color:#e8f6ff}.graph-area canvas{display:block;width:100%;height:572px;touch-action:none;cursor:grab}.graph-area canvas:active{cursor:grabbing}.graph-caption{position:absolute;bottom:48px;left:21px;font-size:10px;color:#648396;pointer-events:none}.graph-caption b{display:block;color:#a0bfcb;font-size:12px;margin-bottom:5px;font-weight:400}.graph-controls{position:absolute;right:18px;bottom:54px;display:flex;gap:5px}.graph-controls button{border:1px solid #365061;background:#1c3141;color:#b6d2dc;border-radius:5px;min-width:30px;height:29px;font-size:11px}.graph-meta{position:absolute;bottom:0;left:0;right:0;border-top:1px solid #253c4d;background:#142635;padding:11px 19px;display:flex;justify-content:space-between;color:#7090a1;font-size:9px}.graph-meta b{font-weight:400;color:#a9c7d1}.inspector{border-left:1px solid var(--line);background:white;min-width:0}.inspector-head{padding:20px;border-bottom:1px solid var(--line)}.inspector-head h3{font-size:16px;margin:11px 0 5px}.inspector-head .mono{color:#9aaab2}.inspector .tabs{padding:0 20px;gap:20px}.inspector-body{padding:18px 20px;min-height:375px;font-size:11px;line-height:1.9}.inspector-body label{font-size:10px}.inspector-body .source{min-height:0;font-size:10px;padding:13px}.inspector-body .reference{font-size:10px;padding:11px}.inspector-actions{padding:0 20px 20px}.inspector-actions .btn{width:100%}.relationship{display:flex;gap:9px;align-items:center;border-bottom:1px solid #eef2f4;padding:10px 0;cursor:pointer;font-size:10px;color:#6d8793;background:transparent;border-top:0;border-right:0;border-left:0;width:100%;text-align:left}.relationship .arrow{color:#7bb8b0}.relationship b{font-weight:500;color:#385e6c}.node-list{padding:12px 20px;border-top:1px solid var(--line);display:flex;align-items:center;gap:7px;flex-wrap:wrap}.node-list span{font-size:10px;color:#8fa1ac;margin-right:5px}.node-list button{border:1px solid #e2eaee;background:#f8fafb;color:#76909c;font-size:9px;padding:5px 9px;border-radius:4px}.node-list button.active{background:#e7f4f0;border-color:#a3cec1;color:#408b76}.graph-note{font-size:10px;color:#8a9da7;margin-top:12px;display:flex;justify-content:space-between;gap:12px}.sim-config{padding:20px 22px;display:flex;gap:22px;align-items:end}.sim-config .form-group{margin:0;flex:1}.sim-config .btn{margin-bottom:1px}.sim-placeholder{padding:60px 20px;text-align:center;color:#8ca2ae;border-top:1px solid var(--line)}.sim-placeholder .placeholder-icon{width:58px;height:58px;border-radius:15px;background:#f0f6f6;color:#83b5ac;display:grid;place-items:center;margin:0 auto 18px}.sim-placeholder h3{color:#63808e;margin-bottom:9px}.sim-summary{display:flex;gap:22px;padding:20px 22px;border-top:1px solid var(--line);align-items:center}.sim-summary .score{padding-right:23px;border-right:1px solid var(--line)}.sim-summary strong{font-size:23px;font-weight:500}.sim-summary span{font-size:11px;color:#8ba1ac;margin-left:9px}.sim-result-detail{margin:18px 22px;padding:18px;border:1px solid #e4ebee;border-radius:8px}.sim-result-detail h3{font-size:13px;margin-bottom:13px}.sim-result-detail .source{min-height:0;font-size:11px}.audit-empty{padding:40px;text-align:center;color:#8c9ca6}.error-text{font-size:11px;color:#b85d55;line-height:1.8;margin:12px 0}.spacer{height:14px}#toast{position:fixed;bottom:25px;left:calc(50% + 118px);transform:translateX(-50%) translateY(20px);background:#1d444c;color:#e8f6f4;padding:14px 22px;border-radius:8px;box-shadow:0 6px 28px #16343825;font-size:12px;line-height:1.8;opacity:0;pointer-events:none;z-index:40;max-width:calc(100vw - 35px);transition:.2s}#toast.show{opacity:1;transform:translateX(-50%) translateY(0)}dialog{max-width:480px;width:calc(100% - 40px);border:1px solid #dbe7e9;border-radius:14px;padding:30px;color:var(--ink);box-shadow:0 20px 80px #102d3b33}dialog::backdrop{background:#102a3a55;backdrop-filter:blur(3px)}dialog p{font-size:12px;color:#7a929d;margin:18px 0}.close-modal.icon-btn{float:right}
.inspector{display:flex;flex-direction:column;height:572px}.inspector-head,.inspector>.tabs,.inspector-actions{flex-shrink:0}.inspector-body{flex:1;min-height:0;overflow-y:auto}.inspector-actions{padding-top:14px;border-top:1px solid #edf1f4}
@media(min-width:1600px){.graph-area canvas{height:620px}.graph-area{min-height:620px}.inspector{height:620px}}
@media(max-width:1250px){#sidebar{width:210px;padding-inline:12px}.shell{margin-left:210px}.brand{font-size:14px}.brand small{font-size:7px}.shell main{padding:24px}.topbar{padding-inline:24px}.two-col{grid-template-columns:minmax(0,1fr) 260px}.flow{gap:8px;padding-inline:16px}.flow-node{padding:14px 9px}.flow-node b{font-size:10px}.flow-node small{font-size:8px}.ontology-layout{grid-template-columns:minmax(0,1fr) 280px}.review-layout{grid-template-columns:240px minmax(0,1fr)}.panel-header{padding-inline:18px}.sim-config{gap:12px}#toast{left:calc(50% + 105px)}}
@media(max-width:1050px){.two-col{grid-template-columns:1fr}.two-col>.stack:last-child{grid-template-columns:1fr 1fr}.metrics{gap:10px}.metric{padding:16px}.ontology-layout{grid-template-columns:1fr}.graph-area canvas{height:450px}.graph-area{min-height:450px}.inspector{border-left:0;border-top:1px solid var(--line)}.inspector-body{min-height:0}.review-layout{grid-template-columns:210px minmax(0,1fr)}.source-grid{grid-template-columns:1fr}.sim-config{flex-wrap:wrap}.heading-actions .btn{font-size:10px}.heading{align-items:flex-start}h1{font-size:25px}.node-list{gap:5px}}
@media(max-width:760px){#sidebar{transform:translateX(-100%);transition:.2s;width:236px}.menu-open #sidebar{transform:translateX(0)}#scrim{display:none;position:fixed;inset:0;background:#102a3a66;z-index:15}.menu-open #scrim{display:block}.shell{margin-left:0}.topbar{height:57px;padding:0 16px;gap:12px;justify-content:flex-start}.mobile-menu{display:block}.breadcrumb{font-size:10px;gap:9px}.top-right{margin-left:auto;gap:8px}.demo-pill{font-size:7px;letter-spacing:.7px}.top-right .icon-btn{font-size:17px}.shell main{padding:22px 16px}.heading{display:block;margin-bottom:20px}.heading-actions{margin-top:15px}.heading p{font-size:11px}h1{font-size:25px}.metrics{grid-template-columns:1fr 1fr}.metric strong{font-size:26px}.metric .label{font-size:10px}.metric .foot{font-size:9px}.flow{grid-template-columns:1fr;gap:8px}.flow-node{display:grid;grid-template-columns:30px 1fr 50px 100px;align-items:center;padding:13px}.flow-node .flow-index span:last-child{display:none}.flow-node b{margin:0;font-size:11px}.flow-node strong{font-size:18px}.flow-node small{margin:0;font-size:9px}.flow-node:after{display:none}.two-col>.stack:last-child{grid-template-columns:1fr}.review-layout{grid-template-columns:1fr}.queue{display:flex;overflow-x:auto}.queue-head{display:none}.queue-item{min-width:230px;border-bottom:0;border-right:1px solid var(--line)}.queue-item b{font-size:11px}.source-grid{grid-template-columns:1fr}.detail-top,.detail-body{padding:18px}.actions{flex-wrap:wrap;padding:17px 18px}.actions .subtext{width:100%;font-size:9px}.ontology-bar{padding:14px;gap:15px}.legend{gap:4px}.legend button{font-size:9px;padding:5px 7px}.graph-area,.graph-area canvas{height:430px;min-height:430px}.graph-toolbar{left:12px;right:12px;top:14px}.graph-toolbar input{width:175px;font-size:9px}.graph-caption{left:16px;bottom:70px}.graph-controls{bottom:44px;right:12px}.graph-meta{padding:11px;font-size:8px}.graph-note{display:block;line-height:1.9}.node-list{padding:12px}.node-list button{font-size:8px}.sim-config{display:grid;grid-template-columns:1fr;padding:18px}.sim-summary{gap:15px;padding:18px}.sim-summary .score{padding-right:14px}.sim-summary strong{font-size:20px}.sim-summary span{font-size:9px;margin-left:4px}.sim-result-detail{margin:15px}.panel-header{padding:18px}.panel-header h2{font-size:16px}.tabs{gap:19px;padding:0 18px}footer{padding:5px 18px 20px;font-size:9px}#toast{left:50%;font-size:11px}.table-wrap td,.table-wrap th{padding:14px}.panel-bottom{padding:12px 16px;line-height:1.8;gap:14px}.source{min-height:100px}}
@media(max-width:1050px){.inspector{height:auto}.inspector-body{max-height:none;overflow:visible}}
@media(prefers-reduced-motion:reduce){*{transition:none!important;scroll-behavior:auto!important}}

</style><style>
/* Knowledge has three forms: a registry, a publication, and a model. */
:root{--ink:#253247;--muted:#748297;--teal:#5365cb;--line:#e5e8ef;--bg:#f7f8fb;font-size:14px;font-synthesis:weight}
body{background:#f7f8fb}#sidebar{background:#141e30;width:224px;padding-inline:16px}.shell{margin-left:224px}.brand{font-size:15px;letter-spacing:-.5px}.brand-icon{background:#263451;border:1px solid #46577c;color:#d8ddff;border-radius:12px}.brand-icon span{color:#a398ff}.brand small{color:#8d9db8;letter-spacing:1.15px}.workspace-tag{background:#1a263b;border-color:#344259;color:#adb9d1}.status-dot{background:#9da9ff}.nav-label{color:#788aa6}.nav-item{font-size:12px;padding-block:14px;border-radius:8px;color:#acb9ce}.nav-item.active{background:#303b59;border-color:#495579;color:#f3f0ff;box-shadow:inset 3px 0 #aa9cf6}.nav-item:hover{background:#253149}.nav-item .count{color:#c8d0e3;background:#2c3952}.side-note .orbit{color:#a79cde}.side-note b{color:#c1cbe0}.side-note p{color:#8394ae}.side-foot{border-color:#2f3b50}.avatar{background:#35415b;border-color:#4e5c78}.shell main{padding:32px 30px;max-width:1760px}.topbar{height:64px;padding-inline:30px;border-color:#e9edf2}.breadcrumb{font-size:11px}.demo-pill{color:#858eb0}.eyebrow{font-size:10px;font-weight:700;letter-spacing:2px;color:#7d87a0;margin-bottom:9px}h1{font-size:32px;font-weight:700;letter-spacing:-1.3px;line-height:1.45}.heading{margin-bottom:23px}.heading p{font-size:12px;line-height:1.9;color:#7e8ba0;margin-top:8px}.btn{font-size:12px;min-height:39px;border-radius:8px}.btn.primary{background:var(--accent,#5865c6);border-color:var(--accent,#5865c6);box-shadow:0 3px 7px #4c5bb41a}.btn.primary:hover{filter:brightness(.94);background:var(--accent,#5865c6)}.btn.text{color:var(--accent,#5865c6)}.panel{border-radius:12px;border-color:#e4e8ef;box-shadow:0 3px 14px #1d324004}.badge{font-size:10px;padding:5px 8px;font-weight:500}.badge.amber{background:#fff3dc;color:#967025}.badge.gray{background:#edf1f7;color:#7d8ba0}.badge.blue{background:#edf1ff;color:#6571be}.metric strong{font-size:32px;font-weight:600}.metric .label{font-size:12px}.metric .foot{font-size:11px}.metric{border-radius:12px}.source,.subtext{color:#6f8092}.subtext{font-size:12px}.form-group label.field-label{font-size:12px}.source{font-size:13px}.icon-btn{color:#8793aa}.tabs .tab{font-size:12px}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}
.knowledge-switch{display:flex;gap:5px;padding:5px;background:#edf0f6;border:1px solid #e8ebf1;border-radius:10px;width:fit-content;margin-bottom:24px}.knowledge-switch a{display:flex;align-items:center;gap:8px;padding:9px 14px;border-radius:7px;font-size:12px;color:#7f8ba0}.knowledge-switch small{font-size:9px;color:#9aa5b8;margin-left:3px}.knowledge-switch a.active{background:white;color:var(--accent,#5668c6);box-shadow:0 2px 5px #30405c0d;font-weight:600}.knowledge-switch a:hover{color:#4b5f96}.section-caption{display:block;font-size:9px;letter-spacing:1.7px;font-weight:700;color:#959db1;margin-bottom:14px}.tag{display:inline-block;border-radius:5px;background:#f0f2f6;color:#74849c;padding:5px 8px;font-size:10px;font-weight:600}.tag.blue{background:#ecf2ff;color:#6985c8}.tag.violet{background:#f1ecfb;color:#9578bb}
/* Shortcut registry */
[data-page=shortcut]{--accent:#5374cc}.registry-hero{display:flex;align-items:center;gap:20px;padding:25px 27px;background:#eef3fd;border:1px solid #e0e8f8;border-radius:12px;margin-bottom:24px;position:relative;overflow:hidden}.registry-symbol{width:62px;height:64px;border-radius:16px;display:grid;place-items:center;flex-shrink:0;color:#6d88cb;background:#e0e8fa;border:1px solid #d3dff7;transform:rotate(-5deg)}.registry-hero h2{font-size:17px;font-weight:600;color:#3f5276;letter-spacing:-.6px}.registry-hero p{font-size:11px;color:#8798b8;margin-top:7px}.registry-hero .eyebrow{color:#8c9ec5;font-size:8px;letter-spacing:1.8px;margin-bottom:8px}.registry-stats{display:flex;gap:26px;align-self:stretch;margin-left:auto;align-items:center;padding-left:22px;border-left:1px solid #dce4f4}.registry-stats>div{min-width:57px}.registry-stats strong{font-size:30px;color:#647eae;font-weight:500;letter-spacing:-1px;display:block}.registry-stats span{font-size:9px;color:#8d9fbd;display:block;margin-top:5px}.registry-toolbar{display:flex;gap:16px;padding:19px 20px;align-items:center;justify-content:space-between;flex-wrap:wrap;border-bottom:1px solid #e6ebf2}.status-tabs{display:flex;align-items:center;gap:5px}.status-tabs button{border:0;background:transparent;color:#8b97aa;border-radius:7px;padding:8px 10px;font-size:11px;display:flex;align-items:center;gap:7px}.status-tabs button span{font-size:10px;background:#f0f2f7;color:#8893a8;min-width:18px;text-align:center;border-radius:4px;padding:1px 3px}.status-tabs button.active{color:#5e75b8;background:#edf2fc;font-weight:600}.status-tabs button.active span{background:#dce6fa;color:#6481b7}.registry-filters{display:flex;gap:8px;align-items:center}.search-field{display:flex;align-items:center;gap:9px;background:white;border:1px solid #e2e7ef;border-radius:7px;padding:0 11px;color:#9ca7b9}.search-field input{border:0;outline:none;padding:9px 0;background:transparent;width:190px;font-size:11px;color:#5f6f88}.search-field:focus-within{outline:2px solid #b9c8f0;outline-offset:1px}.search-field input:focus-visible{outline:0}.search-field input::placeholder{color:#8c99ad}.registry-filters select{padding:8px 10px;font-size:10px;border-color:#e2e7ef;color:#8190a7;max-width:130px}.shortcut-table th{font-size:10px;letter-spacing:.2px;color:#919bad;background:#fbfcfe;padding:15px 18px}.shortcut-table td{padding:21px 18px;font-size:11px;border-color:#edf0f5}.shortcut-row{cursor:pointer;transition:background .15s}.shortcut-row:hover,.shortcut-row:focus-visible{background:#f5f8fe}.shortcut-row td:first-child{min-width:245px;max-width:305px}.record-id{font-family:ui-monospace,Consolas,monospace;color:#8291aa;font-size:9px;letter-spacing:.8px;display:block;margin-bottom:6px}.shortcut-table td strong{font-size:13px;font-weight:600;color:#435675;display:block}.record-question{font-size:11px;color:#8390a6;display:block;margin-top:5px;overflow:hidden;text-overflow:ellipsis;max-width:290px;white-space:nowrap}.condition-tags{display:flex;gap:5px;flex-wrap:wrap;max-width:165px}.condition-tags span{padding:3px 6px;background:#f4f6fa;border:1px solid #e9edf4;border-radius:4px;color:#697d9c;font-size:9px;white-space:nowrap}.evidence-count{display:flex;align-items:center;gap:6px;color:#637ca3;font-size:10px}.shortcut-table td small{font-size:9px;color:#8694a9;margin-top:5px}.shortcut-table td small.record-warning{color:#ba9480}.usage-number{font-variant-numeric:tabular-nums;font-size:17px;color:#7e91ad;font-weight:500}.record-date{font-size:11px;color:#687d9c}.row-arrow{color:#adbad1;font-size:16px!important}.shortcut-row:hover .row-arrow{color:#698aca}.registry-table-foot{display:flex;justify-content:space-between;align-items:center;gap:15px;padding:17px 21px;border-top:1px solid #e9edf3;font-size:10px;color:#8996a8}.registry-table-foot b{color:#6d81a5;font-weight:500}.registry-note{display:flex;justify-content:space-between;gap:16px;font-size:10px;color:#a0abba;margin-top:18px;line-height:1.8}.registry-note span:first-child{display:flex;gap:8px;align-items:center}.empty-search{text-align:center;padding:50px 20px;color:#8b9aaf;font-size:12px;line-height:2}.record-drawer{position:fixed;left:auto;right:0;top:0;bottom:0;width:min(580px,100%);max-width:100%;height:100dvh;max-height:100dvh;margin:0;border:0;border-radius:0;padding:0;box-shadow:-15px 0 70px #1e2b4425}.record-drawer::backdrop{background:#15264155;backdrop-filter:blur(3px)}.record-drawer .panel{border:0;border-radius:0;box-shadow:none}.drawer-top{padding:25px 24px;display:flex;justify-content:space-between;align-items:center;background:#f7f9fd;border-bottom:1px solid #e6ebf3}.drawer-top h2{font-size:20px}.drawer-top .eyebrow{font-size:8px}.record-drawer .detail-top{padding-top:20px}.record-drawer .detail-top h2{font-size:20px}.record-drawer .source-grid{grid-template-columns:1fr 1fr}.record-drawer .route-path{gap:7px}.record-drawer .route-path span{font-size:10px;max-width:140px;padding:10px}.record-drawer .actions{position:sticky;bottom:0;background:#fff;box-shadow:0 -8px 22px #13284306;flex-wrap:wrap}.record-drawer .actions .subtext{width:100%;font-size:10px}.record-drawer .form-group textarea{font-size:12px}.record-drawer .error-text{margin-bottom:0}
/* Legal Wiki: library / document / context */
[data-page=wiki]{--accent:#7d66c7}.wiki-workspace{display:grid;grid-template-columns:205px minmax(0,1fr) 170px;gap:24px;align-items:start}.wiki-library{padding:15px 0;position:sticky;top:20px;min-width:0}.library-label{font-size:9px;letter-spacing:1.7px;color:#8290a7;font-weight:700;display:flex;justify-content:space-between;margin:0 8px 19px}.library-label span{font-size:8px;font-weight:400;letter-spacing:.7px;color:#afb7c5}.wiki-search{background:white;margin:0 0 25px;padding:0 9px}.wiki-search input{width:100%;min-width:0;font-size:10px;padding-block:10px}.library-group{margin-bottom:23px}.library-group h3{font-size:10px;letter-spacing:0;color:#8490a5;display:flex;justify-content:space-between;align-items:center;padding:0 10px 11px;font-weight:600}.library-group h3 span{font-size:8px;color:#b0b8c5;font-weight:400}.library-page{border:0;background:none;width:100%;display:flex;align-items:center;gap:9px;text-align:left;padding:12px 10px;color:#6f7e94;border-radius:7px;font-size:11px;line-height:1.7;margin:2px 0}.library-page span{flex:1}.library-page svg{flex-shrink:0;color:#adb4c7}.library-page:hover{background:#eff0f8;color:#7a70a9}.library-page.active{background:#edebf8;color:#8071ae;font-weight:600}.library-page.active svg{color:#a094c7}.page-status{width:4px;height:4px;border-radius:50%;background:#c5b08c;flex-shrink:0}.page-status.published{background:#92b9a9}.page-status.conflict{background:#d4a196}.library-footer{padding:25px 14px 0;border-top:1px solid #e4e7ef;margin-top:34px}.library-spark{font-size:29px;color:#afa5cb;display:block;margin-bottom:14px}.library-footer b{font-size:12px;font-weight:500;color:#8791a9;line-height:1.9}.library-footer p{font-size:9px;color:#acb3c3;margin-top:11px}.library-footer small{font-size:8px;color:#b1b9c6;display:block;margin-top:8px}.wiki-document-column{min-width:0}.wiki-doc-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:15px;padding:0 4px}.wiki-doc-toolbar>span{font-size:10px;color:#9aa4b7;display:flex;align-items:center;gap:8px}.wiki-doc-toolbar i{font-style:normal;color:#c8cddd}.wiki-doc-tabs{display:flex;gap:5px}.wiki-doc-tabs button{padding:7px 9px;border:0;border-radius:5px;background:none;color:#96a0b4;font-size:10px}.wiki-doc-tabs button.active{background:#edebf7;color:#8d7bb9;font-weight:600}.wiki-paper{background:#fff;border:1px solid #e5e7f0;border-radius:12px;overflow:hidden;box-shadow:0 8px 26px #28305104}.wiki-cover-line{height:5px;background:linear-gradient(90deg,#b4a6d8 0%,#e5def2 70%,#f4eff9 100%)}.wiki-title-block{padding:33px 36px 0}.wiki-document-icon{width:55px;height:57px;display:grid;place-items:center;background:#f0ecf9;color:#a397bf;border:1px solid #e8e0f3;border-radius:14px;margin-bottom:24px;transform:rotate(-4deg)}.wiki-title-block .row{flex-wrap:wrap;gap:8px}.ai-origin{color:#9381b1;font-size:9px;letter-spacing:.2px}.wiki-title-block h2{font-size:29px;font-weight:700;letter-spacing:-1.2px;line-height:1.55;color:#3d3d55;margin:15px 0 11px;word-break:keep-all;overflow-wrap:anywhere}.wiki-title-block>p{font-size:13px;color:#72768d;line-height:1.9;word-break:keep-all}.wiki-properties{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:25px;padding:20px 0;border-top:1px solid #f0eef5;border-bottom:1px solid #f0eef5}.wiki-properties div{display:grid;gap:8px}.wiki-properties span{font-size:9px;color:#90899f}.wiki-properties b{font-size:10px;font-weight:500;color:#6b627d}.wiki-content{padding:29px 36px 36px}.wiki-abstract{display:flex;align-items:flex-start;gap:12px;background:#f8f6fc;border:1px solid #eee9f5;border-radius:8px;padding:17px 18px;margin-bottom:30px}.wiki-abstract>span{color:#b7a6d4;font-size:23px;line-height:1}.wiki-abstract b{font-size:11px;color:#8265ac;font-weight:600}.wiki-abstract p{font-size:11px;color:#7d708e;line-height:1.9;margin-top:7px;word-break:keep-all}.wiki-prose{font-size:14px;line-height:2;color:#5c6175;word-break:keep-all;overflow-wrap:anywhere}.wiki-prose h3{font-size:17px;font-weight:600;color:#55566f;letter-spacing:-.4px;margin:29px 0 14px;scroll-margin-top:30px}.wiki-prose h3:first-child{margin-top:0}.wiki-prose p{margin:10px 0;line-height:2}.wiki-prose strong{font-weight:600;color:#5f5b7d}.wiki-prose ol{margin:13px 0 20px;padding-left:23px}.wiki-prose li{padding:5px 0 5px 6px}.wiki-prose li::marker{color:#b3a6ce;font-size:11px}.wiki-prose blockquote{margin:22px 0;border-left:3px solid #d4c9e6;background:#faf8fd;padding:13px 18px;font-size:12px;color:#a195b8;line-height:1.9}.wiki-inline-link{font-size:inherit;padding:1px 3px;border:0;background:#f1eef8;color:#9480b5;border-radius:3px;cursor:pointer}.wiki-sources{margin-top:37px;padding-top:24px;border-top:1px solid #eeedf3;scroll-margin-top:20px}.wiki-sources h3{font-size:13px;color:#828198;font-weight:600}.wiki-sources>.spread>span{font-size:9px;color:#9787ab}.citation-card{display:flex;align-items:center;gap:12px;border:1px solid #eae8f0;background:#fdfcfe;border-radius:7px;padding:15px;margin:17px 0;color:#b5adc7}.citation-index{font-family:ui-monospace,monospace;font-size:9px;background:#f2eef8;border-radius:5px;padding:8px 7px;color:#b7a6d0}.citation-card>div{flex:1}.citation-card b{font-size:11px;color:#6d5d84;font-weight:500;line-height:1.7}.citation-card p{font-size:9px;color:#9b8da8;margin-top:6px}.related-pages{display:flex;gap:7px;flex-wrap:wrap}.related-pages .btn{font-size:9px;color:#8b75a9;border-color:#ede8f2;background:#fcfbfd}.wiki-page-footer{padding:18px 35px;border-top:1px solid #f1eff5;background:#fdfcfe;display:flex;align-items:center;justify-content:space-between;gap:12px;font-size:8px;color:#b2abbe}.wiki-page-footer span:first-child{display:flex;gap:7px;align-items:center;letter-spacing:1px}.wiki-context{padding-top:55px;position:sticky;top:20px}.wiki-toc{display:flex;flex-direction:column;border-left:1px solid #e5e2ec;padding-left:13px;gap:4px}.wiki-toc button{text-align:left;background:none;border:0;font-size:10px;color:#7d8399;padding:7px 0;line-height:1.6}.wiki-toc button:first-child{color:#a193bd}.wiki-toc button:hover{color:#7d66c7}.wiki-context-rule{height:1px;background:#e8e7ef;margin:30px 0}.connected-ontology{border:1px solid #e8e5f0;border-radius:9px;padding:17px 15px;background:#f2f1f8;color:#b0a6c6}.connected-ontology b{display:block;font-size:11px;font-weight:500;color:#81719c;line-height:1.7;margin:14px 0 8px}.connected-ontology p{font-size:10px;color:#8e829f;line-height:1.9}.connected-ontology .btn{font-size:10px;margin-top:9px;color:#8c72b2}.wiki-editor-note{font-size:11px;color:#88729f;background:#f8f6fc;border-radius:7px;padding:14px;display:flex;gap:10px;line-height:1.9}.wiki-content input[type=text]{font-size:12px}.wiki-content .markdown-editor{font-family:ui-monospace,'Malgun Gothic',monospace;font-size:12px;background:#fbfbfe;line-height:1.9;padding:18px}.wiki-version{display:flex;align-items:flex-start;gap:14px;border:1px solid #e9e5f0;background:#fdfcfe;border-radius:8px;padding:20px 17px;margin-top:20px}.version-dot{width:8px;height:8px;border-radius:50%;background:#c3b0d8;margin-top:4px;flex-shrink:0}.version-dot.published{background:#9bbcae}.wiki-version>div{flex:1}.wiki-version b{font-size:12px;font-weight:500;color:#8d809e}.wiki-version p{font-size:11px;color:#8f819d;margin-top:8px}.wiki-version small{display:block;font-size:9px;color:#bbb2c4;margin-top:10px}.wiki-scope-text{font-size:12px;line-height:2;color:#9a8eaa;margin:15px 0 22px}#wiki-edit-preview:empty{display:none}#wiki-edit-preview{margin-top:28px;border-top:1px solid #e9e4f2;padding-top:25px}
/* Ontology: model tree / graph / inspector */
[data-page=ontology]{--accent:#368c88}.ontology-panel{border-color:#dce6e9}.ontology-layout{grid-template-columns:175px minmax(0,1fr) 275px}.ontology-tree{background:#f8fbfc;border-right:1px solid #e3ebee;height:572px;overflow-y:auto;padding:20px 12px}.model-tree-title{padding:0 5px 20px;border-bottom:1px solid #e1e9ed;margin-bottom:17px}.model-tree-title .section-caption{font-size:7px;letter-spacing:1.4px;color:#8fa7ad;margin-bottom:9px}.model-tree-title h3{font-size:14px;color:#577c84;font-weight:600}.model-tree-title p{font-size:9px;color:#9db0b9;margin-top:8px}.model-class{margin-bottom:17px}.model-class summary{display:flex;align-items:center;gap:7px;font-size:10px;color:#5f8490;cursor:pointer;list-style:none;padding:0 4px}.model-class summary:before{content:'⌄';font-size:10px;color:#b0c1c6}.model-class:not([open]) summary:before{content:'›'}.model-class summary small{font-size:8px;margin-left:auto;color:#b3c3ca}.model-class>div{margin:9px 0 0 12px;border-left:1px solid #e1e9ec;padding-left:6px}.model-class button{display:flex;align-items:center;gap:5px;background:transparent;border:0;border-radius:4px;font-size:9px;text-align:left;width:100%;padding:7px 5px;color:#77959f;line-height:1.6}.model-class button span{color:#c0ced3}.model-class button.active{color:#588d88;background:#e9f4f1}.model-class button:hover{background:#edf4f5}.model-tree-note{font-size:8px;line-height:1.9;color:#acbdc4;padding:14px 5px;border-top:1px solid #e3ebed}.ontology-bar{padding:18px 20px}.ontology-bar select{font-size:13px;color:#547582;font-weight:600}.legend button{background:#f4f8f8;border-color:#e3ecec;font-size:9px;color:#718f95}.graph-area{background:#111e2b}.inspector-head h3{font-size:18px;color:#4a727b;font-weight:600}.inspector .tab{font-size:11px}.inspector-body{font-size:12px;color:#78919a}.inspector-body .source-title{color:#9cb0b8}.inspector-body .reference{color:#7c9ba5;font-size:10px}.inspector-body .reference b{color:#7b9a9f}.relationship{font-size:10px;padding:12px 0;color:#7897a0}.relationship b{font-size:11px;color:#74989a}.graph-note{font-size:9px;color:#97acb6}.graph-caption b{font-size:11px}.graph-caption{font-size:9px}.ontology-panel .node-list{padding:13px 18px}.ontology-panel .node-list button{font-size:9px}.ontology-tree .legend-dot{width:5px;height:5px}.inspector-head .badge{font-size:9px}
@media(min-width:1600px){.ontology-tree{height:620px}.wiki-workspace{grid-template-columns:220px minmax(0,1fr) 180px;gap:30px}.wiki-title-block{padding:37px 45px 0}.wiki-content{padding:32px 45px 40px}.ontology-layout{grid-template-columns:190px minmax(0,1fr) 300px}}
@media(max-width:1400px){.wiki-workspace{grid-template-columns:190px minmax(0,1fr);gap:22px}.wiki-context{display:none}.registry-hero{padding:22px}.registry-hero h2{font-size:15px}.registry-stats{gap:18px}.registry-stats>div{min-width:45px}.registry-stats strong{font-size:25px}.ontology-layout{grid-template-columns:155px minmax(0,1fr) 255px}.ontology-tree{padding:18px 9px}.ontology-bar{gap:12px}.ontology-bar select{min-width:175px}.legend button{padding:5px 6px}}
@media(max-width:1150px){#sidebar{width:205px;padding-inline:12px}.shell{margin-left:205px}.shell main{padding:26px 22px}.brand{font-size:13px}.brand-icon{width:34px}.registry-hero{gap:14px}.registry-hero h2{font-size:14px}.registry-stats{gap:15px;padding-left:16px}.registry-stats span{font-size:8px}.registry-symbol{width:46px;height:50px}.wiki-workspace{grid-template-columns:175px minmax(0,1fr);gap:17px}.wiki-title-block{padding:27px 27px 0}.wiki-content{padding:25px 27px 30px}.wiki-title-block h2{font-size:25px}.ontology-layout{grid-template-columns:160px minmax(0,1fr)}.ontology-tree{height:480px}.ontology-layout .graph-area,.ontology-layout .graph-area canvas{height:480px;min-height:480px}.ontology-layout .inspector{grid-column:1/-1;height:auto;border-left:0;border-top:1px solid #e2ebee;display:grid;grid-template-columns:220px minmax(0,1fr)}.ontology-layout .inspector-head{grid-column:1;grid-row:1/3;border-right:1px solid #e5ecef}.ontology-layout .inspector>.tabs{grid-column:2}.ontology-layout .inspector-body{grid-column:2;max-height:370px}.ontology-layout .inspector-actions{grid-column:1/-1}.knowledge-switch small{display:none}}
@media(max-width:900px){.registry-hero{flex-wrap:wrap}.registry-hero>div:nth-child(2){flex:1}.registry-stats{border-left:0;border-top:1px solid #dce4f3;width:100%;padding:17px 0 0;margin:5px 0 0;gap:35px}.registry-stats>div{display:flex;gap:9px;align-items:center}.registry-stats span{margin:0}.wiki-workspace{grid-template-columns:1fr}.wiki-library{position:static;padding:0}.library-label,.library-footer{display:none}.wiki-search{max-width:300px;margin-bottom:14px}#wiki-library-items{display:flex;gap:14px;overflow-x:auto;padding-bottom:8px}.library-group{margin:0;flex-shrink:0;min-width:220px}.library-group h3{font-size:9px;padding-bottom:5px}.library-page{padding:9px 10px;white-space:nowrap}.wiki-doc-toolbar{margin-top:8px}.wiki-title-block{padding-top:25px}.wiki-properties{grid-template-columns:repeat(4,1fr)}.registry-filters{flex-wrap:wrap}.registry-note{display:block}.registry-note span{margin:7px 0}.registry-hero p{font-size:10px}}
@media(max-width:760px){#sidebar{width:236px;padding-inline:16px}.shell{margin-left:0}.shell main{padding:24px 16px}.topbar{height:57px;padding-inline:16px}.heading{margin-bottom:20px}h1{font-size:29px}.heading p{font-size:11px}.knowledge-switch{width:100%;justify-content:space-between;margin-bottom:20px;padding:4px}.knowledge-switch a{flex:1;justify-content:center;padding:9px 11px;font-size:11px;gap:7px}.registry-hero{padding:19px 17px}.registry-symbol{width:44px;height:48px;border-radius:11px}.registry-hero h2{font-size:14px;line-height:1.8;word-break:keep-all}.registry-hero .eyebrow{font-size:7px;letter-spacing:1px}.registry-hero p{font-size:10px;line-height:1.9}.registry-stats{gap:20px;justify-content:space-between}.registry-stats strong{font-size:25px}.registry-stats span{font-size:8px}.registry-toolbar{padding:14px 12px;gap:14px}.status-tabs{gap:2px;width:100%;justify-content:space-between}.status-tabs button{font-size:10px;padding:7px 8px;gap:4px}.status-tabs button span{font-size:9px}.registry-filters{width:100%;gap:7px}.registry-filters .search-field{width:100%}.registry-filters .search-field input{flex:1;width:100%;font-size:11px}.registry-filters select{flex:1;max-width:none;font-size:10px}.shortcut-table th,.shortcut-table td{padding:15px 16px}.shortcut-row td:first-child{position:sticky;left:0;background:white;z-index:1;border-right:1px solid #edf0f5;min-width:220px}.shortcut-row:hover td:first-child{background:#f5f8fe}.record-question{max-width:210px}.shortcut-table td strong{font-size:11px}.registry-table-foot{padding:15px;font-size:9px}.registry-note{font-size:9px}.record-drawer .source-grid{grid-template-columns:1fr}.record-drawer .actions{gap:7px}.wiki-workspace{gap:15px}.library-page{font-size:10px}.wiki-doc-toolbar{flex-wrap:wrap;gap:12px;padding-inline:2px}.wiki-doc-toolbar>span{font-size:9px}.wiki-doc-tabs button{padding:7px 8px;font-size:9px}.wiki-title-block{padding:25px 22px 0}.wiki-title-block h2{font-size:25px;margin-top:14px}.wiki-title-block>p{font-size:11px}.wiki-document-icon{width:45px;height:46px;margin-bottom:20px}.wiki-title-block .badge{font-size:9px}.ai-origin{font-size:8px}.wiki-properties{grid-template-columns:1fr 1fr;row-gap:18px;padding:18px 0}.wiki-properties span{font-size:8px}.wiki-properties b{font-size:10px}.wiki-content{padding:24px 22px 28px}.wiki-abstract{padding:15px 13px;gap:9px}.wiki-abstract p{font-size:10px}.wiki-abstract b{font-size:10px}.wiki-prose{font-size:12px}.wiki-prose h3{font-size:16px}.wiki-prose blockquote{padding:11px 13px;font-size:11px}.wiki-page-footer{padding:16px 20px;font-size:7px}.wiki-sources>.spread{align-items:flex-start}.wiki-sources h3{font-size:12px}.wiki-sources>.spread>span{font-size:8px}.citation-card{padding:12px;gap:9px}.citation-card b{font-size:10px}.citation-card p{font-size:8px}.wiki-content .row{flex-wrap:wrap}.wiki-content .form-group .spread{display:block}.wiki-content .form-group .spread .subtext{font-size:9px;display:block;margin-bottom:7px}.ontology-layout{grid-template-columns:1fr}.ontology-tree{height:auto;max-height:220px;display:flex;overflow:auto;padding:15px 12px;gap:16px;border-right:0;border-bottom:1px solid #e2ebee}.model-tree-title{min-width:110px;border:0;margin:0;padding:0}.model-tree-title .section-caption{font-size:6px}.model-tree-title h3{font-size:12px}.model-tree-title p{font-size:8px;white-space:nowrap}.model-class{min-width:125px;margin:0}.model-class summary{white-space:nowrap;font-size:9px}.model-class button{font-size:8px;white-space:nowrap}.model-tree-note{display:none}.ontology-layout .graph-area,.ontology-layout .graph-area canvas{height:430px;min-height:430px}.ontology-layout .inspector{display:flex;grid-column:auto}.ontology-layout .inspector-head{border-right:0}.ontology-layout .inspector-body{max-height:none;overflow:visible}.ontology-bar{padding:15px 12px}.ontology-bar select{font-size:12px}.legend{gap:5px}.legend button{font-size:8px}.graph-toolbar input{width:175px}.graph-caption b{font-size:10px}.graph-caption{font-size:8px}.inspector-head h3{font-size:19px}.ontology-panel .node-list{padding:12px}.ontology-panel .node-list button{font-size:8px}.graph-note{font-size:8px;line-height:2}}

@media(max-width:760px){#wiki-library-items{gap:7px;padding-bottom:8px;max-height:64px}.wiki-library .library-group{display:contents}.wiki-library .library-group h3{display:none}.wiki-library .library-page{width:auto;min-width:170px;height:43px;flex-shrink:0;white-space:nowrap;border:1px solid #e5e7ef;background:#fff;padding:10px;margin:0}.wiki-library .library-page.active{background:#edebf8;border-color:#ded7f1}.wiki-search{max-width:none;margin-bottom:12px}.wiki-prose{font-size:13px}.wiki-prose p{line-height:1.95}}

</style>
<style>.table-wrap{position:relative;}</style>
</head>
<body>
  <a class="skip" href="#main">본문으로 이동</a>
  <aside id="sidebar">
    <a class="brand" href="#pipeline"><span class="brand-icon">K<span>·</span></span><span>법률 지식 운영실<small>KNOWLEDGE OPERATIONS</small></span></a>
    <div class="workspace-tag"><span class="status-dot"></span> 디자인 워크스페이스 <span>⌄</span></div>
    <div class="nav-label">운영 워크플로우</div><nav id="nav" aria-label="주 메뉴"></nav>
    <div class="side-note"><span class="orbit">↗</span><b>지식을 검토하고,<br>다시 검증합니다.</b><p>배치 → 검토 → 지식 관리 → 시뮬레이션</p></div>
    <div class="side-foot"><span class="avatar">D</span><div>디자인 검토자<small>예시 데이터 · 개인 체험</small></div><span class="foot-mark">v4</span></div>
  </aside>
  <div id="scrim"></div>
  <div class="shell">
    <header class="topbar"><button class="icon-btn mobile-menu" id="menu-toggle" aria-label="메뉴 열기" aria-expanded="false">☰</button><div class="breadcrumb">워크스페이스 <span>/</span> <b id="crumb">배치 모니터</b></div><div class="top-right"><span class="demo-pill"><span class="status-dot"></span> UI PROTOTYPE</span><button class="icon-btn" id="about-button" aria-label="프로토타입 안내">ⓘ</button></div></header>
    <main id="main" tabindex="-1"></main>
    <footer>예시 문서·예시 수치로 구성한 화면입니다. 변경은 이 탭에만 저장되며 Oracle·Dataiku·RAG에 반영되지 않습니다.</footer>
  </div>
  <div id="toast" role="status" aria-live="polite"></div>
  <dialog id="about"><button class="icon-btn close-modal" aria-label="닫기">×</button><span class="eyebrow">이 화면에 관하여</span><h2>업무 흐름을 함께 검토하는 공간</h2><p>여섯 관리 화면과 승인·편집 동선을 체험할 수 있습니다. 실제 업무 데이터, 계정 정보, 내부 문서는 포함하지 않았습니다.</p><p>시뮬레이션은 결과 화면의 예시이며 실제 법률 판단이나 RAG 실행 결과가 아닙니다. 새 탭에서는 별도의 체험 상태로 시작합니다.</p><button class="btn primary close-modal">확인했습니다</button></dialog>

<script>
// Synthetic design fixtures only. No internal business records.
const DEMO = {
  "STRUCTURES": [
    {
      "id": "ST-001",
      "title": "표 아래 각주 누락",
      "document": "예시 위험검토지침",
      "location": "제4조 · 표 2 · 각주 ①",
      "type": "각주 누락",
      "status": "승인 대기",
      "source": "표 2. 검토 항목\n대상 업무 | 확인 자료\nPF | 사업성 평가 자료\n① 기준일이 없는 자료는 기준일 확인 대상으로 남긴다.",
      "before": "표 2. 검토 항목\n대상 업무 | 확인 자료\nPF | 사업성 평가 자료",
      "fix": "① 기준일이 없는 자료는 기준일 확인 대상으로 남긴다.",
      "impact": "표의 적용 범위를 읽을 때 각주가 함께 전달됩니다."
    },
    {
      "id": "ST-002",
      "title": "항·호 경계 분리 보완",
      "document": "예시 자료관리기준",
      "location": "제7조 제2항",
      "type": "조항 분리",
      "status": "승인 대기",
      "source": "② 다음 자료를 확인한다.\n1. 작성 기준일\n2. 작성 부서",
      "before": "② 다음 자료를 확인한다. 1. 작성 기준일 2. 작성 부서",
      "fix": "② 다음 자료를 확인한다.\n1. 작성 기준일\n2. 작성 부서",
      "impact": "항과 호를 구분해 원문 위치를 탐색할 수 있습니다."
    },
    {
      "id": "ST-003",
      "title": "명시 참조 연결 보완",
      "document": "예시 검토업무절차",
      "location": "제3조 제1항 → 별표 1",
      "type": "참조 연결",
      "status": "승인 대기",
      "source": "검토 항목은 별표 1을 따른다.",
      "before": "검토 항목은 별표 1을 따른다.\n참조 연결: 미확보",
      "fix": "같은 문서의 별표 1을 참조 끝점으로 연결",
      "impact": "본문에서 명시적으로 참조한 별표를 열 수 있습니다."
    }
  ],
  "SHORTCUTS": [
    {
      "id": "SC-021",
      "title": "PF 기준일 확인 경로",
      "question": "PF 검토에 필요한 기준일은 어디서 확인하나요?",
      "status": "승인 대기",
      "eligible": true,
      "run": "DEMO-RUN-104",
      "state": "완료",
      "reads": "예시 위험검토지침 / 제4조 / v1",
      "scope": "동일 업무·동일 조건",
      "path": [
        "업무 유형 확인",
        "기준일 관련 원문 열람",
        "확인 결과·미확인 기록"
      ],
      "business": "PF",
      "uses": 8,
      "conditions": [
        "업무 PF",
        "기준일 확인"
      ],
      "evidenceCount": 1,
      "created": "2026-10-21"
    },
    {
      "id": "SC-022",
      "title": "충당금 관련 조사 경로",
      "question": "충당금 검토 시 어떤 자료가 필요한가요?",
      "status": "승인 대기",
      "eligible": false,
      "run": "DEMO-RUN-108",
      "state": "부분 완료",
      "reads": "일부 원문 미확보",
      "scope": "범위 미확정",
      "path": [
        "용어 확인",
        "연결 조항 조사 중단",
        "미확보 근거 기록"
      ],
      "business": "공통",
      "uses": 0,
      "conditions": [
        "근거 미확보",
        "범위 미확정"
      ],
      "evidenceCount": 0,
      "created": "2026-10-21"
    },
    {
      "id": "SC-018",
      "title": "PF 자료 제출 범위 확인",
      "question": "PF 검토에 필요한 자료의 범위를 어떻게 확인하나요?",
      "status": "승인됨",
      "eligible": true,
      "run": "DEMO-RUN-100",
      "state": "완료",
      "reads": "예시 위험검토지침 / 제4조·별표1 / v1",
      "scope": "동일 업무·원문 판본 일치",
      "path": [
        "검토 대상 자료 목록 확인",
        "내규 제4조와 별표 열람",
        "누락 자료 표시"
      ],
      "business": "PF",
      "uses": 23,
      "conditions": [
        "검토 대상 일치",
        "원문 v1"
      ],
      "evidenceCount": 2,
      "created": "2026-10-20",
      "reason": "디자인 예시의 검토 상태"
    },
    {
      "id": "SC-016",
      "title": "문서 시행일 확인 경로",
      "question": "문서의 시행일과 질문의 기준일을 어떻게 비교하나요?",
      "status": "승인됨",
      "eligible": true,
      "run": "DEMO-RUN-93",
      "state": "완료",
      "reads": "예시 문서관리기준 / 제2조 / v1",
      "scope": "동일 업무·원문 판본 일치",
      "path": [
        "문서 시행일 열람",
        "질문의 기준일 확인",
        "적용 판본 확인"
      ],
      "business": "공통",
      "uses": 12,
      "conditions": [
        "시행일 확인",
        "판본 일치"
      ],
      "evidenceCount": 1,
      "created": "2026-10-19",
      "reason": "디자인 예시의 검토 상태"
    },
    {
      "id": "SC-014",
      "title": "RP 대상 범위 조사",
      "question": "RP 관련 검토에서 먼저 확인할 항목은 무엇인가요?",
      "status": "승인 대기",
      "eligible": true,
      "run": "DEMO-RUN-86",
      "state": "완료",
      "reads": "예시 RP 업무지침 / 제3조 / v1",
      "scope": "동일 업무·원문 판본 일치",
      "path": [
        "대상 업무 확인",
        "연결된 원문 열람",
        "예외 조건 확인"
      ],
      "business": "RP",
      "uses": 3,
      "conditions": [
        "대상 업무 RP",
        "동일 조건"
      ],
      "evidenceCount": 1,
      "created": "2026-10-18",
      "reason": "디자인 예시의 검토 상태"
    },
    {
      "id": "SC-011",
      "title": "변경 원문 재확인 경로",
      "question": "원문 버전이 바뀌면 어떤 지식을 다시 검토하나요?",
      "status": "보류",
      "eligible": false,
      "run": "DEMO-RUN-79",
      "state": "부분 완료",
      "reads": "일부 원문 미확보",
      "scope": "범위 미확정",
      "path": [
        "참조 버전 확인",
        "변경 문서 조회",
        "연결 지식 재검토 대기"
      ],
      "business": "공통",
      "uses": 0,
      "conditions": [
        "판본 변경",
        "재검토 대기"
      ],
      "evidenceCount": 0,
      "created": "2026-10-17",
      "reason": "디자인 예시의 검토 상태"
    }
  ],
  "WIKIS": [
    {
      "id": "WK-01",
      "title": "PF 검토의 확인 순서",
      "status": "게시됨",
      "revision": 2,
      "scope": "PF 검토",
      "body": "### 검토 목적\n질문에 답하기 전에 **검토 대상과 기준일**을 먼저 확인합니다. 이 문서는 자료를 찾고 확인하는 순서를 안내하는 예시 지식입니다.\n\n### 확인 순서\n1. 질문에 해당하는 업무 유형과 검토 대상 자료를 확인합니다.\n2. 관련 내규의 적용 범위와 문서 버전을 확인합니다.\n3. 내규에서 명시적으로 연결된 외규의 원문을 읽습니다.\n4. 예외 조건과 미확인 사항을 함께 기록합니다.\n\n### 기준일이 없는 경우\n기준일을 확보하지 못했다면 임의로 채우지 않고 **미확인 상태**로 남깁니다. 날짜별 적용 범위는 [[기준일과 시행일 구분]]을 함께 참고합니다.\n\n> ① 기준일이 없는 자료는 기준일 확인 대상으로 남긴다.\n\n### 적용 범위와 예외\n동일한 PF 업무라도 자료의 기준일과 원문 판본이 다르면 재확인이 필요합니다. 새로운 정보를 확보하면 기존 조사와 연결해 이어갑니다.",
      "source": "예시 위험검토지침 · 제4조 · v1",
      "description": "PF 검토를 시작할 때 필요한 정보와 원문 탐색 순서를 정리합니다.",
      "summary": "대상 업무와 기준일을 먼저 확인하고, 내규에서 연결된 외규의 원문을 따라 검토합니다."
    },
    {
      "id": "WK-02",
      "title": "기준일과 시행일 구분",
      "status": "검토 필요",
      "revision": 1,
      "scope": "공통",
      "body": "### 확인 사항\n질문의 기준일과 문서 시행일을 구분해서 기록합니다.\n\n### 미확인 처리\n날짜를 확보하지 못하면 추정해서 채우지 않습니다.",
      "source": "예시 자료관리기준 · 제7조 · v1",
      "description": "질문의 기준일과 원문 시행일을 구분해 적용 판본을 확인합니다.",
      "summary": "기준일은 질문의 시점, 시행일은 문서의 적용 시점입니다. 둘 다 확인 가능한 근거와 연결합니다."
    },
    {
      "id": "WK-03",
      "title": "서로 다른 해석 검토",
      "status": "상충 확인",
      "revision": 1,
      "scope": "공통",
      "body": "### 상충 상태\n두 해석의 원문과 적용 범위를 나란히 보존합니다.\n\n### 재검토\n어떤 조건에서 해석이 달라지는지 확인합니다.",
      "source": "출처 연결 재확인 필요",
      "description": "상충하는 해석을 지우지 않고 근거와 범위를 나란히 보존합니다.",
      "summary": "서로 다른 해석이 있으면 양쪽 근거를 남기고 조건과 버전을 다시 검토합니다."
    },
    {
      "id": "WK-04",
      "title": "원문 판본과 참조 관리",
      "status": "게시됨",
      "revision": 1,
      "scope": "공통",
      "body": "### 문서 판본 확인\n지식에서 참조한 원문의 **문서명·위치·판본**을 함께 확인합니다.\n\n### 변경된 원문 재검토\n원문 판본이 변경되면 연결 지식의 적용 범위를 확인합니다.\n1. 변경된 원문과 기존 참조를 확인합니다.\n2. 연결된 위키와 온톨로지를 함께 검토합니다.\n3. 확인 결과와 미확인 범위를 남깁니다.",
      "source": "예시 문서관리기준 · 제2조 · v1",
      "description": "근거의 판본과 연결 상태를 확인하는 검토 안내입니다."
    },
    {
      "id": "WK-05",
      "title": "미확인 사항과 조사 재개",
      "status": "초안",
      "revision": 0,
      "scope": "공통",
      "body": "### 미확인 기록\n확보하지 못한 정보와 필요한 근거를 구분해 남깁니다.\n\n### 다시 시작하는 조건\n1. 누락된 자료가 확보되었는지 확인합니다.\n2. 이전 조사 기록의 상태와 판본을 확인합니다.\n3. 확인된 지점부터 조사를 이어갑니다.",
      "source": "원문 연결 전",
      "description": "추가 정보를 확보한 뒤 조사를 재개하는 흐름의 초안입니다."
    }
  ],
  "ONTOLOGIES": [
    {
      "id": "ON-01",
      "title": "PF 검토 조건",
      "revision": 3,
      "status": "검토 대기",
      "business": "PF",
      "require_date": true,
      "unknown": "미확인 유지",
      "wiki": "WK-01"
    },
    {
      "id": "ON-02",
      "title": "공통 기준일 확인",
      "revision": 1,
      "status": "초안",
      "business": "공통",
      "require_date": true,
      "unknown": "미확인 유지",
      "wiki": "WK-02"
    }
  ],
  "SCENARIOS": [
    {
      "id": "T01",
      "case": "정상 입력",
      "input": "업무·기준일·원문 확보",
      "expected": "검토 항목 연결",
      "observed": "검토 항목 연결",
      "status": "일치",
      "node": "적용 조건"
    },
    {
      "id": "T02",
      "case": "기준일 누락",
      "input": "업무만 확인 / 기준일 없음",
      "expected": "미확인 유지",
      "observed": "적용으로 처리",
      "status": "불일치",
      "node": "미확인 처리"
    },
    {
      "id": "T03",
      "case": "업무 범위 밖",
      "input": "다른 업무 유형",
      "expected": "제외 이유 기록",
      "observed": "제외 이유 기록",
      "status": "일치",
      "node": "적용 조건"
    },
    {
      "id": "T04",
      "case": "예외 해당",
      "input": "명시된 제외 조건 충족",
      "expected": "해당 항목 제외",
      "observed": "해당 항목 제외",
      "status": "일치",
      "node": "제외·재개"
    },
    {
      "id": "T05",
      "case": "원문 버전 변경",
      "input": "참조 원문 변경 / 재확인 전",
      "expected": "원문 재확인",
      "observed": "원문 재확인 대기",
      "status": "미확인",
      "node": "근거 연결"
    },
    {
      "id": "T06",
      "case": "누락 자료 확보",
      "input": "미확인 기준일 추가 확보",
      "expected": "기존 조사 재개",
      "observed": "기존 조사 재개",
      "status": "일치",
      "node": "제외·재개"
    }
  ]
};

</script>
<script>
'use strict';
/* Small, local-only 3D projection. No WebGL, CDN, model, or remote data dependency. */
class KnowledgeGraph {
 constructor(canvas,data,groups,options={}){
  this.canvas=canvas;this.ctx=canvas.getContext('2d');this.data=data;this.groups=groups;this.options=options;
  this.mode=options.mode||'3d';this.off=new Set(options.off);this.selected=options.selected;
  this.query=options.search||'';this.yaw=.12;this.pitch=.18;this.scale=1;this.drag=null;this.points=[];
  this.abort=new AbortController();const opts={signal:this.abort.signal};
  canvas.addEventListener('pointerdown',e=>{this.drag={x:e.clientX,y:e.clientY,originX:e.clientX,originY:e.clientY,moved:false};canvas.setPointerCapture(e.pointerId);},opts);
  canvas.addEventListener('pointermove',e=>{if(this.drag){const dx=e.clientX-this.drag.x,dy=e.clientY-this.drag.y;if(Math.hypot(e.clientX-this.drag.originX,e.clientY-this.drag.originY)>5)this.drag.moved=true;if(this.mode==='3d'){this.yaw+=dx*.006;this.pitch=Math.max(-1,Math.min(1,this.pitch+dy*.006));this.draw();}this.drag.x=e.clientX;this.drag.y=e.clientY;}else{canvas.style.cursor=this.hit(e)?'pointer':'grab';}},opts);
  canvas.addEventListener('pointerup',e=>{if(this.drag&&!this.drag.moved){const p=this.hit(e);if(p)this.options.onSelect?.(p.node.id);}this.drag=null;},opts);
  canvas.addEventListener('pointercancel',()=>{this.drag=null;},opts);
  canvas.addEventListener('wheel',e=>{e.preventDefault();this.zoom(e.deltaY>0?.92:1.08);},{...opts,passive:false});
  canvas.addEventListener('keydown',e=>{if(e.key==='+'||e.key==='='){this.zoom(1.15);e.preventDefault();}if(e.key==='-'){this.zoom(.85);e.preventDefault();}if(e.key==='0'){this.fit();e.preventDefault();}if(e.key.startsWith('Arrow')){this.yaw+=e.key==='ArrowLeft'?-.12:e.key==='ArrowRight'?.12:0;this.pitch+=e.key==='ArrowUp'?-.08:e.key==='ArrowDown'?.08:0;this.draw();e.preventDefault();}},opts);
  this.observer=new ResizeObserver(()=>this.resize());this.observer.observe(canvas);this.resize();
 }
 resize(){const rect=this.canvas.getBoundingClientRect();this.w=rect.width;this.h=rect.height;const dpr=Math.min(window.devicePixelRatio||1,2);this.canvas.width=Math.round(this.w*dpr);this.canvas.height=Math.round(this.h*dpr);this.ctx.setTransform(dpr,0,0,dpr,0,0);this.draw();}
 project(node){let [x,y,z]=node.pos;if(this.mode==='3d'){const nx=x*Math.cos(this.yaw)+z*Math.sin(this.yaw),nz=-x*Math.sin(this.yaw)+z*Math.cos(this.yaw);x=nx;z=nz;const ny=y*Math.cos(this.pitch)-z*Math.sin(this.pitch);z=y*Math.sin(this.pitch)+z*Math.cos(this.pitch);y=ny;}else z=0;const f=650/(650+z);const fit=Math.min((this.w-80)/540,(this.h-190)/390);return {node,x:this.w/2+(x+15)*fit*f*this.scale,y:this.h/2-10+y*fit*f*this.scale,z,r:(node.id==='concept'?13:node.group==='rule'||node.group==='exception'?8:6)*Math.max(.8,fit)*f*Math.sqrt(this.scale)};}
 hit(event){const r=this.canvas.getBoundingClientRect(),x=event.clientX-r.left,y=event.clientY-r.top;return [...this.points].reverse().find(p=>Math.hypot(p.x-x,p.y-y)<p.r+12);}
 draw(){
  if(!this.ctx||!this.w)return;
  const ctx=this.ctx;ctx.clearRect(0,0,this.w,this.h);
  // A subdued spatial grid keeps orientation readable while rotating.
  ctx.fillStyle='#1e3547';for(let x=20;x<this.w;x+=30)for(let y=65;y<this.h-110;y+=30){ctx.beginPath();ctx.arc(x,y,.7,0,Math.PI*2);ctx.fill();}
  this.points=this.data.nodes.filter(n=>!this.off.has(n.group)).map(n=>this.project(n)).sort((a,b)=>b.z-a.z);
  const byId=Object.fromEntries(this.points.map(p=>[p.node.id,p]));
  const links=this.data.links.filter(l=>byId[l[0]]&&byId[l[1]]);
  const neighbors=new Set(this.data.links.filter(l=>l[0]===this.selected||l[1]===this.selected).flatMap(l=>[l[0],l[1]]));
  for(const [a,b,label] of links){const p=byId[a],q=byId[b],active=a===this.selected||b===this.selected,color=this.groups[q.node.group].color;const dx=q.x-p.x,dy=q.y-p.y,dist=Math.hypot(dx,dy);if(dist<1)continue;const ux=dx/dist,uy=dy/dist,tx=q.x-ux*(q.r+5),ty=q.y-uy*(q.r+5);
   ctx.globalAlpha=active?.6:.22;ctx.strokeStyle=active?color:'#7e9eaf';ctx.lineWidth=active?1.3:.8;ctx.beginPath();ctx.moveTo(p.x+ux*p.r,p.y+uy*p.r);ctx.lineTo(tx,ty);ctx.stroke();ctx.beginPath();ctx.moveTo(tx,ty);ctx.lineTo(tx-ux*6+uy*3,ty-uy*6-ux*3);ctx.lineTo(tx-ux*6-uy*3,ty-uy*6+ux*3);ctx.closePath();ctx.fillStyle=color;ctx.fill();
   if(active&&this.w>450){ctx.globalAlpha=.75;ctx.font='9px "Malgun Gothic",sans-serif';ctx.textAlign='center';ctx.fillStyle='#91aebb';const mx=(p.x+q.x)/2,my=(p.y+q.y)/2;ctx.fillText(label,mx,my-6);}
  }
  for(const p of this.points){const n=p.node,g=this.groups[n.group],selected=n.id===this.selected,matches=!this.query||n.label.toLowerCase().includes(this.query.toLowerCase()),near=neighbors.has(n.id);
   ctx.globalAlpha=matches?(selected||near?1:.75):.2;
   if(selected){const gradient=ctx.createRadialGradient(p.x,p.y,2,p.x,p.y,48);gradient.addColorStop(0,g.color+'28');gradient.addColorStop(1,g.color+'00');ctx.fillStyle=gradient;ctx.beginPath();ctx.arc(p.x,p.y,48,0,Math.PI*2);ctx.fill();}
   if(selected||n.group==='rule'||n.group==='exception'){ctx.beginPath();ctx.arc(p.x,p.y,p.r+5,0,Math.PI*2);ctx.strokeStyle=g.color;ctx.lineWidth=selected?1.4:.6;ctx.stroke();}
   const grad=ctx.createRadialGradient(p.x-p.r*.4,p.y-p.r*.4,1,p.x,p.y,p.r);grad.addColorStop(0,g.color);grad.addColorStop(1,g.color+'66');ctx.fillStyle=grad;ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,Math.PI*2);ctx.fill();
   ctx.font=`${selected?'600 ':''}${this.w<450?10:11}px "Malgun Gothic","Apple SD Gothic Neo",sans-serif`;ctx.textAlign='center';const label=n.label.length>17?n.label.slice(0,16)+'…':n.label,width=ctx.measureText(label).width;ctx.fillStyle='#111e2bdd';ctx.fillRect(p.x-width/2-5,p.y+p.r+8,width+10,17);ctx.fillStyle=selected?'#ecfcff':g.color;ctx.fillText(label,p.x,p.y+p.r+20);
  }
  ctx.globalAlpha=1;this.options.onCount?.(this.points.length,links.length);
  if(!this.points.length){ctx.textAlign='center';ctx.fillStyle='#93acba';ctx.font='12px sans-serif';ctx.fillText('유형 필터를 켜면 연결을 볼 수 있습니다.',this.w/2,this.h/2);}
 }
 select(id){this.selected=id;this.draw();}
 setFilter(off){this.off=new Set(off);this.draw();}
 setMode(mode){this.mode=mode;this.draw();}
 search(query){this.query=query;this.draw();}
 zoom(factor){this.scale=Math.min(2.4,Math.max(.5,this.scale*factor));this.draw();}
 fit(){this.scale=1;this.yaw=.12;this.pitch=.18;this.draw();}
 destroy(){this.abort.abort();this.observer.disconnect();}
}

</script>
<script>
'use strict';
// Views follow the shape of the knowledge: records, documents, and typed relations.
function knowledgeSwitch(active){return `<div class="knowledge-switch" aria-label="지식 보기 방식">${[['shortcut','route','테이블','Shortcut Registry'],['wiki','book','문서','Legal Wiki'],['ontology','network','관계도','Ontology']].map(([id,i,label,en])=>`<a href="#${id}" class="${active===id?'active':''}">${icon(i,16)}<span>${label}</span><small>${en}</small></a>`).join('')}</div>`;}
function filteredShortcuts(){let rows=state.shortcuts.map((x,index)=>({...x,index}));const q=view.shortcutSearch.trim().toLowerCase();if(q)rows=rows.filter(x=>[x.id,x.title,x.question,x.scope,x.business].join(' ').toLowerCase().includes(q));if(view.shortcutStatus!=='all')rows=rows.filter(x=>view.shortcutStatus==='pending'?['승인 대기','보류'].includes(x.status):x.status===view.shortcutStatus);if(view.shortcutBusiness!=='all')rows=rows.filter(x=>x.business===view.shortcutBusiness);return rows.sort((a,b)=>view.shortcutSort==='uses'?b.uses-a.uses:view.shortcutSort==='title'?a.title.localeCompare(b.title,'ko'):b.created.localeCompare(a.created));}
function renderShortcuts(){const pending=state.shortcuts.filter(x=>['승인 대기','보류'].includes(x.status)).length,approved=state.shortcuts.filter(x=>x.status==='승인됨').length;
 return heading('KNOWLEDGE / 01','Shortcut Registry','질문에서 쌓인 조사 경로를, 재사용 가능한 레코드로.',`${badge('예시 데이터','gray')}${button(icon('file',14)+' CSV 내보내기','shortcut-export')}`)+knowledgeSwitch('shortcut')+
 `<section class="registry-hero"><div class="registry-symbol">${icon('route',31)}</div><div><span class="eyebrow">THE REUSABLE PATH</span><h2>좋은 조사 경로가 다음 질문의 출발점이 됩니다.</h2><p>적용 조건과 읽은 근거를 확인한 뒤, 재사용할 경로를 승인하세요.</p></div><div class="registry-stats"><div><strong>${state.shortcuts.length}</strong><span>전체 레코드</span></div><div><strong>${pending}</strong><span>검토 대기</span></div><div><strong>${approved}</strong><span>승인됨</span></div></div></section>
 <section class="panel registry-panel"><div class="registry-toolbar"><div class="status-tabs" role="group" aria-label="숏컷 상태 필터">${[['all','전체',state.shortcuts.length],['pending','검토 대기',pending],['승인됨','승인됨',approved],['반려','반려',state.shortcuts.filter(x=>x.status==='반려').length]].map(([id,label,n])=>`<button data-action="shortcut-filter" data-value="${id}" class="${view.shortcutStatus===id?'active':''}" aria-pressed="${view.shortcutStatus===id}">${label}<span>${n}</span></button>`).join('')}</div><div class="registry-filters"><label class="search-field">${icon('search',15)}<input id="shortcut-search" placeholder="질문, ID, 적용 조건 검색" value="${esc(view.shortcutSearch)}" aria-label="숏컷 검색"></label><select id="shortcut-business" aria-label="숏컷 업무 필터">${[['all','모든 업무'],['PF','PF'],['공통','공통'],['RP','RP']].map(([id,label])=>`<option value="${id}" ${view.shortcutBusiness===id?'selected':''}>${label}</option>`).join('')}</select><select id="shortcut-sort" aria-label="숏컷 정렬">${[['latest','최근 적재순'],['uses','재사용 많은 순'],['title','이름순']].map(([id,label])=>`<option value="${id}" ${view.shortcutSort===id?'selected':''}>${label}</option>`).join('')}</select></div></div>
 <div id="shortcut-records">${shortcutTable()}</div></section>
 <div class="registry-note"><span>${icon('layers',14)} 질문 · 적용 조건 · 근거 경로 · 실행 기록을 하나의 행으로 관리합니다.</span><span>레코드 선택 → 상세 검토 → 승인</span></div>
 ${view.shortcutDetail?`<dialog id="shortcut-detail" class="record-drawer" aria-labelledby="record-drawer-title"><div class="drawer-top"><div><span class="eyebrow">RECORD INSPECTOR</span><h2 id="record-drawer-title">숏컷 상세 검토</h2></div><button class="icon-btn" data-action="shortcut-close" aria-label="숏컷 상세 닫기">×</button></div>${renderReview('shortcut')}</dialog>`:''}`;
}
function shortcutTable(){const rows=filteredShortcuts();return `<div class="table-wrap"><table class="shortcut-table"><thead><tr><th>레코드 / 질문</th><th>업무</th><th>적용 조건</th><th>근거 경로</th><th>재사용</th><th>검토 상태</th><th>최근 적재</th><th><span class="sr-only">상세</span></th></tr></thead><tbody>${rows.map(x=>`<tr data-action="shortcut-open" data-value="${x.index}" class="shortcut-row" tabindex="0" aria-label="${esc(x.title)} 상세 검토"><td><span class="record-id">${esc(x.id)}</span><strong>${esc(x.title)}</strong><span class="record-question">${esc(x.question)}</span></td><td><span class="tag ${x.business==='PF'?'blue':x.business==='RP'?'violet':''}">${esc(x.business)}</span></td><td><div class="condition-tags">${x.conditions.map(c=>`<span>${esc(c)}</span>`).join('')}</div></td><td><div class="evidence-count">${icon('file',13)} ${x.evidenceCount}개 근거</div><small>${esc(x.state)}</small></td><td><span class="usage-number">${x.uses}</span><small>회 · 예시</small></td><td>${badge(x.status)}${!x.eligible?'<small class="record-warning">근거 보완 필요</small>':''}</td><td><span class="record-date">${esc(x.created.slice(5).replace('-','.'))}</span><small>${esc(x.created.slice(0,4))}</small></td><td class="row-arrow">↗</td></tr>`).join('')||'<tr><td colspan="8"><div class="empty-search">일치하는 레코드가 없습니다.<br><button class="btn text" data-action="shortcut-reset">필터 초기화</button></div></td></tr>'}</tbody></table></div><div class="registry-table-foot"><span><b>${rows.length}</b>개 표시 / 전체 ${state.shortcuts.length}개</span><span>모든 행은 디자인 예시입니다.</span></div>`;}
function openShortcut(index){selection.shortcut=index;view.shortcutDetail=true;render();}
function closeShortcut(){view.shortcutDetail=false;$('#shortcut-detail')?.close();render();$('.shortcut-row')?.focus({preventScroll:true});}
function exportShortcuts(){const fields=[['id','숏컷 ID'],['title','이름'],['question','질문'],['business','업무'],['scope','적용 범위'],['reads','근거'],['status','상태']];const cell=x=>'"'+String(x??'').replace(/^[=+@-]/,"'$&").replace(/"/g,'""')+'"';const csv='\ufeff'+[fields.map(f=>cell(f[1])).join(','),...filteredShortcuts().map(x=>fields.map(([k])=>cell(x[k])).join(','))].join('\r\n');const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='shortcut-demo-records.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('현재 필터의 예시 레코드를 내보냈습니다.');}
function wikiVisible(){const q=view.wikiSearch.trim().toLowerCase();return state.wikis.map((x,index)=>({...x,index})).filter(x=>!q||[x.title,x.scope,x.body].join(' ').toLowerCase().includes(q));}
function wikiLibrary(){const all=wikiVisible();return `<div class="library-label">LIBRARY <span>${state.wikis.length} PAGES</span></div><label class="search-field wiki-search">${icon('search',14)}<input id="wiki-search" value="${esc(view.wikiSearch)}" placeholder="지식 문서 검색" aria-label="위키 문서 검색"></label><div id="wiki-library-items">${wikiLibraryItems(all)}</div><div class="library-footer"><span class="library-spark">✧</span><b>LLM이 정리하고,<br>사람이 검토하는 지식.</b><p>초안 → 근거 확인 → 검토 → 게시</p><small>화면의 문서는 예시입니다.</small></div>`;}
function wikiLibraryItems(items=wikiVisible()){return ['업무별 가이드','공통 검토 원칙'].map(group=>{const rows=items.filter(x=>(x.scope.includes('PF')||x.scope.includes('RP')?'업무별 가이드':'공통 검토 원칙')===group);return rows.length?`<div class="library-group"><h3>${group}<span>${rows.length}</span></h3>${rows.map(x=>`<button class="library-page ${selection.wiki===x.index?'active':''}" data-action="select" data-kind="wiki" data-value="${x.index}">${icon('file',14)}<span>${esc(x.title)}</span><i class="page-status ${x.status==='게시됨'?'published':x.status==='상충 확인'?'conflict':'draft'}" title="${esc(x.status)}"></i></button>`).join('')}</div>`:'';}).join('')||'<p class="subtext empty-search">검색한 문서가 없습니다.</p>';}
function inlineWiki(text){return esc(text).replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>').replace(/\[\[(.+?)\]\]/g,(_,title)=>{const index=state.wikis.findIndex(x=>esc(x.title)===title);return index>=0?`<button class="wiki-inline-link" data-action="select" data-kind="wiki" data-value="${index}">${title} ↗</button>`:title;});}
function wikiDocument(body){let section=0,inList=false,out='';for(const line of body.split('\n')){if(!/^\d+\. |^- /.test(line)&&inList){out+='</ol>';inList=false;}if(/^#{2,3} /.test(line))out+=`<h3 id="wiki-section-${section++}">${esc(line.replace(/^#{2,3} /,''))}</h3>`;else if(/^\d+\. |^- /.test(line)){if(!inList){out+='<ol>';inList=true;}out+=`<li>${inlineWiki(line.replace(/^\d+\. |^- /,''))}</li>`;}else if(/^> /.test(line))out+=`<blockquote>${inlineWiki(line.slice(2))}</blockquote>`;else if(line.trim())out+=`<p>${inlineWiki(line)}</p>`;}return out+(inList?'</ol>':'');}
function renderWiki(){const x=state.wikis[selection.wiki],draft=x.draft||x,reading=x.revision===0&&x.draft?x.draft:x,sections=reading.body.split('\n').filter(l=>/^#{2,3} /.test(l)),hasSource=!x.source.includes('미확보')&&!x.source.includes('재확인')&&!x.source.includes('연결 전'),linked=state.ontologies.some(o=>o.wiki===x.id);let content='';
 if(view.wiki==='read')content=`<div class="wiki-abstract"><span>✧</span><div><b>문서 한눈에 보기</b><p>${esc(x.summary||'적용 범위와 필요한 근거를 확인하고, 확보하지 못한 정보는 미확인으로 남깁니다.')}</p></div></div><article class="wiki-prose">${wikiDocument(reading.body)}</article><section id="wiki-sources" class="wiki-sources"><div class="spread"><h3>근거와 연결 문서</h3><span>${hasSource?'1개 원문 연결':'근거 확인 필요'}</span></div><div class="citation-card"><span class="citation-index">01</span><div><b>${esc(x.source)}</b><p>${hasSource?'디자인용 예시 문서 · 실제 운영 원문과 연결 전':'확보하지 못한 근거는 문서에 연결하지 않습니다.'}</p></div>${icon('file',17)}</div><div class="related-pages">${state.wikis.filter(w=>w.id!==x.id).slice(0,2).map(w=>button(icon('book',13)+' '+esc(w.title),'select','small',`data-kind="wiki" data-value="${state.wikis.indexOf(w)}"`)).join('')}</div></section>`;
 if(view.wiki==='edit')content=`<div class="wiki-editor-note">${icon('file',16)} ${x.revision?'게시본 v'+x.revision+'을 보존하고 별도 초안을 편집합니다.':'새 문서의 초안을 작성합니다. 검토 후 게시할 수 있습니다.'}</div><div class="form-group"><label class="field-label" for="wiki-title">문서 제목</label><input id="wiki-title" type="text" value="${esc(draft.title)}" placeholder="지식의 주제가 드러나는 제목"></div><div class="form-group"><label class="field-label" for="wiki-scope">적용 범위</label><input id="wiki-scope" type="text" value="${esc(draft.scope)}"></div><div class="form-group"><div class="spread"><label class="field-label" for="wiki-body">문서 본문</label><span class="subtext">Markdown · [[문서 제목]]으로 연결</span></div><textarea class="markdown-editor" id="wiki-body" rows="14">${esc(draft.body)}</textarea></div><div class="form-group"><label class="field-label" for="wiki-reason">변경 사유</label><input id="wiki-reason" type="text" placeholder="확인한 근거와 바꾼 내용을 적어주세요."></div><div class="row">${button('초안 저장','wiki-save','primary')}${button('검토 요청','wiki-request')}${button('미리보기','wiki-preview')}</div><p class="error-text" id="wiki-error" role="alert"></p><div id="wiki-edit-preview" class="wiki-prose"></div>`;
 if(view.wiki==='refs')content=`<div class="section-caption">SOURCE CONNECTIONS</div><h3>이 지식의 근거</h3><div class="citation-card"><span class="citation-index">01</span><div><b>${esc(x.source)}</b><p>${hasSource?'문서 판본 v1 · 디자인 예시':'원문 연결 재확인 전'}</p></div>${icon('file',17)}</div><h3 class="section-gap">적용 범위</h3><p class="wiki-scope-text">${esc(x.scope)}</p>${linked?button('연결된 온톨로지에서 확인 →','wiki-ontology','primary'):'<p class="subtext">이 문서에 연결된 온톨로지 예시는 없습니다.</p>'}`;
 if(view.wiki==='history')content=`<div class="section-caption">REVISION HISTORY</div><h3>초안과 게시본의 변경 이력</h3>${x.draft?`<div class="wiki-version"><span class="version-dot"></span><div><b>${x.reviewRequested?'검토 요청된 초안':'편집 중인 초안'}</b><p>${esc(x.draft.reason)}</p><small>작성자 · 디자인 검토자</small></div>${badge(x.reviewRequested?'검토 필요':'초안')}</div>`:''}<div class="wiki-version"><span class="version-dot published"></span><div><b>${x.revision?'게시본 v'+x.revision:'최초 초안'}</b><p>예시 데이터에 포함된 기준 문서</p><small>실제 게시 이력과 연결 전</small></div>${badge(x.revision?'게시됨':'초안')}</div>`;
 return heading('KNOWLEDGE / 02','Legal Wiki','흩어진 근거를 읽을 수 있는 지식으로 연결합니다.',button('+ 새 문서','wiki-new','primary'))+knowledgeSwitch('wiki')+`<div class="wiki-workspace"><aside class="wiki-library" aria-label="위키 문서 목록">${wikiLibrary()}</aside><div class="wiki-document-column"><div class="wiki-doc-toolbar"><span>${icon('book',14)} ${esc(x.scope)} <i>/</i> ${esc(x.id)}</span><div class="wiki-doc-tabs">${[['read','문서 보기'],['edit','편집'],['refs','근거'],['history','이력']].map(([k,l])=>`<button data-action="wiki-tab" data-value="${k}" class="${view.wiki===k?'active':''}">${l}</button>`).join('')}</div></div><section class="wiki-paper"><div class="wiki-cover-line"></div><header class="wiki-title-block"><div class="wiki-document-icon">${icon('book',28)}</div><div class="row">${badge(x.status)}<span class="ai-origin">✧ LLM 정리 흐름 · 예시</span>${x.draft?badge('수정 초안 있음','blue'):''}</div><h2>${esc(reading.title||'새 지식 문서')}</h2><p>${esc(x.description||'검토 목적, 확인 순서와 필요한 근거를 정리한 지식 문서입니다.')}</p><div class="wiki-properties"><div><span>버전</span><b>${x.revision?'v'+x.revision:'초안'}</b></div><div><span>적용 범위</span><b>${esc(x.scope||'작성 중')}</b></div><div><span>연결 원문</span><b>${hasSource?'1개':'확인 필요'}</b></div><div><span>작성·검토</span><b>디자인 검토자</b></div></div></header><div class="wiki-content">${content}</div><div class="wiki-page-footer"><span>${icon('book',14)} LEGAL KNOWLEDGE</span><span>원문과 해석 지식을 구분합니다.</span></div></section></div><aside class="wiki-context"><span class="section-caption">ON THIS PAGE</span>${view.wiki==='read'?`<div class="wiki-toc">${sections.map((t,i)=>`<button data-action="wiki-anchor" data-value="wiki-section-${i}">${esc(t.replace(/^#{2,3} /,''))}</button>`).join('')}<button data-action="wiki-anchor" data-value="wiki-sources">근거와 연결 문서</button></div>`:'<p class="subtext">변경된 초안은 게시본과 분리하여 보관합니다.</p>'}<div class="wiki-context-rule"></div><span class="section-caption">CONNECTED KNOWLEDGE</span><div class="connected-ontology">${icon('network',24)}<b>${linked?'온톨로지에 연결됨':'검토 중인 지식'}</b><p>${linked?'이 문서의 적용 조건과 예외를 관계도에서 확인하세요.':'근거와 적용 범위 확인 후 연결합니다.'}</p>${linked?button('관계도 열기 ↗','wiki-ontology','text'):badge('연결 전','gray')}</div></aside></div>`;
}
function newWiki(){const id='WK-DEMO-'+String(state.wikis.length+1).padStart(2,'0');state.wikis.push({id,title:'새 지식 문서',status:'초안',revision:0,scope:'공통',body:'### 검토 목적\n\n### 확인 순서\n\n### 적용 범위와 미확인\n',source:'원문 연결 전',summary:'검토 목적과 근거를 작성 중입니다.'});selection.wiki=state.wikis.length-1;view.wiki='edit';view.wikiSearch='';record('wiki',id,'문서 초안 등록','사용자가 새 문서 작성 시작');render();$('#wiki-title').focus();$('#wiki-title').select();}
function ontologyTree(){const d=graphData();return `<div class="model-tree-title"><span class="section-caption">MODEL EXPLORER</span><h3>모델 구성</h3><p>${d.nodes.length}개 개체 · ${d.links.length}개 관계</p></div>${Object.entries(GROUPS).map(([key,g])=>`<details class="model-class" open><summary><span class="legend-dot" style="--node-color:${g.color}"></span>${g.label}<small>${d.nodes.filter(n=>n.group===key).length}</small></summary><div>${d.nodes.filter(n=>n.group===key).map(n=>`<button data-action="node" data-value="${n.id}" class="${view.node===n.id?'active':''}"><span>↳</span>${esc(n.label)}</button>`).join('')}</div></details>`).join('')}<div class="model-tree-note">개체를 선택하면<br>속성과 연결 관계가 열립니다.</div>`;}
function updateNodeTree(){if(!$('.ontology-tree'))return;$$('.ontology-tree [data-action=node]').forEach(b=>b.classList.toggle('active',b.dataset.value===view.node));}
document.addEventListener('click',e=>{const b=e.target.closest('[data-action]');if(!b||b.disabled)return;const a=b.dataset.action,v=b.dataset.value;
 if(a==='shortcut-open')openShortcut(Number(v));if(a==='shortcut-close')closeShortcut();if(a==='shortcut-export')exportShortcuts();if(a==='shortcut-filter'){view.shortcutStatus=v;render();}if(a==='shortcut-reset'){view.shortcutSearch='';view.shortcutStatus='all';view.shortcutBusiness='all';render();}
 if(a==='wiki-new')newWiki();if(a==='wiki-anchor')document.getElementById(v)?.scrollIntoView({behavior:'smooth',block:'start'});if(a==='wiki-preview'){$('#wiki-edit-preview').innerHTML='<h3>초안 미리보기</h3>'+wikiDocument($('#wiki-body').value);$('#wiki-edit-preview').scrollIntoView({behavior:'smooth'});}
});
document.addEventListener('keydown',e=>{const row=e.target.closest('.shortcut-row');if(row&&(e.key==='Enter'||e.key===' ')){e.preventDefault();openShortcut(Number(row.dataset.value));}});
document.addEventListener('input',e=>{if(e.target.id==='shortcut-search'){view.shortcutSearch=e.target.value;$('#shortcut-records').innerHTML=shortcutTable();}if(e.target.id==='wiki-search'){view.wikiSearch=e.target.value;$('#wiki-library-items').innerHTML=wikiLibraryItems();}});
document.addEventListener('change',e=>{if(e.target.id==='shortcut-business'){view.shortcutBusiness=e.target.value;$('#shortcut-records').innerHTML=shortcutTable();}if(e.target.id==='shortcut-sort'){view.shortcutSort=e.target.value;$('#shortcut-records').innerHTML=shortcutTable();}});

</script>
<script>
'use strict';
const $ = (s,root=document)=>root.querySelector(s);
const $$ = (s,root=document)=>[...root.querySelectorAll(s)];
const esc = value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clone = x=>JSON.parse(JSON.stringify(x));
const NAV=[['pipeline','배치 모니터','activity'],['structure','구조화 누락 승인','file'],['shortcut','숏컷 승인','route'],['wiki','Legal Wiki','book'],['ontology','온톨로지 관리','network'],['simulation','시뮬레이션','play']];
const paths={activity:'M3 12h4l3-8 4 16 3-8h4',file:'M14 3H5v18h14V8l-5-5v5h5 M8 12h8M8 16h5',route:'M5 5h9a4 4 0 0 1 0 8H9a4 4 0 0 0 0 8h10 M17 18l3 3-3 3',book:'M12 5C8 2 4 3 2 4v16c4-2 7-1 10 1 3-2 6-3 10-1V4c-3-1-6-2-10 1v16',network:'M12 4v6m0 0-7 7m7-7 7 7M12 1v5M2 17h6v5H2zM16 17h6v5h-6zM9 8h6v5H9z',play:'M9 5v14l11-7-11-7Z',check:'M4 12l5 5L20 6',clock:'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M12 7v5l4 2',arrow:'M4 12h16m-6-6 6 6-6 6',search:'M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14m5 12 6 6',layers:'m12 3 10 5-10 5L2 8l10-5Zm-10 10 10 5 10-5M2 18l10 5 10-5'};
const icon=(name,size=17)=>`<svg class="icon" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name]||paths.file}"/></svg>`;
const tone=s=>['승인 대기','검토 대기','검토 필요','보류','초안','미확인','확인 필요'].includes(s)?'amber':['반려','불일치','상충 확인','부분 완료'].includes(s)?'red':['미연결','예시','제외'].includes(s)?'gray':'';
const badge=(s,t=tone(s))=>`<span class="badge ${t}">${esc(s)}</span>`;
const initial=()=>({structures:clone(DEMO.STRUCTURES),shortcuts:clone(DEMO.SHORTCUTS),wikis:clone(DEMO.WIKIS),ontologies:clone(DEMO.ONTOLOGIES),audit:[],result:null});
let state=initial(),storageAvailable=true;
try{const saved=JSON.parse(sessionStorage.getItem('knowledge-ops-v3')||'null');if(saved?.schema===3)state=saved.state;}catch(_){storageAvailable=false;}
for(const [key,fixtures] of [['shortcuts',DEMO.SHORTCUTS],['wikis',DEMO.WIKIS]]){for(const seed of fixtures){const old=state[key].find(x=>x.id===seed.id);if(!old)state[key].push(clone(seed));else for(const [k,v] of Object.entries(seed))if(old[k]===undefined)old[k]=clone(v);}}
let page='pipeline',selection={structure:0,shortcut:0,wiki:0,ontology:0,scenario:1},view={pipeline:'batch',wiki:'read',inspector:'detail',node:'concept',mode:'3d',off:new Set(),search:'',simCount:'6',shortcutSearch:'',shortcutStatus:'all',shortcutBusiness:'all',shortcutSort:'latest',shortcutDetail:false,wikiSearch:''},graph=null;
function save(){try{sessionStorage.setItem('knowledge-ops-v3',JSON.stringify({schema:3,state}));}catch(_){storageAvailable=false;toast('탭 저장 공간을 사용할 수 없어 새로고침하면 변경이 사라집니다.');}}
function record(kind,id,action,reason){state.audit.unshift({kind,id,action,reason,time:new Date().toLocaleTimeString('ko-KR',{hour12:false})});save();}
let toastTimer;
function toast(message){$('#toast').textContent=message;$('#toast').classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').classList.remove('show'),4300);}
function go(target){if(location.hash.slice(1)===target)render();else location.hash=target;document.body.classList.remove('menu-open');$('#menu-toggle').setAttribute('aria-expanded','false');}
function heading(kicker,title,description,actions=''){return `<div class="heading"><div><span class="eyebrow">${kicker}</span><h1>${title}</h1><p>${description}</p></div><div class="heading-actions">${actions}</div></div>`;}
const button=(label,action,cls='',extra='')=>`<button class="btn ${cls}" data-action="${action}" ${extra}>${label}</button>`;
const goto=(label,target,cls='')=>button(label,'goto',cls,`data-target="${target}"`);
function render(){
 graph?.destroy();graph=null;
 page=NAV.some(n=>n[0]===location.hash.slice(1))?location.hash.slice(1):'pipeline';
 const pending={structure:state.structures.filter(x=>['승인 대기','보류'].includes(x.status)).length,shortcut:state.shortcuts.filter(x=>['승인 대기','보류'].includes(x.status)).length};
 $('#nav').innerHTML=NAV.map(([id,label,i])=>`<a href="#${id}" class="nav-item ${page===id?'active':''}" ${page===id?'aria-current="page"':''}>${icon(i)}<span>${label}</span>${pending[id]!==undefined?`<span class="count">${pending[id]}</span>`:''}</a>`).join('');
 $('#crumb').textContent=NAV.find(n=>n[0]===page)[1];
 $('#main').dataset.page=page;
 $('#main').innerHTML=({pipeline:renderPipeline,structure:()=>renderReview('structure'),shortcut:renderShortcuts,wiki:renderWiki,ontology:renderOntology,simulation:renderSimulation})[page]();
 if(page==='ontology')mountGraph();
 if(page==='shortcut'&&view.shortcutDetail){const d=$('#shortcut-detail');d.showModal();d.addEventListener('cancel',()=>{view.shortcutDetail=false;});d.addEventListener('click',e=>{if(e.target===d)closeShortcut();});}
 document.title=`${NAV.find(n=>n[0]===page)[1]} · 법률 지식 운영실`;
}
function metric(label,value,unit,foot,i,attention=false){return `<div class="metric"><span class="metric-icon">${icon(i)}</span><div class="label">${label}</div><strong>${value}<small>${unit}</small></strong><div class="foot ${attention?'attention':''}">${foot}</div></div>`;}
function renderPipeline(){
 const p=state.structures.filter(x=>['승인 대기','보류'].includes(x.status)).length,s=state.shortcuts.filter(x=>['승인 대기','보류'].includes(x.status)).length;
 return heading('OPERATIONS OVERVIEW','배치 모니터','자료가 들어오는 순간부터, 검토 가능한 지식이 되기까지 한눈에 확인합니다.',`${badge('예시 데이터','gray')}<span class="btn">${icon('clock',14)} 2026. 10. 21</span>`)+
 `<div class="metrics">${metric('배치 확인 필요','1','건','구조화 단계에 검토 항목이 있습니다.','activity',true)}${metric('구조화 승인 대기',p,'건','원문을 보고 누락 내용을 확인하세요.','file')}${metric('숏컷 승인 대기',s,'건','재사용할 조사 경로를 검토하세요.','route')}${metric('지식 검토 항목','4','건','위키 2 · 온톨로지 2','network')}</div>
 <div class="two-col"><div class="stack"><section class="panel"><div class="panel-header"><div><h2>오늘의 배치 흐름</h2><p>DAILY-1021 · 외규 정기 수집 · 실행 기록 예시</p></div>${badge('확인 필요')}</div>
 <div class="flow">${[['중계서버','24','신규·갱신 자료 수신','수신 완료'],['Dataiku','24','수집·변경분 분류','처리 완료'],['구조화','21','누락 검토 3건','검토 필요'],['색인','21','확정된 문서 색인','처리 완료'],['Oracle','21','지식 데이터 반영','적재 완료']].map((x,i)=>`<div class="flow-node ${i===2?'warn':''}"><div class="flow-index">0${i+1}<span>${i===2?'◷':'✓'}</span></div><b>${x[0]}</b><strong>${x[1]}</strong><small>${x[2]}<br>${x[3]}</small></div>`).join('')}</div><div class="panel-bottom"><span>배치 기록은 실행 시점의 예시입니다. 승인 체험과 별도로 유지됩니다.</span>${goto('누락 항목 확인 →','structure','text')}</div></section>
 <section class="panel"><div class="tabs">${[['batch','배치 실행 기록'],['connection','연결 상태'],['audit','검토 이력']].map(([id,label])=>`<button class="tab ${view.pipeline===id?'active':''}" data-action="pipeline-tab" data-value="${id}">${label}${id==='audit'&&state.audit.length?' · '+state.audit.length:''}</button>`).join('')}</div>${pipelineTab()}</section>
 <div class="callout blue">${icon('layers',15)} <span>흐름을 확인한 뒤 원문 누락 → 숏컷 → 위키 → 온톨로지 순으로 검토하고, 시뮬레이션에서 다시 확인합니다.</span></div></div>
 <div class="stack"><section class="panel"><div class="panel-header"><h3>지금 확인할 일</h3>${badge(p+s+4+'건','gray')}</div>${[['structure','원문 누락 확인','구조화에서 놓친 내용 검토',p,'file'],['shortcut','조사 경로 승인','완료·부분 완료를 구분해 검토',s,'route'],['wiki','위키 변경 검토','출처와 적용 범위 확인',2,'book'],['ontology','온톨로지 조건 검토','적용·제외·재개 조건 확인',2,'network']].map(x=>`<button class="inbox-row" data-action="goto" data-target="${x[0]}"><span class="inbox-symbol">${icon(x[4],15)}</span><span><b>${x[1]}</b><small>${x[2]}</small></span><span class="number">${x[3]}</span></button>`).join('')}</section>
 <div class="next-step"><span class="eyebrow">KNOWLEDGE EXPLORER</span><h3>지식의 연결을<br>직접 살펴보세요.</h3><p>개념·확인 항목·근거·예외를 3D 관계도로 탐색하고 수정할 수 있습니다.</p>${goto('온톨로지 탐색 '+icon('arrow',13),'ontology')}</div></div></div>`;
}
function pipelineTab(){
 if(view.pipeline==='connection')return `<div class="panel-pad"><div class="callout blue">이 공유 화면은 디자인 체험용입니다. 아래 운영 시스템에는 연결하지 않았습니다.</div>${['API 중계서버','Dataiku 배치','Oracle 지식 저장소','RAG 실행'].map(x=>`<div class="inbox-row"><span>${x}</span><span style="margin-left:auto">${badge('미연결')}</span></div>`).join('')}</div>`;
 if(view.pipeline==='audit')return state.audit.length?`<div class="table-wrap"><table><thead><tr><th>시각</th><th>검토 항목</th><th>작업</th><th>사유</th></tr></thead><tbody>${state.audit.map(x=>`<tr><td>${esc(x.time)}</td><td>${esc(x.id)}</td><td>${esc(x.action)}</td><td>${esc(x.reason)}</td></tr>`).join('')}</tbody></table></div>`:`<div class="audit-empty">아직 이 탭에서 검토한 항목이 없습니다.</div>`;
 return `<div class="table-wrap"><table><thead><tr><th>배치 실행</th><th>구분</th><th>문서</th><th>처리 상태</th><th>실행 시각</th></tr></thead><tbody><tr><td><b>외규 정기 수집</b><small class="mono">DAILY-1021</small></td><td>정기 배치</td><td>24건</td><td>${badge('확인 필요')}</td><td>10.21 02:00</td></tr><tr><td><b>내규 업로드 반영</b><small class="mono">PORTAL-1020</small></td><td>수시 수집</td><td>8건</td><td>${badge('완료')}</td><td>10.20 16:35</td></tr><tr><td><b>외규 정기 수집</b><small class="mono">DAILY-1020</small></td><td>정기 배치</td><td>12건</td><td>${badge('완료')}</td><td>10.20 02:00</td></tr></tbody></table></div>`;
}
function queue(items,type){return `<section class="panel"><div class="queue-head"><div class="spread"><h3>검토 목록</h3>${badge(items.length+'건','gray')}</div><div class="subtext" style="margin-top:9px">항목을 선택해 내용을 확인하세요.</div></div><div class="queue">${items.map((x,i)=>`<button class="queue-item ${selection[type]===i?'active':''}" data-action="select" data-kind="${type}" data-value="${i}"><div class="spread"><span class="mono muted">${esc(x.id)}</span>${badge(x.status)}</div><b>${esc(x.title)}</b><small>${esc(x.document||x.scope||x.business)}<br>${esc(x.location||x.run||'예시 지식 · 검토용')}</small></button>`).join('')}</div></section>`;}
function renderReview(kind){
 const structures=kind==='structure',items=structures?state.structures:state.shortcuts,x=items[selection[kind]],terminal=['승인됨','반려'].includes(x.status);
 let body=structures?`<div class="source-grid"><div><div class="source-title">원문 <span>예시 문서 · v1</span></div><div class="source">${esc(x.source)}</div></div><div><div class="source-title">현재 구조화 결과 <span>변경 전</span></div><div class="source">${esc(x.before)}</div></div></div><div class="section-gap"><h3>보완 제안</h3><div class="addition">${esc(x.fix)}</div><p class="subtext">${esc(x.impact)} 원문은 그대로 보존합니다.</p></div>`:
 `<h3>원래 질문과 조사 경로</h3><p class="subtext" style="margin-top:10px">${esc(x.question)}</p><div class="route-path">${x.path.map((t,i)=>`${i?'<i>→</i>':''}<span>${esc(t)}</span>`).join('')}</div><div class="reference"><b>읽은 근거</b>${esc(x.reads)}<br>실행 기록 ${esc(x.run)} · ${esc(x.state)}</div><div class="source-grid"><div><div class="source-title">재사용 범위</div><div class="source" style="min-height:70px">${esc(x.scope)}</div></div><div><div class="source-title">원래 실행 상태</div><div class="source" style="min-height:70px">${badge(x.state)}<br>${x.eligible?'근거 경로를 재사용할 수 있는 예시입니다.':'미확보 근거가 있어 승인할 수 없습니다.'}</div></div></div><div class="callout section-gap">과거 답변을 정답으로 승인하지 않습니다. 검증된 탐색 경로와 적용 조건을 검토합니다.</div>`;
 const detail=`<section class="panel"><div class="detail-top"><div class="spread"><span class="mono muted">${x.id} · ${structures?'STRUCTURE':'SHORTCUT'}</span>${badge(x.status)}</div><h2>${esc(x.title)}</h2><p class="subtext">${esc(structures?x.document+' / '+x.location:x.run+' / '+x.scope)}</p></div><div class="detail-body">${body}${terminal?`<div class="callout blue section-gap">${esc(x.status)} · 검토 사유: ${esc(x.reason)}<br>이 탭의 체험 기록에 저장했습니다. 실제 운영에는 반영되지 않습니다.</div>`:`<div class="form-group"><label class="field-label" for="review-reason">검토 사유</label><textarea id="review-reason" rows="2" placeholder="확인한 내용과 승인·보류·반려 이유를 남겨주세요."></textarea></div><label class="checkbox-label"><input type="checkbox" id="review-check">${structures?'원문의 위치·버전과 보완 내용을 확인했습니다.':'근거와 재사용 범위를 확인했습니다.'}</label><p id="review-error" class="error-text" role="alert"></p>`}</div><div class="actions"><span class="subtext">${terminal?'검토 완료 · 중복 승인은 기록하지 않습니다.':'승인 시 검토 사유와 확인 표시가 필요합니다.'}</span>${button('반려','review-reject','danger',terminal?'disabled':'')}${button('보류','review-hold','',terminal?'disabled':'')}${button('승인하기','review-approve','primary',terminal||(!structures&&!x.eligible)?'disabled':'')}</div></section>`;
 if(!structures)return detail;
 return heading(structures?'STRUCTURE REVIEW':'SHORTCUT REVIEW',structures?'구조화 누락 승인':'숏컷 승인',structures?'원문과 구조화 결과를 나란히 보고, 누락된 내용을 검토합니다.':'사용 중 쌓인 조사 경로를 확인하고, 재사용할 지식으로 검토합니다.',badge('체험 모드','gray'))+`<div class="review-layout">${queue(items,kind)}${detail}</div>`;
}
function review(action){const items=page==='structure'?state.structures:state.shortcuts,x=items[selection[page]];if(['승인됨','반려'].includes(x.status))return;const reason=$('#review-reason')?.value.trim();if(!reason){$('#review-error').textContent='검토 사유를 먼저 입력해주세요.';return;}if(action==='승인됨'&&(!$('#review-check')?.checked||(page==='shortcut'&&!x.eligible))){$('#review-error').textContent='원문·근거와 적용 범위 확인이 필요합니다.';return;}x.status=action;x.reason=reason;record(page,x.id,action,reason);render();toast(`${x.id} ${action} · 이 탭의 검토 이력에 저장했습니다.`);}
function saveWiki(request){const x=state.wikis[selection.wiki],title=$('#wiki-title').value.trim(),scope=$('#wiki-scope').value.trim(),body=$('#wiki-body').value.trim(),reason=$('#wiki-reason').value.trim();if(!title||!scope||!body||!reason){$('#wiki-error').textContent='제목·범위·본문·변경 사유를 모두 입력해주세요.';return;}x.draft={title,scope,body,reason};if(x.revision===0){x.title=title;x.scope=scope;}x.reviewRequested=request;record('wiki',x.id,request?'검토 요청':'초안 저장',reason);view.wiki='history';render();toast('초안을 저장했습니다. 게시본은 유지됩니다.');}
const GROUPS={concept:{label:'개념',color:'#50baa9'},check:{label:'확인 항목',color:'#72a9df'},rule:{label:'적용 조건',color:'#e1b86b'},exception:{label:'예외·재개',color:'#d9847c'},source:{label:'근거·위키',color:'#a99ada'}};
function graphData(){const o=state.ontologies[selection.ontology];return {nodes:[
 {id:'concept',group:'concept',label:o.title,pos:[0,0,0],note:'질문에 필요한 검토 항목을 연결하는 중심 개념입니다.'},
 {id:'business',group:'check',label:'업무 유형',pos:[-150,-90,55],note:'질문의 업무 유형이 적용 범위에 포함되는지 확인합니다.'},
 {id:'date',group:'check',label:'기준일 확인',pos:[-110,80,80],note:o.require_date?'기준일이 없으면 미확인 상태로 유지합니다.':'기준일 확인을 필수로 요구하지 않는 초안입니다.'},
 {id:'scope',group:'rule',label:'적용 범위',pos:[135,-80,30],note:`대상 업무: ${o.business}. 범위가 맞는 질문에만 검토 항목을 연결합니다.`},
 {id:'unknown',group:'rule',label:'미확인 처리',pos:[-30,145,-40],note:o.unknown+' · 부족한 정보를 추정해서 채우지 않습니다.'},
 {id:'exception',group:'exception',label:'제외 조건',pos:[210,55,0],note:o.exclude||'명시된 제외 조건에 해당하면 이유를 남기고 적용을 제외합니다.'},
 {id:'resume',group:'exception',label:'재개 기준',pos:[120,160,70],note:o.resume||'기준일 등 필요한 정보가 추가되면 기존 조사를 이어갑니다.'},
 {id:'wiki',group:'source',label:'검토 순서 Wiki',pos:[-175,-180,-50],note:'승인된 탐색 순서와 적용 범위를 연결합니다. 예시 위키 '+o.wiki},
 {id:'source',group:'source',label:'예시 지침 · 제4조',pos:[-250,10,-30],note:'예시 위험검토지침 제4조 · v1. 원문 위치와 버전을 확인합니다.'},
 {id:'evidence',group:'source',label:'원문 버전',pos:[-210,145,-70],note:'원문이 갱신되면 연결된 지식의 재확인이 필요합니다.'},
 {id:'output',group:'rule',label:'검토 항목 연결',pos:[135,-180,-70],note:'조건이 맞고 근거가 확보된 항목을 기존 조사 입력에 연결합니다.'},
 {id:'query',group:'concept',label:'검토 질문',pos:[0,-170,100],note:'업무·기준일·대상 자료를 질문에서 확인합니다.'}
 ],links:[['query','concept','질문 해석'],['concept','business','확인 필요'],['concept','date','확인 필요'],['concept','scope','적용 조건'],['scope','output','조건 충족'],['scope','exception','제외 검토'],['date','unknown','정보 누락'],['unknown','resume','정보 확보'],['exception','resume','조건 변경'],['wiki','concept','검토 순서'],['source','wiki','근거'],['source','date','확인 근거'],['evidence','source','버전 확인'],['concept','unknown','미확인 보존']]};}
function renderOntology(){const o=state.ontologies[selection.ontology];return heading('ONTOLOGY EXPLORER','온톨로지 관리','지식의 연결을 탐색하고, 적용·제외·재개 조건을 확인합니다.',`${badge('검토 대기')} ${button('이 버전으로 시뮬레이션 '+icon('arrow',13),'onto-sim','primary')}`)+knowledgeSwitch('ontology')+
 `<section class="panel ontology-panel"><div class="ontology-bar"><div class="row"><label class="sr-label" for="ontology-select" hidden>온톨로지 선택</label><select id="ontology-select" aria-label="온톨로지 선택">${state.ontologies.map((x,i)=>`<option value="${i}" ${selection.ontology===i?'selected':''}>${esc(x.title)} · v${x.revision}</option>`).join('')}</select>${badge('후보','gray')}</div><div class="legend">${Object.entries(GROUPS).map(([id,g])=>`<button data-action="filter-group" data-value="${id}" aria-pressed="${!view.off.has(id)}" class="${view.off.has(id)?'off':''}"><span class="legend-dot" style="--node-color:${g.color}"></span>${g.label}</button>`).join('')}</div></div>
 <div class="ontology-layout"><aside class="ontology-tree" aria-label="온톨로지 모델 구성">${ontologyTree()}</aside><div class="graph-area"><div class="graph-toolbar"><input id="graph-search" value="${esc(view.search)}" placeholder="노드 검색 · 기준일, 예외, 원문" aria-label="노드 검색"><div class="graph-toggle"><button data-action="graph-mode" data-value="2d" class="${view.mode==='2d'?'active':''}" aria-pressed="${view.mode==='2d'}">2D</button><button data-action="graph-mode" data-value="3d" class="${view.mode==='3d'?'active':''}" aria-pressed="${view.mode==='3d'}">3D</button></div></div><canvas id="graph" tabindex="0" aria-label="온톨로지 관계도. 드래그로 회전, 휠로 확대. 키보드 탐색은 아래 노드 버튼을 이용하세요."></canvas><div class="graph-caption"><b>연결을 따라가면, 판단의 조건이 보입니다.</b><span id="graph-help">${view.mode==='3d'?'드래그로 회전':'고정된 2D 보기'} · 휠로 확대 · 노드를 선택해 상세 보기</span></div><div class="graph-controls"><button data-action="zoom-in" aria-label="확대">+</button><button data-action="zoom-out" aria-label="축소">−</button><button data-action="graph-fit" aria-label="전체 보기">전체</button></div><div class="graph-meta"><span id="graph-count">12 nodes · 14 relationships</span><span>예시 관계도 <b>· 후보 v${o.revision}</b></span></div></div><aside class="inspector" aria-label="선택한 노드 상세" id="inspector">${inspector()}</aside></div><div class="node-list" id="node-list">${nodeList()}</div></section>
 <div class="graph-note"><span>참고한 인터랙션: 유형별 색상 · 그룹 필터 · 방향 관계 · 노드 상세</span><span>조건 수정 → 후보 버전 저장 → 시뮬레이션 재확인</span></div>`;}
function nodeList(){return '<span>노드 바로가기</span>'+graphData().nodes.filter(n=>!view.off.has(n.group)).map(n=>`<button data-action="node" data-value="${n.id}" class="${view.node===n.id?'active':''}" aria-pressed="${view.node===n.id}">${esc(n.label)}</button>`).join('');}
function inspector(){const d=graphData(),n=d.nodes.find(x=>x.id===view.node)||d.nodes[0],o=state.ontologies[selection.ontology],g=GROUPS[n.group];let body='';
 if(view.inspector==='detail')body=`<p>${esc(n.note)}</p><div class="reference"><b>적용 범위 · ${esc(o.business)}</b>후보 v${o.revision} · ${esc(o.id)}<br>출처 연결: ${esc(o.wiki)} / 예시 문서 v1</div><div class="source-title section-gap">연결된 지식</div>${d.links.filter(x=>x[0]===n.id||x[1]===n.id).map(l=>{const other=d.nodes.find(v=>v.id===(l[0]===n.id?l[1]:l[0]));return `<button class="relationship" data-action="node" data-value="${other.id}"><span class="arrow">${l[0]===n.id?'→':'←'}</span><span>${l[2]}<br><b>${esc(other.label)}</b></span><span style="margin-left:auto">›</span></button>`;}).join('')}`;
 if(view.inspector==='source')body=`<div class="source-title">근거 원문 · 예시 지침 v1</div><div class="source">① 기준일이 없는 자료는 기준일 확인 대상으로 남긴다.</div><div class="reference"><b>예시 위험검토지침</b>제4조 · 표2 · 각주①<br>디자인용 예시 원문입니다.</div>${button('연결 Wiki 열기 →','onto-wiki','text')}<p class="subtext">실제 서비스에서는 원문·권한·버전을 확인한 결과를 표시합니다.</p>`;
 if(view.inspector==='edit')body=`<p class="subtext">이 노드가 속한 검토 조건을 수정합니다.</p><div class="form-group"><label class="field-label" for="onto-business">대상 업무</label><select id="onto-business">${['PF','공통','RP'].map(x=>`<option ${o.business===x?'selected':''}>${x}</option>`).join('')}</select></div><label class="checkbox-label"><input id="onto-date" type="checkbox" ${o.require_date?'checked':''}>기준일 확인을 필수로 포함</label><div class="form-group"><label class="field-label" for="onto-unknown">정보가 부족한 경우</label><select id="onto-unknown">${['미확인 유지','추가 정보 요청'].map(x=>`<option ${o.unknown===x?'selected':''}>${x}</option>`).join('')}</select></div><div class="form-group"><label class="field-label" for="onto-exclude">제외 조건</label><textarea id="onto-exclude" rows="2">${esc(o.exclude||'명시된 제외 조건을 충족한 경우')}</textarea></div><div class="form-group"><label class="field-label" for="onto-resume">재개 기준</label><textarea id="onto-resume" rows="2">${esc(o.resume||'미확인 정보가 추가 확보된 경우')}</textarea></div><div class="form-group"><label class="field-label" for="onto-reason">변경 사유</label><input id="onto-reason" type="text" placeholder="수정 이유를 입력하세요."></div>${button('새 후보 버전 저장','onto-save','primary')}<p class="error-text" id="onto-error" role="alert"></p>`;
 return `<div class="inspector-head"><div class="spread"><span class="badge" style="background:${g.color}20;color:${g.color}">${g.label}</span>${badge('검토 대기')}</div><h3>${esc(n.label)}</h3><span class="mono">${o.id} / ${n.id}</span></div><div class="tabs">${[['detail','상세'],['source','근거'],['edit','조건 편집']].map(([id,l])=>`<button class="tab ${view.inspector===id?'active':''}" data-action="inspector-tab" data-value="${id}">${l}</button>`).join('')}</div><div class="inspector-body">${body}</div>${view.inspector!=='edit'?`<div class="inspector-actions">${button('조건 편집하기','inspector-tab','', 'data-value="edit"')}</div>`:''}`;
}
function selectNode(id){view.node=id;view.inspector='detail';$('#inspector').innerHTML=inspector();$('#node-list').innerHTML=nodeList();graph?.select(id);updateNodeTree();if(matchMedia('(max-width:1050px)').matches)$('#inspector').scrollIntoView({behavior:'smooth',block:'start'});}
function mountGraph(){graph=new KnowledgeGraph($('#graph'),graphData(),GROUPS,{mode:view.mode,off:view.off,selected:view.node,search:view.search,onSelect:selectNode,onCount:(n,l)=>{$('#graph-count').textContent=`${n} nodes · ${l} relationships`;}});}
function saveOntology(){const o=state.ontologies[selection.ontology],reason=$('#onto-reason').value.trim();if(!reason){$('#onto-error').textContent='변경 사유를 입력해주세요.';return;}o.business=$('#onto-business').value;o.require_date=$('#onto-date').checked;o.unknown=$('#onto-unknown').value;o.exclude=$('#onto-exclude').value.trim();o.resume=$('#onto-resume').value.trim();o.revision+=1;record('ontology',o.id,'후보 v'+o.revision+' 저장',reason);view.inspector='detail';render();toast(`후보 v${o.revision}을 저장했습니다. 이전 시뮬레이션은 재확인이 필요합니다.`);}
function renderSimulation(){const o=state.ontologies[selection.ontology],r=state.result,stale=r&&JSON.stringify(state.ontologies.find(x=>x.id===r.ontology.id))!==JSON.stringify(r.ontology),different=r&&(r.ontology.id!==o.id||r.count!==view.simCount);
 return heading('SIMULATION LAB','시뮬레이션','온톨로지 버전과 질문 묶음을 고정하고, 문제가 있는 조건으로 돌아갑니다.',badge('결과 화면 예시','gray'))+
 `<section class="panel"><div class="panel-header"><div><h2>검증할 버전과 시나리오</h2><p>실제 엔진 호출 없이 결과 확인 흐름을 체험합니다.</p></div>${icon('play',20)}</div><div class="sim-config"><div class="form-group"><label class="field-label" for="sim-ontology">온톨로지 후보</label><select id="sim-ontology">${state.ontologies.map((x,i)=>`<option value="${i}" ${selection.ontology===i?'selected':''}>${esc(x.title)} · v${x.revision}</option>`).join('')}</select></div><div class="form-group"><label class="field-label" for="sim-count">예시 질문 묶음</label><select id="sim-count"><option value="6" ${view.simCount==='6'?'selected':''}>기본·누락·예외·재개 · 6개</option><option value="3" ${view.simCount==='3'?'selected':''}>기본·누락·범위 · 3개</option></select></div>${button(icon('play',14)+' 결과 화면 미리보기','sim-run','primary')}</div>
 ${r?`${stale?'<div class="callout" style="margin:0 22px 16px">온톨로지가 수정되었습니다. 아래는 이전 버전의 기록이며 재확인이 필요합니다.</div>':''}${different?'<div class="callout blue" style="margin:0 22px 16px">현재 선택과 아래 기록의 대상이 다릅니다. 미리보기를 누르면 현재 선택으로 새 예시 기록을 만듭니다.</div>':''}${simulationResult(r)}`:`<div class="sim-placeholder"><div class="placeholder-icon">${icon('play',25)}</div><h3>검토한 지식을 질문에 대입해보세요.</h3><p class="subtext">정상·정보 누락·제외·재개 상황을 나란히 비교합니다.<br>실제 시뮬레이션 실행 기능은 연결 전입니다.</p></div>`}</section><div class="callout blue section-gap">이 화면의 일치·불일치는 고정된 예시입니다. 법률 정확도, 온톨로지 품질 또는 RAG 성능을 측정한 결과가 아닙니다.</div>`;
}
function simulationResult(r){const rows=DEMO.SCENARIOS.slice(0,Number(r.count)),c=rows[selection.scenario]||rows[0];return `<div class="panel-bottom"><span class="mono">${r.id} · ${esc(r.ontology.title)} · v${r.ontology.revision}</span>${badge('예시 기록','gray')}</div><div class="sim-summary">${[['일치','',rows.filter(x=>x.status==='일치').length],['불일치','red',rows.filter(x=>x.status==='불일치').length],['미확인','amber',rows.filter(x=>x.status==='미확인').length]].map(([label,t,n])=>`<div class="score"><strong style="color:${t==='red'?'var(--red)':t==='amber'?'var(--amber)':'var(--green)'}">${n}</strong><span>${label}</span></div>`).join('')}<span style="margin-left:auto">${rows.length}개 시나리오</span></div><div class="table-wrap"><table><thead><tr><th>시나리오</th><th>입력 조건</th><th>예상 처리</th><th>예시 결과</th><th>확인</th></tr></thead><tbody>${rows.map((x,i)=>`<tr class="clickable ${c.id===x.id?'selected':''}"><td><button class="btn text small" data-action="scenario" data-value="${i}">${x.case}</button></td><td>${x.input}</td><td>${x.expected}</td><td>${x.observed}</td><td>${badge(x.status)}</td></tr>`).join('')}</tbody></table></div><div class="sim-result-detail"><div class="spread"><h3>${c.case} · 연결 조건 확인</h3>${badge(c.status)}</div><div class="source-grid"><div><div class="source-title">예상한 처리</div><div class="source">${c.expected}</div></div><div><div class="source-title">예시에서 관찰된 처리</div><div class="source">${c.observed}</div></div></div><div class="spread section-gap"><span class="subtext">관련 조건: ${c.node} · 후보 v${r.ontology.revision}</span>${button('관련 조건으로 이동 →','sim-issue','primary')}</div></div>`;}
function runSimulation(){const o=state.ontologies[selection.ontology];state.result={id:'DEMO-SIM-'+String(state.audit.filter(x=>x.kind==='simulation').length+1).padStart(3,'0'),ontology:clone(o),count:view.simCount};selection.scenario=1;record('simulation',state.result.id,'결과 예시 생성',o.id+' v'+o.revision);render();toast('결과 화면 예시를 만들었습니다. 실제 엔진은 호출하지 않았습니다.');}
document.addEventListener('click',event=>{
 const b=event.target.closest('[data-action]');if(!b||b.disabled)return;
 const a=b.dataset.action,v=b.dataset.value;
 if(a==='goto')go(b.dataset.target);
 if(a==='pipeline-tab'){view.pipeline=v;render();}
 if(a==='select'){selection[b.dataset.kind]=Number(v);if(b.dataset.kind==='wiki')view.wiki='read';render();}
 if(a.startsWith('review-'))review({'review-approve':'승인됨','review-hold':'보류','review-reject':'반려'}[a]);
 if(a==='wiki-tab'){view.wiki=v;render();}
 if(a==='wiki-save'||a==='wiki-request')saveWiki(a==='wiki-request');
 if(a==='wiki-ontology'){const ix=state.ontologies.findIndex(o=>o.wiki===state.wikis[selection.wiki].id);if(ix<0){toast('이 위키에 연결된 온톨로지 예시가 없습니다.');return;}selection.ontology=ix;view.node='wiki';view.inspector='detail';go('ontology');}
 if(a==='onto-wiki'){selection.wiki=Math.max(0,state.wikis.findIndex(x=>x.id===state.ontologies[selection.ontology].wiki));view.wiki='read';go('wiki');}
 if(a==='node')selectNode(v);
 if(a==='inspector-tab'){view.inspector=v;$('#inspector').innerHTML=inspector();}
 if(a==='filter-group'){view.off.has(v)?view.off.delete(v):view.off.add(v);b.classList.toggle('off',view.off.has(v));b.setAttribute('aria-pressed',String(!view.off.has(v)));graph?.setFilter(view.off);$('#node-list').innerHTML=nodeList();}
 if(a==='graph-mode'){view.mode=v;graph?.setMode(v);$$('[data-action=graph-mode]').forEach(x=>{x.classList.toggle('active',x.dataset.value===v);x.setAttribute('aria-pressed',String(x.dataset.value===v));});$('#graph-help').textContent=(v==='3d'?'드래그로 회전':'고정된 2D 보기')+' · 휠로 확대 · 노드를 선택해 상세 보기';}
 if(a==='zoom-in')graph?.zoom(1.15);if(a==='zoom-out')graph?.zoom(.85);if(a==='graph-fit')graph?.fit();
 if(a==='onto-save')saveOntology();if(a==='onto-sim')go('simulation');
 if(a==='sim-run')runSimulation();if(a==='scenario'){selection.scenario=Number(v);render();}
 if(a==='sim-issue'){const c=DEMO.SCENARIOS[selection.scenario];selection.ontology=Math.max(0,state.ontologies.findIndex(x=>x.id===state.result.ontology.id));view.node={'미확인 처리':'unknown','적용 조건':'scope','제외·재개':'exception','근거 연결':'evidence'}[c.node]||'concept';view.inspector='detail';go('ontology');}
});
document.addEventListener('change',event=>{const id=event.target.id;if(id==='ontology-select'||id==='sim-ontology'){selection.ontology=Number(event.target.value);view.node='concept';view.inspector='detail';render();}if(id==='sim-count'){view.simCount=event.target.value;render();}});
document.addEventListener('input',event=>{if(event.target.id==='graph-search'){view.search=event.target.value;graph?.search(view.search);}});
$('#menu-toggle').addEventListener('click',()=>{$('#menu-toggle').setAttribute('aria-expanded',String(document.body.classList.toggle('menu-open')));});
$('#scrim').addEventListener('click',()=>{document.body.classList.remove('menu-open');$('#menu-toggle').setAttribute('aria-expanded','false');});
$('#nav').addEventListener('click',()=>{document.body.classList.remove('menu-open');$('#menu-toggle').setAttribute('aria-expanded','false');});
$('#about-button').addEventListener('click',()=>$('#about').showModal());$$('.close-modal').forEach(x=>x.addEventListener('click',()=>$('#about').close()));
window.addEventListener('hashchange',()=>{render();window.scrollTo(0,0);});render();

</script>
<script>
document.addEventListener('click', function(event) {
  const link = event.target.closest('a[href^="#"]');
  if (!link) return;
  const target = link.getAttribute('href').slice(1);
  if (NAV.some(function(item) { return item[0] === target; })) {
    event.preventDefault();
    go(target);
  } else if (target === 'main') {
    event.preventDefault();
    document.getElementById('main').focus();
  }
}, true);
</script>
</body></html>
"""

# The component is deliberately browser-local. Actual Oracle/Dataiku APIs are not connected.
# A fixed, scrollable viewport also works when Dataiku embeds the webapp in its preview pane.
components.html(HTML, height=1100, scrolling=True, tab_index=0)
