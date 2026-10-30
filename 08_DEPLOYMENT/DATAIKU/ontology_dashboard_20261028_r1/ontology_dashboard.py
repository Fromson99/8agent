"""Native Streamlit ontology dashboard, shared by standalone and existing app."""
from copy import deepcopy
from html import escape
from pathlib import Path
import hashlib
import json
import logging
import os
import sys
import uuid

import streamlit as st
import plotly.graph_objects as go
from ontology_dashboard_model import Dashboard, STATUS, binding, project, component_diff, scenario

PAGES = ['검토 대시보드', '개념 검토', '조사·재지시', '골드 이관', '게시 이력', '가정 비교']
CSS = """
<style>
.stApp{background:#f5f7fa;color:#1c3443}
[data-testid=stMainBlockContainer]{max-width:1540px;padding:2.1rem 2.5rem 4rem}
[data-testid=stHeader]{background:transparent}
[data-testid=stSidebar]{background:#142d3b}
[data-testid=stSidebar] p,[data-testid=stSidebar] label,[data-testid=stSidebar] h2{color:#e4eef2}
[data-testid=stSidebar] [data-testid=stCaptionContainer] p{color:#a9c3ce}
.od-brand{color:#e9faf7;font-size:23px;font-weight:600;margin:8px 0 6px}
.od-eyebrow{color:#647e8d;font-size:12px;letter-spacing:1.4px;margin-bottom:8px}
.od-title{font-size:30px;font-weight:600;letter-spacing:-1px;margin:0 0 6px;line-height:1.4}
.od-sub{color:#687e8a;font-size:14px;margin-bottom:24px;line-height:1.7}
.od-tag{display:inline-block;padding:4px 9px;background:#e6f3ef;color:#206d62;border-radius:5px;font-size:12px;margin-right:7px}
.od-tag.amber{background:#fff2d9;color:#8c631b}.od-tag.gray{background:#eaf0f4;color:#55707e}
.od-step{padding:14px;background:white;border:1px solid #e0e8ed;border-radius:8px;margin-bottom:8px;font-size:14px}
.od-step small{display:block;margin-top:7px;color:#6f8591;line-height:1.7}
.od-source{white-space:pre-wrap;overflow-wrap:anywhere;background:#f0f4f7;border-left:3px solid #7895a5;padding:15px;line-height:1.9;font-size:14px;margin:10px 0}
.od-quote{white-space:pre-wrap;overflow-wrap:anywhere;background:#eaf5f1;border-left:3px solid #25877c;padding:12px;line-height:1.8;font-size:14px;margin:10px 0}
[data-testid=stMetric]{background:white;border:1px solid #dfe7ec;border-radius:10px;padding:17px 20px}
[data-testid=stMetricValue]{font-weight:500;font-size:32px}
[data-testid=stVerticalBlockBorderWrapper]>div{border-color:#dfe7ec}
div[data-testid=stVerticalBlockBorderWrapper]{border-radius:10px}
.stButton button,.stDownloadButton button{border-radius:7px;min-height:40px}
button[kind=primary],button[kind=primaryFormSubmit]{background:#087f80;border-color:#087f80;color:white}
h2{font-size:23px!important}h3{font-size:18px!important}
[data-testid=stForm]{background:white;border-radius:10px}
@media(max-width:800px){[data-testid=stMainBlockContainer]{padding:1.2rem 1rem 3rem}.od-title{font-size:25px}}
</style>
"""


def html(value):
    st.markdown(value, unsafe_allow_html=True)


def tag(text, tone=''):
    return '<span class="od-tag '+tone+'">'+escape(str(text))+'</span>'


def failure(stage):
    reference = uuid.uuid4().hex[:10]
    logging.getLogger('ontology_dashboard').exception('%s reference=%s', stage, reference)
    st.error(f'{stage}을 완료하지 못했습니다. 확인 번호: {reference}')
    st.caption('현재 판본·원문·권한을 새로 확인하세요. 자동 재시도하지 않습니다. 상세 원인은 Dataiku 백엔드 로그에 남습니다.')


def backend():
    root = Path(os.environ.get('GENOS_ONTOLOGY_CODE_ROOT', Path(__file__).resolve().parents[3]))
    backend_path = str(root / '02_BACKEND')
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)
    demo = os.environ.get('ONTOLOGY_DASHBOARD_DEMO') == '1'
    if demo:
        if os.environ.get('GENOS_RAG_ONTOLOGY_CONFIG'):
            raise ValueError('Demo and production settings must not be enabled together')
        if 'od_demo' not in st.session_state:
            from ontology_dashboard_demo import create_demo
            st.session_state.od_demo = create_demo()
        return st.session_state.od_demo[0]
    from semantic_runtime.ontology_work.configuration import workflow
    from semantic_runtime.ontology_work.ui import actor
    return Dashboard(workflow(actor=actor()))


def navigate(page, bid=None):
    st.session_state.od_page = page
    if bid:
        st.session_state.od_bundle = bid


def action(call, success):
    try:
        call()
    except Exception:
        failure('요청 처리')
    else:
        st.session_state.od_notice = success
        st.rerun()


def overview(api, rows):
    counts = [(label, sum(d['status'] == status for d in rows)) for status, label in
              [('DRAFT', '검토 대기'), ('APPROVED', '내용 승인'), ('INPUT', '생성 대기')]]
    counts.append(('기존 게시 있음', sum(bool(d['head']['publication_id']) for d in rows)))
    for col, (label, count) in zip(st.columns(4), counts):
        col.metric(label, count)
    st.caption('접근 가능한 묶음 기준 · 내용 승인과 DB 게시를 따로 집계합니다.')
    left, right = st.columns([2.4, 1], gap='large')
    with left:
        st.subheader('다음 검토할 지식')
        search = st.text_input('개념·원문 검색', placeholder='개념 이름 또는 원문 이름을 입력하세요')
        status = st.radio('상태', ['전체', *STATUS.values()], horizontal=True, key='od_filter')
        visible = [d for d in rows if (status in ('전체', None) or STATUS[d['status']] == status)
                   and search.casefold() in (d['input']['concept'] + ' '.join(s['anchor']['label'] for s in d['input']['originals'])).casefold()]
        order = {'DRAFT': 0, 'APPROVED': 1, 'INPUT': 2, 'REJECTED': 3}
        for d in sorted(visible, key=lambda d: (order[d['status']], d['bundle_id'])):
            with st.container(border=True):
                main, button = st.columns([4, 1])
                with main:
                    html(tag(STATUS[d['status']], 'amber' if d['status'] == 'DRAFT' else 'gray') + tag('r'+str(d['revision']), 'gray'))
                    st.markdown('**'+d['input']['concept']+'**')
                    st.caption(' · '.join(s['anchor']['label'] for s in d['input']['originals']))
                    st.caption(f"원문 {len(d['input']['originals'])}개 · 판단 {len(d['input']['judgments'])}개 · 경로 {len((d.get('proposal') or {}).get('paths', []))}개")
                button.button('검토 열기', key='open_'+d['bundle_id'], use_container_width=True,
                              on_click=navigate, args=('개념 검토', d['bundle_id']))
        if not visible:
            st.info('이 조건에 해당하는 검토 항목이 없습니다.')
    with right:
        st.subheader('골드까지의 진행 순서')
        for title, desc in [('01 · 내용 검토', '원문·조건·예외·변경점을 확인'), ('02 · 모델·메타 승인 확인', '기존 승인 모델 또는 신규 신청'),
                            ('03 · 골드 적재·검증', '매핑 후 Dataiku에서 적재'), ('04 · 사용 판본 전환', '검증된 게시본부터 RAG가 사용')]:
            html('<div class="od-step">'+title+'<small>'+desc+'</small></div>')
        st.info('내용 승인만으로 RAG에 노출되지 않습니다.')
        st.button('골드 이관함 열기', use_container_width=True, on_click=navigate, args=('골드 이관',))
    with st.expander('원문·판단 작업 등록'):
        file = st.file_uploader('ontology-work-v1 JSON', type=['json'], key='od_upload')
        if st.button('작업 등록', disabled=file is None):
            def register():
                if file.size > 2_000_000:
                    raise ValueError('work size limit')
                item = api.workflow.enqueue(json.loads(file.getvalue()))
                navigate('개념 검토', item['bundle_id'])
            action(register, '원문·판단 작업을 등록했습니다.')


def graph_figure(projection, selected, emphasis):
    nodes = projection['nodes'][:36]
    kinds = ['근거 원문', '검토 요소', '업무 경로']
    positions = {}
    for x, kind in enumerate(kinds):
        group = [n for n in nodes if n['kind'] == kind]
        for index, n in enumerate(group):
            positions[n['id']] = (x, (index + 1) / (len(group) + 1))
    figure = go.Figure()
    for edge in projection['edges']:
        if edge['from'] not in positions or edge['to'] not in positions:
            continue
        a, b = positions[edge['from']], positions[edge['to']]
        linked = selected in (edge['from'], edge['to'])
        figure.add_trace(go.Scatter(x=[a[0], b[0]], y=[a[1], b[1]], mode='lines',
                                   line={'color': '#188b88' if linked else '#c9d6de', 'width': 2 if linked else 1},
                                   hoverinfo='skip', showlegend=False))
    for kind in kinds:
        group = [n for n in nodes if n['kind'] == kind]
        colors = ['#087f80' if n['id'] == selected else '#e1f2ee' if n.get('changed') else '#e8eef4' for n in group]
        figure.add_trace(go.Scatter(x=[positions[n['id']][0] for n in group], y=[positions[n['id']][1] for n in group],
                                   customdata=[n['id'] for n in group], text=[escape(n['label'][:24]) for n in group],
                                   mode='markers+text', textposition='bottom center',
                                   textfont={'size': 13, 'color': '#243f50'},
                                   marker={'size': 23, 'color': colors, 'symbol': 'square' if kind == '근거 원문' else 'circle',
                                           'opacity': [1 if emphasis == '전체' or n['id'] == selected or
                                                       (emphasis == '변경 항목' and n.get('changed')) or
                                                       (emphasis == '검토 메모' and n.get('review_note')) else .3 for n in group]},
                                   hovertemplate='%{text}<extra></extra>', showlegend=False))
    figure.update_layout(height=340, margin={'l': 70, 'r': 75, 't': 35, 'b': 30},
                         paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                         clickmode='event+select', dragmode=False,
                         xaxis={'visible': False, 'range': [-.45, 2.45], 'fixedrange': True},
                         yaxis={'visible': False, 'range': [1.08, -.05], 'fixedrange': True},
                         annotations=[{'x': i, 'y': 0, 'text': label, 'showarrow': False, 'yshift': 22,
                                       'font': {'color': '#738895', 'size': 12}} for i, label in enumerate(kinds)])
    return figure


def inspect_node(node, d, projection):
    st.subheader(node['label'])
    html(tag(node['kind'], 'gray') + (tag('이번 변경', 'amber') if node.get('changed') else ''))
    st.write(node['text'])
    if node['kind'] == '근거 원문':
        a = node['data']['anchor']
        st.caption('문서 '+a['document_id']+' · 판본 '+a['version']+' · '+a['unit_id'])
    if node['kind'] == '검토 요소':
        sources = {s['id']: s for s in d['input']['originals']}
        for basis in node['data']['basis']:
            source = sources[basis['source']]
            st.caption('인용 · '+source['anchor']['label'])
            html('<div class="od-quote">'+escape(basis['quote'])+'</div>')
            with st.expander('연결 원문 전체 보기 · '+basis['source']):
                st.text(source['text'])
                st.caption('판본 '+source['anchor']['version'])
    related = [e for e in projection['edges'] if node['id'] in (e['from'], e['to'])]
    with st.expander('연결 의미와 방향'):
        for edge in related:
            st.caption(edge['kind']+' · '+edge['from']+' → '+edge['to'])
    st.caption('표시된 선은 근거 인용·구성 의존·경로 포함입니다.')


def review(api, d):
    expected = binding(d)
    if d['status'] == 'INPUT':
        st.info('원문과 판단이 등록되어 있습니다. 시나리오 초안 생성을 기다립니다.')
        if st.button('저장된 판단으로 초안 생성', disabled=api.workflow.generate is None):
            action(lambda: api.propose(expected), '초안을 생성했습니다.')
        for source in d['input']['originals']:
            with st.expander(source['anchor']['label']):
                st.text(source['text'])
        return
    try:
        package = api.workflow.preview(d['bundle_id'])
        previous = api.previous(d)
    except Exception:
        failure('원문·판본·조립 검사')
        return
    projection = project(d, previous)
    node_ids = [n['id'] for n in projection['nodes']]
    by_id = {n['id']: n for n in projection['nodes']}
    prefix = d['bundle_id']+'_'+str(d['revision'])+'_'+d['work_hash'][:8]
    key = 'od_node_'+prefix
    if st.session_state.get(key) not in node_ids:
        st.session_state[key] = next((n['id'] for n in projection['nodes'] if n.get('changed')), node_ids[0])
    main, detail = st.columns([2.1, 1], gap='large')
    with main, st.container(border=True):
        st.subheader('원문에서 업무 경로까지')
        mode = st.radio('표시 방식', ['관계도', '항목표'], horizontal=True, key='od_view')
        emphasis = st.radio('강조', ['전체', '변경 항목', '검토 메모'], horizontal=True, key='od_emphasis')
        if mode == '항목표':
            st.dataframe([{'종류': n['kind'], '항목': n['label'], '내용': n['text'], '변경': n.get('changed', False)}
                          for n in projection['nodes']], hide_index=True, use_container_width=True)
        else:
            chart_key = 'od_graph_'+prefix
            def select_point():
                points = st.session_state[chart_key]['selection']['points']
                if points and points[-1].get('customdata') in by_id:
                    st.session_state[key] = points[-1]['customdata']
            st.plotly_chart(graph_figure(projection, st.session_state[key], emphasis), key=chart_key,
                            on_select=select_point, selection_mode='points', theme=None,
                            config={'displayModeBar': False, 'scrollZoom': False})
            if len(node_ids) > 36:
                st.caption('관계도는 첫 36개 항목만 표시합니다. 전체 항목은 항목표에서 확인하세요.')
        selected = st.selectbox('상세 항목', node_ids, format_func=lambda x: by_id[x]['kind']+' · '+by_id[x]['label'], key=key)
    with detail, st.container(border=True):
        inspect_node(by_id[selected], d, projection)
    selected_paths = st.multiselect('함께 검토할 업무 경로', [p['id'] for p in package['paths']],
                                    default=[p['id'] for p in package['paths']],
                                    format_func=lambda x: next(p['title'] for p in package['paths'] if p['id'] == x), key='od_paths_'+prefix)
    for path in package['paths']:
        if path['id'] in selected_paths:
            with st.expander(path['title']+' · '+path['business_use']):
                st.text(path['body'])
    changes, originals, edit = st.tabs(['판본 비교', '원문·발견 이력', '수정하기'])
    with changes:
        if previous is None:
            st.info('비교할 이전 작업 판본이 없습니다.')
        else:
            st.caption(f"작업 r{previous['revision']} → r{d['revision']} · 이전 작업 판본과 비교하며 현재 사용 판본과 다를 수 있습니다.")
            diff = component_diff(d, previous)
            if diff:
                st.dataframe(diff, hide_index=True, use_container_width=True)
            else:
                st.info('검토 요소의 변경이 없습니다. 경로 변경은 전체 JSON 비교에서 확인하세요.')
            with st.expander('경로·근거를 포함한 전체 비교'):
                a, b = st.columns(2)
                a.json(previous.get('proposal')); b.json(d['proposal'])
    with originals:
        st.caption('발견 실행 '+str(d['input']['origin']['run_id'])+' → 원문·개념 → 작업 r'+str(d['revision']))
        for source in d['input']['originals']:
            st.markdown('**'+source['anchor']['label']+'**')
            html('<div class="od-source">'+escape(source['text'])+'</div>')
        for j in d['input']['judgments']:
            with st.expander(j['id']+' · 발견 당시 판단'):
                st.json(j)
    with edit:
        with st.form('edit_'+prefix):
            draft = st.text_area('시나리오 레시피 JSON', json.dumps(d['proposal'], ensure_ascii=False, indent=2), height=280, key='od_recipe_'+prefix)
            st.caption('저장 시 인용·참조·의존 순환을 다시 검사하고 새 검토 판본을 만듭니다.')
            if st.form_submit_button('새 판본 저장'):
                action(lambda: api.save(expected, json.loads(draft)), '새 판본을 저장했습니다. 다시 검토해 주세요.')
    if d['status'] == 'DRAFT':
        with st.form('review_'+prefix):
            st.subheader('검토 결정')
            reason = st.text_area('검토 의견', placeholder='원문 대조 결과와 남은 확인 사항', max_chars=4000, key='od_reason_'+prefix)
            confirmed = st.checkbox('조립 경로와 조건·산정·예외의 원문 근거를 확인했습니다.', key='od_confirm_'+prefix)
            a, b = st.columns(2)
            approve = a.form_submit_button('내용 승인', type='primary', use_container_width=True)
            reject = b.form_submit_button('보완 요청 · 반려', use_container_width=True)
            if approve or reject:
                if not reason.strip() or (approve and not confirmed):
                    st.warning('검토 의견을 입력하고, 승인할 때는 원문 확인을 체크하세요.')
                else:
                    action(lambda: api.review(expected, approve, reason), '내용 승인 완료 · 골드 적재 전까지 기존 사용 판본을 유지합니다.' if approve else '보완 요청을 기록했습니다.')
    elif d['status'] == 'APPROVED':
        st.success('내용 승인된 판본입니다. 골드 이관 절차를 이어서 진행하세요.')
        st.button('골드 이관 자료 준비', on_click=navigate, args=('골드 이관', d['bundle_id']))


def investigation(api, d):
    st.subheader('발견 당시 판단과 후속 조사')
    st.caption('기록된 판단을 그대로 보여줍니다. 재지시는 검토 초안이며 에이전트 실행은 별도 연결이 필요합니다.')
    token = d['work_hash']
    key = 'od_commands_'+token
    queue = st.session_state.setdefault(key, [])
    for j in d['input']['judgments']:
        with st.container(border=True):
            st.markdown('**'+j['id']+' · '+', '.join(j['source_ids'])+'**')
            st.json(j['judgment'], expanded=True)
            st.caption('발견 실행 · '+str(j['origin'].get('run_id', '기록 없음')))
            if st.button('이 판단을 다시 검토할 대상으로 담기', key='command_'+token+j['id'], disabled=len(queue) >= 3 or any(q['judgment_id'] == j['id'] for q in queue)):
                queue.append({'judgment_id': j['id'], 'binding': list(binding(d)), 'origin': deepcopy(j['origin']), 'status': 'DRAFT_NOT_EXECUTED'})
                st.rerun()
    st.subheader(f'후속 요청 초안 · {len(queue)} / 3')
    note = st.text_area('추가 조사 지시', placeholder='어떤 근거를 다시 확인해야 하는지 적어 주세요.', key='od_command_note_'+token)
    if queue:
        st.json(queue)
        st.download_button('재지시 초안 내려받기', json.dumps({'version': 'ontology-followup-draft-v1', 'demo': api.demo,
                             'commands': queue, 'note': note, 'executable': False}, ensure_ascii=False, indent=2),
                           file_name='followup-draft.json', mime='application/json')
        if st.button('초안 비우기'):
            queue.clear(); st.rerun()


def gold(api, d):
    st.subheader('내용 승인 이후의 골드 이관')
    stages = [('내용 승인', STATUS[d['status']]), ('모델·메타 확인', '외부 승인 기록 확인 필요'),
              ('골드 적재·검증', 'Dataiku 실행 필요'), ('사용 전환', '검증 후 별도 수행')]
    for col, (name, value) in zip(st.columns(4), stages):
        with col:
            html('<div class="od-step">'+escape(name)+'<small>'+escape(value)+'</small></div>')
    st.info('이 화면은 이관 요청 자료를 준비합니다. 운영 골드 적재·사용 전환 결과는 아직 연결되지 않았습니다.')
    st.caption('기존 게시 ID · '+str(api.workflow.repo.head(d['bundle_id'])['publication_id'] or '없음'))
    if d['status'] != 'APPROVED':
        st.warning('현재 작업 판본의 내용 승인이 먼저 필요합니다.')
        st.button('개념 검토로 이동', on_click=navigate, args=('개념 검토', d['bundle_id']))
        return
    expected = binding(d)
    with st.form('transfer_'+d['work_hash']):
        reference = st.text_input('골드 모델·메타 신청 또는 승인 참조', placeholder='현장의 실제 신청 번호 또는 승인 문서 참조')
        note = st.text_area('이관 담당자에게 전달할 내용', placeholder='대상 업무, 기존 모델 재사용 여부, 확인할 컬럼 매핑')
        st.caption('입력한 참조는 담당자 제공 정보로 저장하며 실제 모델 승인으로 자동 판정하지 않습니다.')
        if st.form_submit_button('이관 요청 자료 저장', type='primary'):
            try:
                key, request = api.prepare_transfer(expected, reference, note)
            except Exception:
                failure('이관 요청 자료 저장')
            else:
                st.session_state['od_transfer_'+d['work_hash']] = key
                st.success('이관 요청 자료를 작업 저장소에 저장했습니다. 골드 적재는 아직 수행되지 않았습니다.')
    stored = st.session_state.get('od_transfer_'+d['work_hash'])
    if stored:
        # Reload and recheck the exact approved revision before exposing a download.
        try:
            api.checked(expected)
            request = api.workflow.store.get(stored)
            st.caption('이관 요청 해시 · '+stored)
            st.download_button('이관 요청 JSON 내려받기', json.dumps(request, ensure_ascii=False, indent=2),
                               file_name='gold-transfer-'+d['bundle_id']+'.json', mime='application/json')
        except Exception:
            failure('이관 요청 자료 확인')
    with st.expander('후속 담당자가 확인할 항목'):
        st.write('모델·메타 승인 → 테이블·컬럼 매핑 → SQL 적재 → 행수·해시·원문 검증 → 사용 판본 전환')
        st.caption('승인한 용어·별칭도 같은 골드 절차를 거친 뒤부터 사용합니다.')


def history(api, d):
    st.subheader('게시 포인터와 검토 이력')
    head = api.workflow.repo.head(d['bundle_id'])
    st.write('현재 게시 ID: '+str(head['publication_id'] or '없음'))
    st.caption('게시 포인터 순번 '+str(head['sequence'])+' · 게시됨과 실제 질문에서 사용됨은 별도입니다.')
    events, more = api.events(d['bundle_id'])
    st.dataframe([{'시각': e['at'], '판본': e['revision'], '행동': e['action'], '검토자': e['actor'],
                   '의견': e.get('reason', ''), '게시 ID': e.get('publication_id') or ''} for e in events],
                 hide_index=True, use_container_width=True)
    if more:
        st.caption('최대 200개의 이력을 표시했습니다. 전체 감사 기록은 에이전트 레이어에서 확인하세요.')
    st.info('질문별 RAG 사용 이력은 아직 연결되지 않았습니다. 사용 횟수는 추정해 표시하지 않습니다.')


def what_if():
    st.subheader('같은 입력, 다른 가정')
    st.caption('합성 산술 예시 · 조건은 금액 ≤ 한도 · 실제 법률 판단이나 온톨로지 계산 엔진이 아닙니다.')
    controls, result = st.columns([1, 2], gap='large')
    with controls, st.container(border=True):
        st.markdown('**비교할 입력**')
        limit = st.number_input('가정 한도 · 만원', min_value=0, max_value=1000, value=200, key='od_limit')
        amount = st.number_input('금액 · 만원', min_value=0, max_value=1000, value=150, key='od_amount')
        missing = st.checkbox('금액 미확인', key='od_missing')
    values = scenario(limit, None if missing else amount)
    with result:
        a, b = st.columns(2)
        a.metric('기준 한도 100만원', values['baseline'])
        b.metric('가정 한도 '+str(limit)+'만원', values['scenario'])
        st.markdown('**영향 경로**')
        st.write('한도 입력 → 금액 비교 → 조건 결과')
        if values['scenario'] == 'UNKNOWN':
            st.warning('입력이 미확인이라 조건 결과를 확정할 수 없습니다.')
        elif values['baseline'] != values['scenario']:
            st.info('한도 변경으로 비교 결과가 달라졌습니다.')
        else:
            st.info('현재 입력에서는 비교 결과가 같습니다.')
        st.caption('가정은 이 브라우저 세션에서만 유지됩니다. 원문·승인·골드 게시본은 변경하지 않습니다.')


def render(*, embedded=False, initial_page=None):
    html(CSS)
    try:
        api = backend()
        identity = (api.actor, api.demo, os.environ.get('GENOS_RAG_ONTOLOGY_CONFIG', ''))
        if st.session_state.get('od_identity') != identity:
            for key in list(st.session_state):
                if key.startswith('od_') and key != 'od_demo':
                    del st.session_state[key]
            st.session_state.od_identity = identity
        rows = api.listing()
    except Exception:
        html('<div class="od-title">온톨로지 검토 대시보드</div>')
        failure('워크플로 연결')
        st.info('운영 연결 설정이 필요합니다. 로컬 예시 실행은 ONTOLOGY_DASHBOARD_DEMO=1로 명시하세요.')
        return
    if 'od_page' not in st.session_state:
        st.session_state.od_page = initial_page or '검토 대시보드'
    if embedded:
        st.radio('온톨로지 작업', PAGES, key='od_page', horizontal=True)
    else:
        with st.sidebar:
            html('<div class="od-brand">지식 운영실</div>')
            st.caption('ONTOLOGY WORKSPACE · v4')
            st.divider()
            st.radio('작업 공간', PAGES, key='od_page', label_visibility='collapsed')
            st.divider()
            st.caption('원문을 기준으로 검토하고\n승인된 지식을 재사용합니다.')
            st.caption('검토자 · '+api.actor)
            st.caption('합성 예시 · 세션 전용' if api.demo else 'Dataiku 작업 저장소 연결')
    page = st.session_state.od_page or PAGES[0]
    html('<div class="od-eyebrow">KNOWLEDGE / ONTOLOGY</div><div class="od-title">'+escape(page)+'</div>')
    html('<div class="od-sub">원문과 판단을 연결하고, 검토한 지식을 골드로 이어갑니다.</div>')
    if api.demo:
        st.caption('예시 모드 · 모든 원문·판단·승인은 합성 데이터입니다. 실제 DB·LLM·골드에는 접근하지 않습니다.')
    if st.session_state.get('od_notice'):
        st.success(st.session_state.pop('od_notice'))
    if page == '검토 대시보드':
        overview(api, rows)
        return
    if page == '가정 비교':
        what_if()
        return
    if not rows:
        st.info('접근 가능한 작업이 없습니다. 검토 대시보드에서 원문·판단 작업을 등록하세요.')
        return
    ids = [d['bundle_id'] for d in rows]
    if st.session_state.get('od_bundle') not in ids:
        st.session_state.od_bundle = ids[0]
    # Keep the picker stable when a review changes status; status is shown below.
    labels = {d['bundle_id']: d['input']['concept'] for d in rows}
    bid = st.selectbox('개념 묶음', ids, key='od_bundle', format_func=labels.__getitem__)
    try:
        d = api.load(bid)
        html(tag('작업 r'+str(d['revision']), 'gray')+tag(STATUS[d['status']], 'amber')+
             tag('기존 게시 유지' if api.workflow.repo.head(bid)['publication_id'] else '게시 없음', 'gray'))
        st.caption(d['bundle_id'])
        {'개념 검토': review, '조사·재지시': investigation, '골드 이관': gold, '게시 이력': history}[page](api, d)
    except Exception:
        failure('선택한 작업 표시')


def main():
    st.set_page_config(page_title='온톨로지 · 지식 운영실', page_icon='◈', layout='wide', initial_sidebar_state='expanded')
    render()
