"""Dataiku knowledge operations UI design; synthetic, session-only workflow data.
Only the inherited Oracle inspector issues real read-only SQL. No model calls.
"""
from copy import deepcopy
from datetime import datetime
from html import escape
import hashlib
import json
import logging
import re
import time
import uuid
import streamlit as st
import os
from pathlib import Path
import sys
if os.environ.get("GENOS_RAG_ONTOLOGY_CONFIG"):
    sys.path.insert(0,str(Path(os.environ.get("GENOS_ONTOLOGY_CODE_ROOT",Path(__file__).resolve().parents[3]))/"02_BACKEND"))

NAV = ['배치 모니터', '구조화 누락 승인', '숏컷 승인', 'Legal Wiki', '온톨로지 관리', '시뮬레이션']
STRUCTURES = [
 {'id':'ST-001','title':'표 아래 각주 누락','document':'예시 위험검토지침','location':'제4조 · 표 2 · 각주 ①','type':'각주 누락','status':'승인 대기','source':'표 2. 검토 항목\n대상 업무 | 확인 자료\nPF | 사업성 평가 자료\n① 기준일이 없는 자료는 기준일 확인 대상으로 남긴다.','before':'표 2. 검토 항목\n대상 업무 | 확인 자료\nPF | 사업성 평가 자료','fix':'① 기준일이 없는 자료는 기준일 확인 대상으로 남긴다.','impact':'표의 적용 범위를 읽을 때 각주가 함께 전달됩니다.'},
 {'id':'ST-002','title':'항·호 경계 분리 보완','document':'예시 자료관리기준','location':'제7조 제2항','type':'조항 분리','status':'승인 대기','source':'② 다음 자료를 확인한다.\n1. 작성 기준일\n2. 작성 부서','before':'② 다음 자료를 확인한다. 1. 작성 기준일 2. 작성 부서','fix':'② 다음 자료를 확인한다.\n1. 작성 기준일\n2. 작성 부서','impact':'항과 호를 구분해 원문 위치를 탐색할 수 있습니다.'},
 {'id':'ST-003','title':'명시 참조 연결 보완','document':'예시 검토업무절차','location':'제3조 제1항 → 별표 1','type':'참조 연결','status':'승인 대기','source':'검토 항목은 별표 1을 따른다.','before':'검토 항목은 별표 1을 따른다.\n참조 연결: 미확보','fix':'같은 문서의 별표 1을 참조 끝점으로 연결','impact':'본문에서 명시적으로 참조한 별표를 열 수 있습니다.'},
]
SHORTCUTS = [
 {'id':'SC-021','title':'PF 기준일 확인 경로','question':'PF 검토에 필요한 기준일은 어디서 확인하나요?','status':'승인 대기','eligible':True,'run':'DEMO-RUN-104','state':'완료','reads':'예시 위험검토지침 / 제4조 / v1','scope':'동일 업무·동일 조건','path':['업무 유형 확인','기준일 관련 원문 열람','확인 결과·미확인 기록']},
 {'id':'SC-022','title':'충당금 관련 조사 경로','question':'충당금 검토 시 어떤 자료가 필요한가요?','status':'승인 대기','eligible':False,'run':'DEMO-RUN-108','state':'부분 완료','reads':'일부 원문 미확보','scope':'범위 미확정','path':['용어 확인','연결 조항 조사 중단','미확보 근거 기록']},
]
WIKIS = [
 {'id':'WK-01','title':'PF 검토의 확인 순서','status':'게시됨','revision':2,'scope':'PF 검토','body':'### 검토 목적\n평가 대상과 기준일을 먼저 확인합니다.\n\n### 탐색 순서\n1. 관련 내규의 범위를 확인합니다.\n2. 명시적으로 연결된 외규의 원문을 읽습니다.\n3. 예외와 미확인 사항을 함께 남깁니다.','source':'예시 위험검토지침 · 제4조 · v1'},
 {'id':'WK-02','title':'기준일과 시행일 구분','status':'검토 필요','revision':1,'scope':'공통','body':'### 확인 사항\n질문의 기준일과 문서 시행일을 구분해서 기록합니다.\n\n### 미확인 처리\n날짜를 확보하지 못하면 추정해서 채우지 않습니다.','source':'예시 자료관리기준 · 제7조 · v1'},
 {'id':'WK-03','title':'서로 다른 해석 검토','status':'상충 확인','revision':1,'scope':'공통','body':'### 상충 상태\n두 해석의 원문과 적용 범위를 나란히 보존합니다.\n\n### 재검토\n어떤 조건에서 해석이 달라지는지 확인합니다.','source':'출처 연결 재확인 필요'},
]
ONTOLOGIES = [
 {'id':'ON-01','title':'PF 검토 조건','revision':3,'status':'검토 대기','business':'PF','require_date':True,'unknown':'미확인 유지','wiki':'WK-01'},
 {'id':'ON-02','title':'공통 기준일 확인','revision':1,'status':'초안','business':'공통','require_date':True,'unknown':'미확인 유지','wiki':'WK-02'},
]
SCENARIOS = [
 {'id':'T01','case':'정상 입력','input':'업무·기준일·원문 확보','expected':'검토 항목 연결','observed':'검토 항목 연결','status':'일치','node':'적용 조건'},
 {'id':'T02','case':'기준일 누락','input':'업무만 확인 / 기준일 없음','expected':'미확인 유지','observed':'적용으로 처리','status':'불일치','node':'미확인 처리'},
 {'id':'T03','case':'업무 범위 밖','input':'다른 업무 유형','expected':'제외 이유 기록','observed':'제외 이유 기록','status':'일치','node':'적용 조건'},
 {'id':'T04','case':'예외 해당','input':'명시된 제외 조건 충족','expected':'해당 항목 제외','observed':'해당 항목 제외','status':'일치','node':'제외·재개'},
 {'id':'T05','case':'원문 버전 변경','input':'참조 원문 변경 / 재확인 전','expected':'원문 재확인','observed':'원문 재확인 대기','status':'미확인','node':'근거 연결'},
 {'id':'T06','case':'누락 자료 확보','input':'미확인 기준일 추가 확보','expected':'기존 조사 재개','observed':'기존 조사 재개','status':'일치','node':'제외·재개'},
]
CSS = """
<style>
:root{--ink:#203441;--muted:#6e818d;--line:#e2e9ed;--teal:#087e82}
.stApp{background:#f5f7f9;color:var(--ink)}
html,body,input,textarea,button{font-family:'Malgun Gothic','Apple SD Gothic Neo','Noto Sans KR',sans-serif}
.block-container{max-width:1500px;padding:2rem 2.4rem 4rem}
[data-testid=stHeader]{background:transparent}
[data-testid=stSidebar]{background:#122c3a;color:#dce9ef;min-width:240px;max-width:240px}
[data-testid=stSidebar] p,[data-testid=stSidebar] label{color:#b8cbd5}
[data-testid=stSidebar] button{border:0;background:transparent;color:#c2d6df;justify-content:flex-start;text-align:left;min-height:45px;padding:10px 14px}
[data-testid=stSidebar] button[kind=primary]{background:#24505c;color:#fff;border:1px solid #396672}
[data-testid=stSidebar] button:hover{background:#244955;color:white}
.brand{display:flex;align-items:center;gap:12px;margin:0 0 28px}.logo{border:1px solid #6b8995;border-radius:9px;padding:8px;color:#c8f0e9;font-size:16px}
.brand b{font-size:17px;color:white}.brand small{display:block;color:#8eaab7;font-size:9px;margin-top:4px;letter-spacing:1px}
.nav-label{color:#7d9ba9;font-size:10px;letter-spacing:1.7px;margin:18px 0 12px}
.side-foot{margin-top:30px;padding-top:18px;border-top:1px solid #2a4653;font-size:11px;line-height:2;color:#99b2bf}
.eyebrow{font-size:11px;color:#728692;margin:0 0 10px;letter-spacing:1px}
.heading{display:flex;align-items:center;justify-content:space-between;gap:10px}.heading h1{padding:0;margin:0;font-size:29px;line-height:1.5;letter-spacing:-1px}
.subtitle{color:#6b808e;font-size:13px;line-height:1.8;margin:6px 0 15px}
.preview{color:#557280;background:#eaf2f5;border:1px solid #dae6eb;border-radius:7px;padding:8px 12px;font-size:11px;margin-bottom:20px}
.badge{display:inline-block;border-radius:5px;background:#e5f3ef;color:#23766a;padding:4px 8px;font-size:11px;font-weight:600;white-space:nowrap}
.badge.amber{background:#fff1d6;color:#94631b}.badge.red{background:#fbe9e7;color:#ad4f47}.badge.gray{background:#edf1f4;color:#657985}
.metric-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:22px}
.metric{padding:17px 19px;background:white;border:1px solid var(--line);border-radius:10px}
.metric span{font-size:12px;color:#6f8390}.metric b{display:block;font-size:29px;font-weight:700;line-height:1.6;letter-spacing:-1px}.metric small{color:#8b9ba5;font-size:11px}
.pipeline{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin:15px 0 8px}
.stage{position:relative;padding:18px 10px;border:1px solid #dce8e7;background:#f8fbfa;border-radius:8px}
.stage.warn{border-color:#ead19a;background:#fffbf1}.stage b{display:block;font-size:13px;margin:10px 0 8px}.stage small{display:block;color:#82949c;font-size:11px;line-height:1.8}
.stage:after{content:'›';position:absolute;right:-9px;top:43%;z-index:1;background:white;color:#a0b1b8}.stage:last-child:after{display:none}
h3{font-size:17px!important;letter-spacing:-.35px;padding:0 0 10px!important}h2{font-size:22px!important}
[data-testid=stForm]{background:white;border-color:var(--line);border-radius:10px;padding:19px}
[class*=st-key-panel_]{background:white;border-color:var(--line)!important;border-radius:10px}
button{border-radius:7px!important;font-size:13px!important;min-height:38px}
button[kind=primary],button[kind=primaryFormSubmit]{background:#087e82;border-color:#087e82;color:white}
input,textarea{font-size:13px!important}textarea{line-height:1.8!important}
[data-baseweb=tab-list]{gap:25px;border-bottom:1px solid #dfe7ec;margin-bottom:13px}
[data-baseweb=tab]{font-size:13px;padding:10px 0}[aria-selected=true][data-baseweb=tab]{color:#087e82}
[data-baseweb=tab-highlight]{background:#087e82}
.kicker{font-size:10px;letter-spacing:1px;color:#8397a1;margin-bottom:12px}
.title{font-size:16px;font-weight:700;margin:8px 0;line-height:1.6}.body{font-size:13px;line-height:1.9;color:#526b79}
.line-item{border-top:1px solid #e9eef0;padding:13px 0;display:flex;align-items:center;justify-content:space-between;gap:12px;font-size:13px}
.line-item small{display:block;color:#8396a1;font-size:11px;line-height:1.8}
.source{white-space:pre-wrap;font-size:13px;line-height:2;background:#f7f9fa;border:1px solid #e1e8ed;border-radius:8px;padding:18px;min-height:153px;color:#354e5b}
.addition{background:#edf8f3;border-left:3px solid #60a88b;padding:12px 14px;font-size:13px;line-height:1.9;white-space:pre-wrap;margin:12px 0;color:#316d57}
.callout{border-left:3px solid #cfa85b;background:#fffbf2;border-radius:0 6px 6px 0;padding:12px 15px;font-size:12px;line-height:1.9;color:#826b40;margin:13px 0}
.route{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:16px 0}.route span{background:#edf4f6;border:1px solid #dce6eb;border-radius:7px;padding:10px;font-size:12px;color:#476b7b}.route i{font-style:normal;color:#8ca3ae}
.graph{padding:18px;border:1px solid #dce6eb;background:#f8fbfc;border-radius:9px;margin-bottom:15px}
.graph-row{display:flex;justify-content:center;align-items:center;gap:14px;margin:10px 0;flex-wrap:wrap}.node{padding:12px 16px;background:white;border:1px solid #cbdce3;border-radius:8px;text-align:center;font-size:12px;min-width:125px}.node.focus{border:2px solid #389294;background:#eaf6f4}.node.warn{border-color:#d4af66;background:#fffaee}.node small{display:block;font-size:10px;color:#7b8f9b;margin-top:5px}.arrow{text-align:center;color:#98abb6;font-size:15px}
.history{border-left:2px solid #dbe6ea;padding:5px 0 12px 15px;margin-left:4px;font-size:12px;line-height:1.9;color:#627b87}
@media(max-width:800px){.block-container{padding:1.5rem 1rem 3rem}.heading h1{font-size:24px}.metric-grid{grid-template-columns:repeat(2,1fr)}.pipeline{grid-template-columns:1fr}.stage:after{display:none}.heading{align-items:flex-start}.badge{white-space:normal}}
</style>
"""


def html(value):
    st.markdown(value, unsafe_allow_html=True)


def badge(text, tone=''):
    return '<span class="badge '+tone+'">'+escape(str(text))+'</span>'


def tone(status):
    if status in {'불일치','상충 확인','부분 완료','반려'}: return 'red'
    if status in {'승인 대기','검토 대기','검토 필요','미확인','보류','초안','확인 필요'}: return 'amber'
    return ''


def state():
    return st.session_state.studio


def initialize():
    if 'studio' not in st.session_state:
        st.session_state.studio={'page':NAV[0],'structures':deepcopy(STRUCTURES),'shortcuts':deepcopy(SHORTCUTS),'wikis':deepcopy(WIKIS),'ontologies':deepcopy(ONTOLOGIES),'events':[],'wiki_drafts':{},'focus_structures':'ST-001','focus_shortcuts':'SC-021','focus_wikis':'WK-01','focus_ontologies':'ON-01','simulation':None,'simulations':[],'sim_target':'ON-01'}
    for item in state()['ontologies']:
        item.setdefault('exclude','업무 범위 밖이면 제외 이유를 기록합니다.')
        item.setdefault('resume','누락된 사실·원문을 확보하면 기존 조사에서 재개합니다.')


def navigate(page, collection=None, item_id=None):
    state()['page']=page
    if collection: state()['focus_'+collection]=item_id


def record(area,target,action,reason):
    state()['events'].insert(0,{'시간':datetime.now().strftime('%H:%M:%S'),'영역':area,'대상':target,'처리':action,'의견':reason,'저장':'현재 세션 · 예시'})


def pending(collection):
    return sum(x['status'] in {'승인 대기','보류'} for x in state()[collection])


def metrics(items):
    html('<div class="metric-grid">'+''.join('<div class="metric"><span>'+escape(label)+'</span><b>'+escape(str(value))+'</b><small>'+escape(detail)+'</small></div>' for label,value,detail in items)+'</div>')


def header(index,subtitle):
    html('<div class="eyebrow">CM KNOWLEDGE OPS &nbsp; / &nbsp; DATAIKU</div><div class="heading"><h1>'+escape(NAV[index])+'</h1>'+badge('운영 콘솔 시안','gray')+'</div><div class="subtitle">'+escape(subtitle)+'</div><div class="preview">설계 미리보기 · 모든 목록·수치·원문·결과는 예시입니다. 승인·편집은 현재 세션에만 반영되며 운영 데이터는 변경되지 않습니다.</div>')


def sidebar():
    with st.sidebar:
        html('<div class="brand"><div class="logo">CM</div><div><b>지식 운영 콘솔</b><small>KNOWLEDGE OPERATIONS</small></div></div><div class="nav-label">MONITOR & REVIEW</div>')
        icons=[':material/monitoring:',':material/fact_check:',':material/route:',':material/menu_book:',':material/account_tree:',':material/science:']
        for i,(name,icon) in enumerate(zip(NAV,icons)):
            if i==3: html('<div class="nav-label">KNOWLEDGE & VALIDATION</div>')
            st.button(str(i)+'  '+name,key='nav_'+name,icon=icon,use_container_width=True,type='primary' if state()['page']==name else 'secondary',on_click=navigate,args=(name,))
        if os.environ.get('GENOS_RAG_ONTOLOGY_CONFIG'):
            html('<div class="side-foot">DATAIKU · ORACLE<br>온톨로지 관리·시뮬레이션 연결 모드<br>다른 메뉴는 설계 미리보기입니다.</div>')
        else:
            html('<div class="side-foot">DATAIKU · ORACLE<br>설계 미리보기 / 실제 승인 미연결</div>')
        with st.expander('연결 상태'):
            st.caption('온톨로지: 설정된 DB·작업 폴더 연결 사용. 나머지 메뉴는 기존 시안입니다.' if os.environ.get('GENOS_RAG_ONTOLOGY_CONFIG') else '온톨로지 설정이 없어 시안 데이터를 표시합니다.')
            st.caption('배치 모니터의 Oracle 점검만 기존 읽기 전용 연결 예시입니다.')


def queue(collection):
    for item in state()[collection]:
        with st.container(border=True,key='panel_queue_'+item['id']):
            html(badge(item['status'],tone(item['status']))+'<div class="title">'+escape(item['title'])+'</div>')
            st.caption(item.get('document',item.get('scope',item['id'])))
            chosen=state()['focus_'+collection]==item['id']
            st.button('선택됨' if chosen else '검토하기 →',key='select_'+item['id'],type='primary' if chosen else 'secondary',use_container_width=True,on_click=navigate,args=(state()['page'],collection,item['id']))
    return next(x for x in state()[collection] if x['id']==state()['focus_'+collection])


def decision(item,area,eligible=True):
    if item['status'] in {'승인','반려'}:
        st.success('이 예시의 검토 처리가 기록되었습니다: '+item['status'])
        st.caption(item.get('opinion',''))
        return
    with st.form('decision_'+item['id']):
        st.markdown('### 검토 의견')
        reason=st.text_area('승인·보류·반려 사유',key='reason_'+item['id'],height=70,max_chars=1000,placeholder='원문 대조 결과 또는 추가 확인할 내용을 남겨주세요.')
        checked=st.checkbox('원문·버전·적용 범위를 확인했습니다',key='checked_'+item['id'],disabled=not eligible)
        c1,c2,c3=st.columns(3)
        approve=c1.form_submit_button('승인',type='primary',disabled=not eligible,use_container_width=True)
        hold=c2.form_submit_button('보류',use_container_width=True)
        reject=c3.form_submit_button('반려',use_container_width=True)
        if approve or hold or reject:
            if not reason.strip() or (approve and not checked):
                st.error('검토 사유를 입력하고, 승인할 때는 원문·버전·적용 범위 확인에 체크하세요.')
            elif approve and not eligible:
                st.error('미완료 실행은 재사용 승인할 수 없습니다.')
            else:
                item['status']='승인' if approve else '보류' if hold else '반려'
                item['opinion']=reason.strip()
                record(area,item['id'],item['status'],reason.strip())
                st.rerun()
    st.caption('예시 상태만 변경됩니다. 실제 승인은 원문·권한·버전을 서버에서 다시 검증합니다.')


def render_pipeline():
    header(0,'중계서버에서 Oracle 적재까지, 멈춘 단계와 오늘 처리할 검토를 확인합니다.')
    knowledge_count=sum(x['status']!='게시됨' for x in state()['wikis'])+len(state()['ontologies'])
    metrics([('배치 확인 필요',1,'구조화 단계의 검토 대기'),('구조화 검토 대기',pending('structures'),'원문 대조 후 보완안 승인'),('숏컷 검토 대기',pending('shortcuts'),'재사용 범위·근거 확인'),('지식 검토 필요',knowledge_count,'위키 · 온톨로지 후보')])
    main,aside=st.columns([2.05,1],gap='large')
    with main:
        status_tab,oracle_tab,history_tab=st.tabs(['배치 실행 현황','Oracle 점검','검토 이력'])
        with status_tab:
            with st.container(border=True,key='panel_pipeline'):
                st.markdown('### 오늘의 배치 흐름')
                st.caption('예시 일일 배치 · 2026.10.21 06:00 · DAILY-1021')
                nodes=[('01','중계서버','응답 수신','24건 확인',False),('02','Dataiku 수집','입력 대조','24건 수집',False),('03','구조화','검토 대기','21건 완료 · 3건 대기',True),('04','색인·연결','완료 건 처리','21건 반영',False),('05','Oracle 적재','완료 건 적재','21건 반영',False)]
                html('<div class="pipeline">'+''.join('<div class="stage '+('warn' if warn else '')+'"><small>'+n+'</small><b>'+name+'</b>'+badge(detail,'amber' if warn else '')+'<small>'+number+'</small></div>' for n,name,detail,number,warn in nodes)+'</div>')
                html('<div class="callout"><b>구조화 3건이 검토 단계로 분리되었습니다.</b><br>완료된 21건은 적재되었고, 누락 후보 3건은 보완 승인 뒤 재처리 대상으로 연결합니다. 아래 흐름은 고정된 배치 예시입니다.</div>')
                st.button('구조화 누락 검토하기 →',key='pipeline_to_structure',on_click=navigate,args=(NAV[1],),use_container_width=True)
            st.markdown('### 실행별 상태')
            run=st.selectbox('실행 선택',['DAILY-1021 · 일일 외규 수집','PORTAL-1020 · 내규 입력'],label_visibility='collapsed')
            rows=([{'단계':'중계서버 → Dataiku','입력':24,'완료':24,'상태':'완료','최근 기록':'06:03'},{'단계':'구조화','입력':24,'완료':21,'상태':'검토 분리 3','최근 기록':'06:08'},{'단계':'색인 → Oracle','입력':21,'완료':21,'상태':'완료','최근 기록':'06:14'}] if run.startswith('DAILY') else [{'단계':'포탈 → Dataiku → Oracle','입력':2,'완료':2,'상태':'완료','최근 기록':'어제 17:42'}])
            st.dataframe(rows,hide_index=True,use_container_width=True)
            with st.expander('선택한 실행의 로그·재개 계획'):
                st.code('DEMO / '+run+'\n수집 → 구조화 → 검토 대상 분리 → 완료 건 적재\n승인 결과가 확정된 대상만 후속 재처리에 전달',language=None)
                st.button('실제 재처리 · 배치 API 연결 필요',disabled=True)
        with oracle_tab:
            oracle_inspector()
        with history_tab:
            if state()['events']: st.dataframe(state()['events'],hide_index=True,use_container_width=True)
            else: st.info('아직 이 세션에서 처리한 검토가 없습니다.')
    with aside:
        with st.container(border=True,key='panel_inbox'):
            html('<div class="kicker">REVIEW INBOX</div>')
            st.markdown('### 오늘 확인할 일')
            tasks=[('원문의 누락 보완',str(pending('structures'))+'건 · 표 각주·조항·참조',1),('쌓인 숏컷 검토',str(pending('shortcuts'))+'건 · 완료 상태와 근거 확인',2),('위키 출처 재확인','적용 범위·상충 해석 확인',3),('온톨로지 검증 준비','조건·예외·재개 기준',4)]
            for title,detail,page in tasks:
                html('<div class="line-item"><div>'+title+'<small>'+detail+'</small></div>'+badge('검토','gray')+'</div>')
                st.button('열기 → '+NAV[page],key='inbox_'+str(page),use_container_width=True,on_click=navigate,args=(NAV[page],))
        with st.container(border=True,key='panel_cycle'):
            html('<div class="kicker">VALIDATION LOOP</div><div class="title">승인 다음에는 검증</div><div class="body">원문 보완 → 재사용 지식 검토 → 온톨로지 관리 → 시뮬레이션 → 문제 조건 수정</div>')
            st.button('시뮬레이션 준비 →',on_click=navigate,args=(NAV[5],),use_container_width=True)


def render_structure():
    header(1,'구조화 과정에서 빠진 내용을 원문과 대조하고 보완안을 승인합니다.')
    left,right=st.columns([1,2.25],gap='large')
    with left:
        st.markdown('### 검토 대상')
        st.caption('승인 대기·보류 '+str(pending('structures'))+'건 / 전체 예시 3건')
        item=queue('structures')
    with right:
        html(badge(item['type'],'gray')+' '+badge(item['status'],tone(item['status']))+'<div class="title">'+escape(item['document'])+'</div>')
        st.caption(item['location']+' · 원문 v1 / 구조화 후보 v2 · 가상 문서')
        original,proposed=st.columns(2)
        with original:
            st.markdown('### 원문')
            html('<div class="source">'+escape(item['source'])+'</div>')
        with proposed:
            st.markdown('### 기존 구조화 결과')
            html('<div class="source">'+escape(item['before'])+'</div>')
        st.markdown('### 보완 제안')
        html('<div class="addition">+ '+escape(item['fix'])+'</div>')
        st.caption('승인 후 영향 · '+item['impact'])
        with st.expander('출처·변경 범위'):
            st.write('원문 자체는 유지하고, 선택한 위치의 구조화·참조 결과만 보완 후보로 승인합니다.')
            st.caption('실제 연결 시 문서 ID·원문 해시·구조화 버전·작업 receipt를 함께 검증합니다.')
        decision(item,'구조화')


def render_shortcuts():
    header(2,'사용 중 축적된 조사 경로의 근거와 적용 범위를 확인한 뒤 재사용을 승인합니다.')
    left,right=st.columns([1,2.25],gap='large')
    with left:
        st.markdown('### 새로 쌓인 숏컷')
        st.caption('과거 답변을 정답으로 승인하지 않습니다.')
        item=queue('shortcuts')
    with right:
        html(badge(item['state'],tone(item['state']))+' '+badge(item['status'],tone(item['status']))+'<div class="title">'+escape(item['title'])+'</div>')
        st.caption(item['run']+' · 예시 실행 기록')
        with st.container(border=True,key='panel_shortcut'):
            st.markdown('### 원래 질문과 조사 경로')
            st.write(item['question'])
            html('<div class="route">'+'<i>→</i>'.join('<span>'+escape(x)+'</span>' for x in item['path'])+'</div>')
            st.caption('연결 원문 · '+item['reads'])
            st.caption('재사용 범위 · '+item['scope'])
        st.dataframe([{'확인 항목':'실행 완료 여부','상태':item['state']},{'확인 항목':'원문·버전 참조','상태':'확인 대상' if item['eligible'] else '일부 미확보'},{'확인 항목':'질문·업무 적용 범위','상태':item['scope']},{'확인 항목':'재사용 직전 검사','상태':'사용자 권한·원문 변경 재확인'}],hide_index=True,use_container_width=True)
        if not item['eligible']: st.warning('원문 미확보로 재사용 승인 조건을 충족하지 못했습니다. 보류하거나 반려할 수 있습니다.')
        else: st.caption('승인 대상은 조사 경로와 재사용 조건입니다. 실행 때 권한·원문 버전을 다시 확인합니다.')
        decision(item,'숏컷',item['eligible'])


def render_wiki():
    header(3,'해석 지식과 탐색 경로를 편집하고, 출처·적용 범위·변경 이력을 관리합니다.')
    left,right=st.columns([1,2.25],gap='large')
    with left:
        st.markdown('### 지식 문서')
        item=queue('wikis')
    with right:
        html(badge(item['status'],tone(item['status']))+'<div class="title">'+escape(item['title'])+'</div>')
        st.caption(item['id']+' · 게시 예시 v'+str(item['revision'])+' · '+item['scope'])
        read,edit,sources,history=st.tabs(['문서 보기','편집','근거·연결','버전 이력'])
        with read,st.container(border=True,key='panel_wiki'):
            st.markdown(item['body'])
            st.caption('해석 지식 예시 · 법령 원문 또는 확정된 법률 판단이 아닙니다.')
        with edit:
            draft=state()['wiki_drafts'].get(item['id'],item)
            with st.form('wiki_'+item['id']):
                title=st.text_input('문서 제목',draft['title'],max_chars=120)
                scope=st.text_input('적용 범위',draft['scope'],max_chars=200)
                body=st.text_area('위키 본문',draft['body'],height=220,max_chars=8000)
                note=st.text_input('변경 사유',max_chars=300)
                if st.form_submit_button('초안 저장',type='primary'):
                    if not title.strip() or not body.strip() or not note.strip(): st.error('제목·본문·변경 사유를 입력하세요.')
                    else:
                        state()['wiki_drafts'][item['id']]={**deepcopy(item),'title':title.strip(),'scope':scope.strip(),'body':body.strip(),'note':note.strip()}
                        record('위키',item['id'],'초안 저장',note.strip())
                        st.success('초안을 세션에 저장했습니다. 게시 예시는 유지됩니다.')
            if st.button('초안을 검토 요청',disabled=item['id'] not in state()['wiki_drafts']):
                item['status']='검토 대기'
                record('위키',item['id'],'검토 요청',state()['wiki_drafts'][item['id']]['note'])
                st.rerun()
            if item['id'] in state()['wiki_drafts']:
                with st.expander('저장한 초안 미리보기'): st.markdown(state()['wiki_drafts'][item['id']]['body'])
            st.button('실제 게시 · 관리 API 연결 필요',disabled=True)
        with sources:
            st.write('원문 참조 · '+item['source'])
            st.caption('예시 참조입니다. 실제 원문·버전·해시 검증은 미연결입니다.')
            if st.button('연결된 온톨로지 열기 →'):
                target=next((x for x in state()['ontologies'] if x['wiki']==item['id']),None)
                if target:
                    navigate(NAV[4],'ontologies',target['id']);st.rerun()
                else: st.info('이 예시에 연결된 온톨로지가 없습니다.')
        with history:
            html('<div class="history"><b>v'+str(item['revision'])+' · 현재 게시 예시</b><br>원문 참조와 적용 범위를 연결한 문서</div>')
            events=[e for e in state()['events'] if e['대상']==item['id']]
            if events: st.dataframe(events,hide_index=True,use_container_width=True)
            else: st.caption('이 세션의 추가 변경은 없습니다.')


def ontology_binding(item):
    return hashlib.sha256(json.dumps(item,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def open_simulation(item_id):
    state()['sim_target']=item_id
    st.session_state['simulation_target']=item_id
    navigate(NAV[5])


def edit_problem_condition(item_id,node):
    navigate(NAV[4],'ontologies',item_id)
    st.session_state['node_'+item_id]=node


def graph(item):
    html('<div class="graph"><div class="graph-row"><div class="node">'+escape(item['title'])+'<small>개념 · 검토 방법</small></div></div><div class="arrow">↓</div><div class="graph-row"><div class="node">업무 유형<small>'+escape(item['business'])+'</small></div><div class="node">기준일<small>'+('확인 필요' if item['require_date'] else '필수 입력 아님')+'</small></div><div class="node">원문 · 위키<small>버전 참조</small></div></div><div class="arrow">↓</div><div class="graph-row"><div class="node focus">적용 조건<small>입력 사실과 범위 확인</small></div></div><div class="arrow">↙ &nbsp; ↓ &nbsp; ↘</div><div class="graph-row"><div class="node">조건 충족<small>검토 항목 연결</small></div><div class="node warn">정보 부족<small>'+escape(item['unknown'])+'</small></div><div class="node">제외 조건<small>제외 이유 기록</small></div></div></div>')


def render_ontology():
    if os.environ.get("GENOS_RAG_ONTOLOGY_CONFIG"):
        from ontology_dashboard import render
        return render(embedded=True, initial_page='검토 대시보드')
    header(4,'생성된 개념과 연결 관계를 살펴보고, 조건·제외·재개 기준을 검토합니다.')
    left,right=st.columns([1,2.25],gap='large')
    with left:
        st.markdown('### 온톨로지 목록')
        item=queue('ontologies')
        st.caption('자동 생성 후보는 검토·검증 전까지 초안으로 관리합니다.')
    with right:
        html(badge(item['status'],tone(item['status']))+'<div class="title">'+escape(item['title'])+'</div>')
        st.caption(item['id']+' · 후보 v'+str(item['revision'])+' · 예시 모델')
        relation,condition,references=st.tabs(['관계 보기','조건 편집','근거·영향 범위'])
        with relation:
            graph(item)
            node=st.selectbox('확인할 항목',['적용 조건','미확인 처리','제외·재개','근거 연결'],key='node_'+item['id'])
            descriptions={'적용 조건':'업무 유형과 입력 사실을 확인하고 필요한 검토 항목을 연결합니다.','미확인 처리':'필요한 사실이 없으면 미확인으로 남깁니다. 적용이나 제외로 추정하지 않습니다.','제외·재개':item['exclude']+' '+item['resume'],'근거 연결':'위키와 원문의 버전·권한을 확인합니다. 변경된 참조는 다시 검토합니다.'}
            html('<div class="callout"><b>'+escape(node)+'</b><br>'+escape(descriptions[node])+'</div>')
        with condition:
            with st.form('ontology_'+item['id']):
                title=st.text_input('온톨로지 이름',item['title'],max_chars=120)
                business=st.selectbox('적용 업무',['PF','공통','RP'],index=['PF','공통','RP'].index(item['business']))
                require_date=st.checkbox('기준일 확인 필요',value=item['require_date'])
                unknown=st.selectbox('정보가 부족할 때',['미확인 유지','추가 확인 요청'],index=['미확인 유지','추가 확인 요청'].index(item['unknown']))
                exclude=st.text_area('제외 기준',item['exclude'],height=70,max_chars=1000)
                resume=st.text_area('재개 기준',item['resume'],height=70,max_chars=1000)
                note=st.text_area('수정 사유',height=70,max_chars=1000)
                if st.form_submit_button('새 초안 버전 저장',type='primary'):
                    if not title.strip() or not note.strip(): st.error('온톨로지 이름과 수정 사유를 입력하세요.')
                    else:
                        item.update(title=title.strip(),business=business,require_date=require_date,unknown=unknown,exclude=exclude.strip(),resume=resume.strip(),revision=item['revision']+1,status='초안')
                        record('온톨로지',item['id'],'후보 v'+str(item['revision']),note.strip());st.rerun()
            st.caption('초안이 바뀌면 이전 시뮬레이션 결과로 현재 버전을 통과 처리하지 않습니다.')
        with references:
            st.dataframe([{'연결':'해석 지식','대상':item['wiki'],'상태':'예시 참조'},{'연결':'원문','대상':'예시 문서 v1','상태':'실제 해시 미연결'},{'연결':'검증 사례','대상':'정상·누락·예외·재개','상태':'시뮬레이션에서 확인'}],hide_index=True,use_container_width=True)
        st.button('이 버전으로 시뮬레이션 →',type='primary',use_container_width=True,on_click=open_simulation,args=(item['id'],))
        st.button('실제 게시 · 관리 API 연결 필요',disabled=True,use_container_width=True)


def render_simulation():
    if os.environ.get("GENOS_RAG_ONTOLOGY_CONFIG"):
        from semantic_runtime.ontology_work.ui import render
        return render(simulation=True)
    header(5,'온톨로지 버전과 질문 묶음을 고정하고, 예상한 동작과 실제 결과의 차이를 확인합니다.')
    st.caption('시뮬레이션 화면 시안 · 고정된 예시 결과를 표시하며 엔진·LLM을 실행하거나 실제 품질을 평가하지 않습니다.')
    control,results=st.columns([1,2.25],gap='large')
    with control,st.container(border=True,key='panel_sim_setup'):
        st.markdown('### 검증 설정')
        ids=[x['id'] for x in state()['ontologies']]
        labels={x['id']:x['title'] for x in state()['ontologies']}
        target_id=st.selectbox('온톨로지',ids,index=ids.index(state()['sim_target']),key='simulation_target',format_func=labels.__getitem__)
        item=next(x for x in state()['ontologies'] if x['id']==target_id)
        state()['sim_target']=target_id
        st.caption('선택 후보 v'+str(item['revision'])+' / 원문 참조는 예시')
        suite=st.selectbox('시나리오 묶음',['기본·경계 6개','누락·버전·재개 3개'],key='scenario_suite')
        st.write('정상 입력 · 입력 누락 · 범위 밖 · 예외 · 원문 변경 · 재개')
        st.caption('실제 연결 때는 질문 묶음·기대 결과·자료·예산을 실행 전에 고정합니다.')
        if st.button('결과 화면 미리보기',type='primary',use_container_width=True):
            cases=deepcopy(SCENARIOS if suite.startswith('기본') else [x for x in SCENARIOS if x['id'] in {'T02','T05','T06'}])
            result={'id':'DEMO-SIM-'+str(len(state()['simulations'])+1).zfill(3),'ontology':item['id'],'title':item['title'],'revision':item['revision'],'binding':ontology_binding(item),'suite':suite,'cases':cases}
            state()['simulation']=result
            state()['simulations'].insert(0,deepcopy(result))
            record('시뮬레이션',result['id'],'결과 미리보기','고정 예시 · 엔진 실행 없음')
        st.button('실제 시뮬레이션 · 실행 API 연결 필요',disabled=True,use_container_width=True)
    with results:
        result=state()['simulation']
        if result is None:
            with st.container(border=True,key='panel_sim_empty'):
                st.markdown('### 검증할 버전과 시나리오를 선택하세요')
                html('<div class="body">정상 동작뿐 아니라 누락된 사실, 적용 제외, 원문 변경, 조사 재개를 확인합니다.</div>')
                st.dataframe([{'유형':x['case'],'입력':x['input'],'기대 동작':x['expected']} for x in SCENARIOS],hide_index=True,use_container_width=True)
                st.caption('승인된 정답이 없는 질문은 정답률로 평가하지 않고 동작·근거·미확인 상태를 구분합니다.')
            return
        bound=next(x for x in state()['ontologies'] if x['id']==result['ontology'])
        stale=result['binding']!=ontology_binding(bound)
        different=item['id']!=result['ontology'] or suite!=result['suite']
        st.markdown('### '+result['title']+' · 결과 예시')
        st.caption(result['id']+' · 후보 v'+str(result['revision'])+' · '+result['suite'])
        if stale: st.warning('온톨로지가 수정되었습니다. 이 결과는 이전 버전의 예시이며 현재 후보를 검증하지 않습니다.')
        if different: st.info('설정과 표시 중인 결과의 대상이 다릅니다. 선택한 설정의 결과를 보려면 다시 미리보기 하세요.')
        counts={k:sum(x['status']==k for x in result['cases']) for k in ('일치','불일치','미확인')}
        metrics([('검증 사례',len(result['cases']),'고정 결과 예시'),('기대 동작 일치',counts['일치'],'법률 정답률 아님'),('불일치',counts['불일치'],'문제 조건 검토'),('미확인',counts['미확인'],'원문·범위 추가 확인')])
        st.dataframe([{'사례':x['case'],'기대 동작':x['expected'],'관찰 결과 예시':x['observed'],'상태':x['status']} for x in result['cases']],hide_index=True,use_container_width=True)
        case_id=st.selectbox('사례 상세',[x['id'] for x in result['cases']],index=next(i for i,x in enumerate(result['cases']) if x['status']=='불일치'),format_func=lambda key:next(x['case'] for x in result['cases'] if x['id']==key))
        case=next(x for x in result['cases'] if x['id']==case_id)
        with st.container(border=True,key='panel_sim_case'):
            html(badge(case['status'],tone(case['status']))+'<div class="title">'+escape(case['case'])+'</div>')
            st.write('입력 · '+case['input'])
            st.write('기대 · '+case['expected']+' / 관찰 예시 · '+case['observed'])
            st.caption('확인할 연결 · '+case['node']+' · 실제 원인 분석 결과가 아닌 UI 예시입니다.')
            st.button('연결된 조건 수정하기 →',use_container_width=True,on_click=edit_problem_condition,args=(result['ontology'],case['node']))
        with st.expander('이 세션의 결과 미리보기 이력'):
            st.dataframe([{'실행':r['id'],'온톨로지':r['title'],'버전':r['revision'],'묶음':r['suite']} for r in state()['simulations']],hide_index=True,use_container_width=True)


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



def main():
    st.set_page_config(page_title="CM · 지식 운영 콘솔", page_icon="📑", layout="wide", initial_sidebar_state="expanded")
    html(CSS)
    initialize()
    sidebar()
    dict(zip(NAV, [render_pipeline, render_structure, render_shortcuts, render_wiki, render_ontology, render_simulation]))[state()["page"]]()


if __name__ == "__main__":
    main()
