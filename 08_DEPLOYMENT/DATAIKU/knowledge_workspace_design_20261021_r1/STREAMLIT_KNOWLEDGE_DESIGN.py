"""CM workspace design. Paste this single file into a Dataiku Streamlit webapp.

Design interactions are browser-session examples, not knowledge/API writes.
Oracle read-only inspector adapts streamlit_oracle_smoke_20261021_r1.
No model calls, backend imports, external assets, local datasets or credentials.
"""
from copy import deepcopy
from datetime import date, datetime
from html import escape
import logging
import re
import time
import uuid

import streamlit as st

NAV = ["업무 검토", "검토 지식", "원문 데이터", "게시 이력"]
EXAMPLES = {
    "PF 사업성 평가": {
        "question": "부동산 PF 사업성 평가가 악화되는 경우 자산건전성 분류와 대손충당금 적립을 어떻게 연계해야 하나요?",
        "title": "PF 사업성 변화에 따른 검토",
        "checks": ["평가 대상과 기준일 확인", "건전성 분류 기준의 원문 확인", "충당금 기준과 예외의 연결 확인"],
        "missing": ["평가 기준일", "대상 자산과 거래 구조"],
    },
    "충당금과 준비금": {
        "question": "금융투자회사에 적용되는 공개 규정에서 대손충당금과 대손준비금은 어떻게 구분되나요?",
        "title": "충당금·준비금 구분 검토",
        "checks": ["두 용어의 정의 원문 확인", "적용 대상과 산정 기준 비교", "중복 적용 여부와 예외 확인"],
        "missing": ["비교할 규정의 버전", "검토 기준일"],
    },
    "원화 RP 대상 채권": {
        "question": "금융투자회사가 일반 고객과 원화 RP를 하는 경우 대상 채권과 신용등급 요건은 무엇인가요?",
        "title": "원화 RP 대상 요건 검토",
        "checks": ["거래 당사자와 통화 확인", "대상 채권의 원문 요건 확인", "신용등급 기준과 예외 확인"],
        "missing": ["거래 기준일", "채권 종류와 발행 주체"],
    },
}
SEED_KNOWLEDGE = [
    {"id": "DEMO-METHOD-01", "title": "PF 사업성 변화 검토", "kind": "검토 방법", "state": "게시 예시", "revision": 1,
     "summary": "평가 대상에서 분류 기준, 충당금 요건까지 확인할 순서를 정리합니다.",
     "scope": "부동산 PF", "checks": EXAMPLES["PF 사업성 평가"]["checks"], "exception": "원문과 적용 범위를 확인하기 전에는 자동 제외하지 않습니다."},
    {"id": "DEMO-METHOD-02", "title": "충당금·준비금 구분", "kind": "검토 방법", "state": "초안 예시", "revision": 1,
     "summary": "용어 정의와 적용 대상, 산정 기준을 같은 표에서 확인합니다.",
     "scope": "자산건전성", "checks": EXAMPLES["충당금과 준비금"]["checks"], "exception": "적용 규정이나 기준일이 다르면 차이를 남깁니다."},
    {"id": "DEMO-FIELD-01", "title": "검토 기준일 확인", "kind": "조건·확인 사항", "state": "게시 예시", "revision": 1,
     "summary": "질문의 기준일과 원문 시행일을 구분해 기록합니다.",
     "scope": "공통", "checks": ["사용자 기준일 확인", "원문 시행일 확인"], "exception": "기준일을 모르면 미확인으로 보존합니다."},
    {"id": "DEMO-WIKI-01", "title": "원화 RP 근거 탐색 경로", "kind": "위키·탐색 경로", "state": "검토 예시", "revision": 1,
     "summary": "용어 정의에서 대상 채권과 예외 조항으로 이동하는 경로입니다.",
     "scope": "RP", "checks": EXAMPLES["원화 RP 대상 채권"]["checks"], "exception": "과거 경로를 재사용할 때 원문 버전을 다시 확인합니다."},
    {"id": "DEMO-SHORTCUT-01", "title": "유사 질문의 조사 경로", "kind": "숏컷", "state": "검토 예시", "revision": 1,
     "summary": "이전 실행의 근거 경로와 미확인 사항을 함께 확인합니다.",
     "scope": "공통", "checks": ["원래 실행 상태 확인", "권한과 원문 버전 재확인"], "exception": "과거 답변을 정답으로 자동 채택하지 않습니다."},
]

CSS = """
<style>
:root{--ink:#192b38;--muted:#637582;--line:#e2e9ec;--teal:#087e82}
.stApp{background:#f5f7f9;color:var(--ink)}
html,body,[data-testid="stAppViewContainer"],button,input,textarea,select{
 font-family:'Malgun Gothic','Apple SD Gothic Neo','Noto Sans KR',sans-serif}
.block-container{max-width:1480px;padding:2rem 2.5rem 4rem}
[data-testid="stHeader"]{background:transparent}
[data-testid="stSidebar"]{background:#122c3a;color:#eaf2f4;min-width:240px;max-width:240px}
[data-testid="stSidebar"]>div:first-child{padding-top:1.4rem}
[data-testid="stSidebarUserContent"]{padding-top:1rem}
[data-testid="stSidebar"] p,[data-testid="stSidebar"] label{color:#c3d4db}
[data-testid="stSidebar"] button{background:transparent;border:0;color:#c3d4db;text-align:left;
 justify-content:flex-start;padding:12px 16px;min-height:46px;border-radius:8px}
[data-testid="stSidebar"] button[kind="primary"]{background:#244955;color:white;border:1px solid #39606a}
[data-testid="stSidebar"] button:hover{background:#244955;color:white}
[data-testid="stSidebar"] hr{border-color:#2a4653}
.brand{display:flex;gap:12px;align-items:center;margin:8px 0 36px}
.brand-icon{border:1px solid #597b85;padding:7px;border-radius:10px;font-size:17px;letter-spacing:-1px;color:#d1f1ee}
.brand b{font-size:15px;color:white;white-space:nowrap}.brand small{display:block;color:#86a6b3;font-size:9px;letter-spacing:1px;margin-top:4px}
.nav-label{color:#87a5b1;font-size:11px;letter-spacing:1.5px;margin:12px 0}
.side-foot{margin-top:40px;border-top:1px solid #2a4653;padding-top:22px;font-size:12px;line-height:2;color:#a4bec8}
.eyebrow{font-size:12px;color:var(--muted);letter-spacing:.5px;margin:0 0 12px}
.heading{display:flex;justify-content:space-between;gap:16px;align-items:center;margin-bottom:6px}
.heading h1{font-size:29px;letter-spacing:-1.2px;padding:0;margin:0;font-weight:750;line-height:1.5}
.subtitle{color:var(--muted);font-size:14px;margin-bottom:22px;line-height:1.7}
.badge{display:inline-block;white-space:nowrap;font-size:11px;font-weight:600;padding:4px 9px;border-radius:5px;background:#e6f3f1;color:#187575}
.badge.amber{background:#fff2d9;color:#91651b}.badge.gray{background:#edf1f4;color:#586d7b}
.preview-note{border:1px solid #d9e4e8;background:#edf3f6;border-radius:8px;padding:9px 14px;
 color:#5c7280;font-size:12px;margin:12px 0 23px}
[data-testid="stVerticalBlockBorderWrapper"]>div{border-color:var(--line);border-radius:12px;background:white}
.st-key-evidence,.st-key-review_plan,.st-key-method_card{background:white;border-color:var(--line)!important;border-radius:12px}
[data-testid="stForm"]{background:white;border:1px solid var(--line);border-radius:12px;padding:22px}
h2,h3{letter-spacing:-.55px}h3{font-size:18px!important;padding:0 0 12px!important}
[data-testid="stCaptionContainer"]{color:var(--muted)}
button[kind="primary"],button[kind="primaryFormSubmit"]{background:#087e82;border-color:#087e82;color:white}
button{border-radius:7px!important;font-size:13px!important;min-height:38px}
textarea,input{font-size:14px!important}textarea{line-height:1.8!important}
[data-baseweb="tab-list"]{gap:28px;border-bottom:1px solid var(--line);margin-bottom:12px}
[data-baseweb="tab"]{font-size:13px;padding:10px 0}
[aria-selected="true"][data-baseweb="tab"]{color:#087e82}
[data-baseweb="tab-highlight"]{background:#087e82}
.panel-label{font-size:11px;color:#748a97;letter-spacing:1px;text-transform:uppercase;margin-bottom:12px}
.result-title{font-size:21px;font-weight:700;line-height:1.5;margin:9px 0 10px;letter-spacing:-.65px}
.body-copy{font-size:14px;line-height:1.85;color:#425967;margin:10px 0 20px}
.step{display:flex;gap:12px;padding:16px 0;border-top:1px solid #edf1f3;align-items:flex-start}
.step-num{background:#edf4f4;color:#23787b;border-radius:7px;min-width:28px;height:28px;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700}
.step b{display:block;font-size:14px;font-weight:600;margin-bottom:5px}.step small{font-size:12px;color:#78909b;line-height:1.7}
.callout{border-left:3px solid #cba35b;background:#fffbf2;padding:14px 16px;border-radius:0 6px 6px 0;font-size:13px;line-height:1.9;color:#79633d;margin:15px 0}
.source-empty{border:1px dashed #ccd9de;border-radius:9px;padding:23px 18px;background:#f9fbfc;text-align:center;color:#6c8390;font-size:13px;line-height:1.9;margin:14px 0}
.mini-label{font-size:11px;color:#8295a0;margin-bottom:6px}.mini-value{font-size:14px;color:#244753;font-weight:600}
.knowledge-title{font-size:15px;font-weight:650;line-height:1.8}.knowledge-desc{font-size:12px;color:#69808c;line-height:1.8;margin-top:8px}
.publish-step{padding:16px;border:1px solid var(--line);border-radius:8px;margin-bottom:12px;background:white;font-size:14px;line-height:1.9}
.publish-step b{color:#197378}
@media(max-width:800px){.block-container{padding:1.5rem 1rem 3rem}.heading h1{font-size:25px}.heading{align-items:flex-start}.badge{white-space:normal}}
</style>
"""


def html(content):
    # Static markup only; all variable text below is escaped.
    st.markdown(content, unsafe_allow_html=True)


def badge(text, tone=""):
    return '<span class="badge ' + tone + '">' + escape(str(text)) + '</span>'


def go(page):
    st.session_state.page = page


def initialize():
    previous = st.session_state.get("review") or {}
    for key, value in {"page": NAV[0], "knowledge": SEED_KNOWLEDGE, "events": [], "drafts": {},
                       "selected_knowledge": "DEMO-METHOD-01", "question": previous.get("question", EXAMPLES["PF 사업성 평가"]["question"]),
                       "example": previous.get("example", "PF 사업성 평가"), "review": None}.items():
        if key not in st.session_state:
            st.session_state[key] = deepcopy(value)


def set_example():
    st.session_state.question = EXAMPLES[st.session_state.example]["question"]
    st.session_state.review = None


def header(title, subtitle):
    html('<div class="eyebrow">CM WORKSPACE &nbsp; / &nbsp; 리스크관리</div>'
         '<div class="heading"><h1>' + escape(title) + '</h1>' + badge("화면 설계 v1", "gray") + '</div>'
         '<div class="subtitle">' + escape(subtitle) + '</div>')


def sidebar():
    with st.sidebar:
        html('<div class="brand"><div class="brand-icon">CM</div><div><b>검토 워크스페이스</b><small>KNOWLEDGE & REVIEW</small></div></div>'
             '<div class="nav-label">WORKSPACE</div>')
        icons = [":material/forum:", ":material/menu_book:", ":material/database:", ":material/history:"]
        for name, icon in zip(NAV, icons):
            st.button(name, key="nav_" + name, icon=icon, use_container_width=True,
                      type="primary" if st.session_state.page == name else "secondary", on_click=go, args=(name,))
        html('<div class="side-foot">DATAIKU WEBAPP<br>설계 미리보기 · 예시 데이터<br>RAG · 관리 API 미연결</div>')
        with st.expander("이 화면의 연결 상태"):
            st.caption("질문·편집·게시 흐름은 화면 시안입니다. 예시 변경은 현재 세션에만 남습니다.")
            st.caption("원문 데이터의 Oracle 조회는 기존 AIDP 연결을 사용합니다. 문서별 사용자 권한은 아직 연결되지 않았습니다.")


def render_review():
    header("업무 검토", "질문을 검토 항목으로 나누고, 판단과 근거를 함께 확인합니다.")
    html('<div class="preview-note">설계 예시 &nbsp;·&nbsp; 아래 항목은 화면 구성을 위한 예시입니다. 실제 RAG 답변과 법률 판단은 생성하지 않습니다.</div>')
    left, right = st.columns([2.05, 1], gap="large")
    with left:
        st.selectbox("검토 예시", list(EXAMPLES), key="example", on_change=set_example)
        with st.form("question_form"):
            st.markdown("### 무엇을 검토할까요?")
            st.text_area("질문", key="question", height=102, label_visibility="collapsed", max_chars=3000)
            scope, asof = st.columns([1.4, 1])
            scope.selectbox("조사 범위", ["내규에서 연결된 외규", "외규", "내규"], key="scope")
            asof.date_input("검토 기준일", date(2026, 10, 21), key="asof")
            submit = st.form_submit_button("검토 화면 미리보기", type="primary", use_container_width=True)
        if submit:
            if not st.session_state.question.strip():
                st.error("검토할 질문을 입력하세요.")
                st.session_state.review = None
            else:
                st.session_state.review = {"question": st.session_state.question.strip(), "scope": st.session_state.scope,
                                           "asof": str(st.session_state.asof), "example": st.session_state.example}
        review = st.session_state.review
        selected = EXAMPLES[st.session_state.example]
        exact_example = review is None or review["question"] == selected["question"]
        tabs = st.tabs(["검토 요약", "내규–외규 대사", "실행 기록"])
        with tabs[0], st.container(border=True, key="review_plan"):
            html('<div class="panel-label">REVIEW PLAN</div>' + badge("원문 확인 대기", "amber")
                 + '<div class="result-title">' + escape(selected["title"] if exact_example else "입력한 질문의 검토 준비") + '</div>'
                 '<div class="body-copy">확인할 항목과 추가로 필요한 정보를 먼저 보여줍니다. 실제 조사 결과가 도착하면 이 자리에 판단·이유·인용을 연결합니다.</div>')
            if review:
                st.caption("입력한 질문 · " + review["question"])
                st.caption("선택한 범위 · " + review["scope"] + " / 기준일 · " + review["asof"])
            checks = selected["checks"] if exact_example else ["질문 해석 결과 확인", "관련 원문과 적용 범위 확인", "판단·인용·미확인 사항 확인"]
            for i, check in enumerate(checks):
                html('<div class="step"><div class="step-num">0' + str(i+1) + '</div><div><b>' + escape(check)
                     + '</b><small>실제 조사에서 원문과 확인 결과를 연결할 항목</small></div></div>')
            html('<div class="callout"><b>추가로 확인할 정보</b><br>' + escape(" · ".join(selected["missing"]) if exact_example else "실제 질문 해석 후 확인할 정보를 표시합니다.") + '</div>')
        with tabs[1]:
            st.caption("표 구조 예시 · 질문 → 내규 원문 → 해당 개념·범위 → 연결 외규 → 해석 순서입니다.")
            st.dataframe([{"내규 출처 조항": "원문 연결 대기", "개념·확인 내용": "적용 대상과 기준일", "내규 실제 원문": "미확보",
                           "연결 외규·조항": "조사 대기", "외규 실제 원문": "미확보", "해석·미확인": "해석 전"}],
                         hide_index=True, use_container_width=True)
        with tabs[2]:
            st.info("이 화면에서 실행한 RAG 요청은 없습니다.")
            st.caption("연결 후에는 요청 ID, 조사 단계, 사용 지식 버전, 미확인 사유, 재개 가능 여부를 기존 실행 기록에서 읽습니다.")
    with right:
        with st.container(border=True, key="evidence"):
            html('<div class="panel-label">EVIDENCE PANEL</div>')
            st.markdown("### 근거와 검토 지식")
            source_tab, method_tab = st.tabs(["근거 원문", "검토 지식"])
            with source_tab:
                html('<div class="mini-label">선택한 근거</div><div class="mini-value">원문 연결 대기</div>'
                     '<div class="source-empty">문서 · 조항 · 버전<br>선택한 인용의 실제 원문이<br>이곳에 표시됩니다.</div>')
                st.caption("위키 설명이나 과거 답변을 원문으로 표시하지 않습니다.")
                st.button("원문 데이터 살펴보기", use_container_width=True, on_click=go, args=("원문 데이터",))
            with method_tab:
                html(badge("연결 방식 예시", "gray") + '<div class="body-copy">검토 방법과 조건을 조회한 뒤, 적용 여부·제외 이유·미확인 사항을 함께 보여줍니다.</div>')
                st.caption("버전과 원문 해시는 실제 관리 API에서 확인합니다.")
        with st.container(border=True, key="method_card"):
            html('<div class="panel-label">KNOWLEDGE TO REVIEW</div>')
            item = st.session_state.knowledge[0 if st.session_state.example == "PF 사업성 평가" else 1 if st.session_state.example == "충당금과 준비금" else 3]
            html('<div class="knowledge-title">' + escape(item["title"]) + '</div>'
                 '<div class="knowledge-desc">' + escape(item["summary"]) + '</div>')
            st.caption("v" + str(item["revision"]) + " · " + item["state"] + " · 실제 적용 아님")
            if st.button("검토 지식 열기 →", use_container_width=True):
                st.session_state.selected_knowledge = item["id"]
                go("검토 지식")
                st.rerun()


def choose_knowledge(item_id):
    st.session_state.selected_knowledge = item_id


def render_knowledge():
    header("검토 지식", "확인 사항과 조건, 근거 경로를 편집하고 게시 전에 적용 범위를 확인합니다.")
    html('<div class="preview-note">편집 흐름 시안 &nbsp;·&nbsp; 저장과 게시 미리보기는 현재 세션에만 반영됩니다. Oracle·관리 API에는 기록되지 않습니다.</div>')
    listing, editing = st.columns([1, 1.9], gap="large")
    with listing:
        search = st.text_input("지식 검색", placeholder="제목 또는 업무 범위")
        kind = st.selectbox("지식 종류", ["전체", "검토 방법", "조건·확인 사항", "위키·탐색 경로", "숏컷"])
        items = [x for x in st.session_state.knowledge if (kind == "전체" or x["kind"] == kind) and
                 search.lower() in (x["title"] + x["scope"]).lower()]
        st.caption(f"표시 중인 예시 {len(items)}개")
        for item in items:
            with st.container(border=True):
                html(badge(item["kind"], "gray") + '<div class="knowledge-title">' + escape(item["title"]) + '</div>')
                st.caption(item["state"] + " · v" + str(item["revision"]))
                st.button("선택됨" if item["id"] == st.session_state.selected_knowledge else "열기 →",
                          key="select_" + item["id"], type="primary" if item["id"] == st.session_state.selected_knowledge else "secondary",
                          use_container_width=True, on_click=choose_knowledge, args=(item["id"],))
        if not items:
            st.info("검색 조건에 맞는 예시가 없습니다.")
    with editing:
        item = next(x for x in st.session_state.knowledge if x["id"] == st.session_state.selected_knowledge)
        item_id = item["id"]
        draft = st.session_state.drafts.get(item_id, item)
        st.markdown("### " + item["title"])
        st.caption(item_id + " · v" + str(item["revision"]) + " · " + item["state"])
        edit_tab, source_tab, publish_tab = st.tabs(["내용·적용 조건", "근거 연결", "게시 미리보기"])
        with edit_tab, st.form("edit_" + item_id):
            title = st.text_input("지식 이름", draft["title"], max_chars=120)
            summary = st.text_area("검토 목적", draft["summary"], height=85, max_chars=1000)
            scope = st.text_input("적용 업무", draft["scope"], max_chars=120)
            checks = st.text_area("확인할 항목 · 한 줄에 하나", "\n".join(draft["checks"]), height=130, max_chars=2000)
            exception = st.text_area("제외·재개 기준", draft["exception"], height=85, max_chars=1000)
            st.caption("실제 연결 시: 범위 미확정은 미확인으로 보존하고, 확인되지 않은 조건으로 조사를 생략하지 않습니다.")
            if st.form_submit_button("초안 저장 미리보기", type="primary", use_container_width=True):
                if not title.strip() or not checks.strip():
                    st.error("지식 이름과 확인할 항목을 입력하세요.")
                else:
                    st.session_state.drafts[item_id] = {**deepcopy(item), "title": title.strip(), "summary": summary.strip(),
                         "scope": scope.strip(), "checks": [x.strip() for x in checks.splitlines() if x.strip()], "exception": exception.strip()}
                    st.success("세션에 초안 예시를 저장했습니다. 실제 DB 저장은 실행하지 않았습니다.")
        with source_tab:
            st.info("이 예시에는 검증된 원문 참조가 연결되어 있지 않습니다.")
            st.dataframe([{"문서": "선택 대기", "조항·위치": "선택 대기", "원문 버전": "미확인", "원문 해시": "미확인"}],
                         hide_index=True, use_container_width=True)
            st.caption("원문을 선택하면 기존 source-reference API가 버전·위치·해시를 확정합니다. 위키·숏컷도 기존 저장소의 참조를 사용합니다.")
        with publish_tab:
            saved = st.session_state.drafts.get(item_id)
            for num, title_, detail in [(1, "변경 내용 확인", "저장한 초안의 범위·확인 항목·제외 기준을 확인합니다."),
                                        (2, "근거와 권한 검증", "게시 API에서 원문 해시, 참조 버전, 사용자 권한을 검증합니다."),
                                        (3, "게시 버전 확정", "검증된 버전만 질문에 제공하고 이전 버전은 이력으로 보존합니다.")]:
                html('<div class="publish-step"><b>0' + str(num) + ' &nbsp; ' + escape(title_) + '</b><br>' + escape(detail) + '</div>')
            if saved:
                st.caption("초안 예시 · " + saved["title"])
            st.button("실제 게시 · 관리 API 연결 필요", disabled=True, use_container_width=True)
            if st.button("게시 후 화면 미리보기", disabled=saved is None, use_container_width=True):
                updated = {**deepcopy(saved), "revision": item["revision"] + 1, "state": "게시 예시"}
                st.session_state.knowledge = [updated if x["id"] == item_id else x for x in st.session_state.knowledge]
                st.session_state.events.insert(0, {"시간": datetime.now().strftime("%H:%M:%S"), "지식": updated["title"],
                    "버전": "v" + str(updated["revision"]), "상태": "게시 화면 예시", "기록 위치": "현재 세션만"})
                st.session_state.drafts.pop(item_id, None)
                go("게시 이력")
                st.rerun()


# Same bounded SELECT-only inspector as the existing Dataiku example.
# Never feed table previews into RAG or treat them as authorized source bindings.
def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def identifier(value):
    return '"' + str(value).replace('"', '""') + '"'


def oracle_query(connection, label, sql):
    request_id = uuid.uuid4().hex[:12]
    started = time.monotonic()
    try:
        import dataiku
        with st.spinner(label + " 중…"):
            frame = dataiku.SQLExecutor2(connection=connection).query_to_df(sql, infer_from_schema=True, parse_dates=False)
    except Exception as exc:
        # Terminal UI boundary: SQLExecutor2 has deployment-specific exceptions.
        # One call, no retries. Keep root cause in restricted backend logs.
        logging.getLogger("cm_streamlit").exception("SQL_FAILED request=%s stage=%s", request_id, label)
        codes = ", ".join(sorted(set(re.findall(r"ORA-\d{5}", str(exc)))))
        st.error(label + " 실패 · 확인 번호 " + request_id + (" · " + codes if codes else ""))
        st.caption("Dataiku 백엔드 로그에서 확인 번호를 확인하세요. 설정을 확인한 뒤 버튼으로 다시 실행합니다.")
        st.stop()
    st.caption(f"{label} · {len(frame)}행 · {time.monotonic()-started:.2f}초")
    return frame


def oracle_inspector():
    st.caption("기존 Streamlit 예시의 AIDP 연결을 사용한 읽기 전용 조회입니다. 웹앱 실행 계정의 DB 권한으로 조회합니다.")
    st.warning("개발 확인용 · 문서별 사용자 권한은 미연결입니다. 제한된 개발자용 Dataiku 웹앱에서 사용하세요.")
    c1, c2, c3 = st.columns(3)
    connection = c1.text_input("Dataiku 연결 이름", "AIDP").strip()
    schema = c2.text_input("Oracle 스키마", placeholder="현재 스키마").strip().upper()
    prefix = c3.text_input("테이블 시작 글자", placeholder="선택").strip().upper()
    binding = (connection, schema, prefix)
    if st.session_state.get("oracle_binding") != binding:
        st.session_state.oracle_binding = binding
        for key in ("oracle_catalog", "oracle_rows", "oracle_info"):
            st.session_state.pop(key, None)
    if not connection or (schema and not re.fullmatch(r"[A-Z][A-Z0-9_$#]{0,127}", schema)) or (prefix and not re.fullmatch(r"[A-Z0-9_$#]{1,128}", prefix)):
        st.error("연결 이름을 입력하고 스키마·시작 글자는 일반 Oracle 식별자로 입력하세요.")
        return
    c1, c2 = st.columns(2)
    if c1.button("연결 확인", use_container_width=True):
        st.session_state.pop("oracle_info", None)
        st.session_state.oracle_info = oracle_query(connection, "연결 확인", "SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS DB_USER, SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AS CURRENT_SCHEMA FROM DUAL")
    if c2.button("테이블 목록 조회", type="primary", use_container_width=True):
        st.session_state.pop("oracle_catalog", None)
        st.session_state.pop("oracle_rows", None)
        owner_sql = literal(schema) if schema else "SYS_CONTEXT('USERENV','CURRENT_SCHEMA')"
        filter_sql = f" AND SUBSTR(TABLE_NAME,1,{len(prefix)})={literal(prefix)}" if prefix else ""
        st.session_state.oracle_catalog = oracle_query(connection, "테이블 목록", f"SELECT OWNER,TABLE_NAME FROM (SELECT OWNER,TABLE_NAME FROM ALL_TABLES WHERE OWNER={owner_sql}{filter_sql} ORDER BY TABLE_NAME) WHERE ROWNUM<=201")
    if st.session_state.get("oracle_info") is not None:
        st.success("이 연결 설정에서 Oracle 응답을 확인했습니다.")
        st.dataframe(st.session_state.oracle_info, hide_index=True, use_container_width=True)
    catalog = st.session_state.get("oracle_catalog")
    if catalog is None:
        st.info("연결 이름을 확인하고 테이블 목록을 조회하세요. 화면 진입만으로 조회하지 않습니다.")
        return
    if catalog.empty:
        st.info("이 조건에서 표시할 테이블이 없습니다. 범위와 접근 권한을 확인하세요.")
        return
    if len(catalog) > 200:
        st.warning("처음 200개 테이블을 표시합니다. 시작 글자로 범위를 줄이세요.")
    options = list(catalog.iloc[:200][["OWNER", "TABLE_NAME"]].itertuples(index=False, name=None))
    owner, table = st.selectbox("테이블", options, format_func=lambda x: ".".join(x))
    row_limit = st.number_input("조회 행 수", 1, 20, 10)
    selection = (binding, owner, table, row_limit)
    if st.session_state.get("oracle_selection") != selection:
        st.session_state.oracle_selection = selection
        st.session_state.pop("oracle_rows", None)
    if st.button("선택 테이블 미리보기", type="primary"):
        st.session_state.pop("oracle_rows", None)
        columns = oracle_query(connection, "열 정보", f"SELECT COLUMN_NAME,DATA_TYPE FROM (SELECT COLUMN_NAME,DATA_TYPE FROM ALL_TAB_COLUMNS WHERE OWNER={literal(owner)} AND TABLE_NAME={literal(table)} ORDER BY COLUMN_ID) WHERE ROWNUM<=41")
        if columns.empty:
            st.warning("열 정보가 없습니다. 목록과 접근 권한을 확인하세요.")
            return
        if len(columns) > 40:
            st.caption("앞 40개 열만 표시합니다.")
        expressions, skipped = [], []
        for name, dtype in columns.iloc[:40].itertuples(index=False, name=None):
            col = identifier(name)
            if dtype in {"CLOB", "NCLOB"}:
                expressions.append(f"DBMS_LOB.SUBSTR({col},300,1) AS {col}")
            elif dtype in {"CHAR", "VARCHAR2", "NCHAR", "NVARCHAR2"}:
                expressions.append(f"SUBSTR({col},1,300) AS {col}")
            elif dtype in {"NUMBER", "FLOAT", "BINARY_FLOAT", "BINARY_DOUBLE", "DATE"} or dtype.startswith("TIMESTAMP"):
                expressions.append(col)
            else:
                skipped.append(str(name))
        if skipped:
            st.caption("미지원 형식으로 제외된 열: " + ", ".join(skipped))
        if not expressions:
            st.warning("지원하는 형식의 열이 없습니다.")
            return
        sql = f"SELECT {', '.join(expressions)} FROM {identifier(owner)}.{identifier(table)} WHERE ROWNUM<={int(row_limit)}"
        st.session_state.oracle_rows = oracle_query(connection, "데이터 조회", sql)
    if st.session_state.get("oracle_rows") is not None:
        st.caption(f"{owner}.{table} · 순서 미지정 일부 행 · 문자열·본문 앞 300자 · 원문 전체가 아닙니다.")
        st.dataframe(st.session_state.oracle_rows, hide_index=True, use_container_width=True)


def render_sources():
    header("원문 데이터", "Dataiku의 Oracle 데이터를 확인하고, 검토에 연결할 출처 정보를 살펴봅니다.")
    mode = st.radio("표시할 데이터", ["설계 예시", "Oracle 조회"], horizontal=True)
    if mode == "Oracle 조회":
        oracle_inspector()
        return
    html('<div class="preview-note">원문 탐색 화면의 구성 예시입니다. 아래 항목은 실제 문서나 수집 통계가 아닙니다.</div>')
    st.text_input("문서·조항·용어 검색", placeholder="예: 자산건전성, 사업성 평가", disabled=True)
    left, right = st.columns([1, 1.6], gap="large")
    with left, st.container(border=True):
        st.markdown("### 문서 목록")
        st.radio("문서 종류", ["내규", "외규"], horizontal=True)
        st.info("문서 카탈로그 API 연결 대기")
        st.caption("목록에는 문서명, 버전, 시행일, 공개·내부 구분을 표시합니다.")
    with right, st.container(border=True):
        st.markdown("### 선택한 원문")
        html('<div class="source-empty">문서를 선택하면 목차와 조항을 탐색하고<br>원문 전체를 권한 범위 안에서 읽습니다.</div>')
        st.dataframe([{"표시 항목": "출처", "내용": "문서 ID · 이름 · 내규/외규"},
                      {"표시 항목": "원문 위치", "내용": "장 · 절 · 조 · 항 · 호"},
                      {"표시 항목": "버전", "내용": "시행일 · 원문 해시"}], hide_index=True, use_container_width=True)
        st.button("검토 지식에 참조 연결 · API 연결 필요", disabled=True, use_container_width=True)


def render_history():
    header("게시 이력", "무엇을 바꿨는지, 어떤 버전이 질문에 사용되는지 확인합니다.")
    html('<div class="preview-note">현재 세션의 화면 미리보기 기록입니다. 실제 게시 이력이나 감사 로그가 아닙니다.</div>')
    if st.session_state.events:
        st.dataframe(st.session_state.events, hide_index=True, use_container_width=True)
    else:
        with st.container(border=True):
            st.markdown("### 아직 게시 미리보기 기록이 없습니다")
            st.caption("검토 지식에서 초안을 저장하고 ‘게시 후 화면 미리보기’를 누르면 변경 버전이 이곳에 나타납니다.")
            st.button("검토 지식 편집하기 →", on_click=go, args=("검토 지식",))
    with st.expander("실제 연결 시 확인할 정보"):
        st.write("게시자 · 게시 시각 · 변경 사유 · 원문 및 참조 버전 · 영향받는 검토 항목 · 이전 버전")
        st.caption("기존 관리 API의 작업 receipt와 게시 버전을 사용합니다. 이 화면에서 별도 게시 저장소를 만들지 않습니다.")
    st.button("이전 버전 복원 · 관리 API 연결 필요", disabled=True)


def main():
    st.set_page_config(page_title="CM · 검토 워크스페이스", page_icon="📑", layout="wide", initial_sidebar_state="expanded")
    html(CSS)
    initialize()
    sidebar()
    {"업무 검토": render_review, "검토 지식": render_knowledge, "원문 데이터": render_sources, "게시 이력": render_history}[st.session_state.page]()


if __name__ == "__main__":
    main()
