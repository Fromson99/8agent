"""Collected records → explicit generation → human review, using one workflow."""
from html import escape
from pathlib import Path
from functools import partial
import hashlib
import json
import logging
import os
import sys
import uuid

import streamlit as st
from ontology_dashboard_model import Dashboard, binding

FILTERS = ['검토 대기', '승인 완료', '반려', '전체']
LABELS = {'INPUT': '준비 중', 'DRAFT': '검토 대기', 'APPROVED': '승인 완료', 'REJECTED': '반려'}
STEPS = ['1 · 모인 기록', '2 · 초안 만들기', '3 · 검토·승인']
CSS = """
<style>
.stApp{background:#f8f9fb;color:#202c34}
[data-testid=stHeader]{background:transparent}
[data-testid=stMainBlockContainer]{max-width:1180px;padding:2.6rem 2rem 4rem}
.approval-kicker{color:#77828a;font-size:12px;letter-spacing:.4px;margin-bottom:9px}
.approval-title{font-size:32px;font-weight:650;letter-spacing:-1.1px;line-height:1.35;margin:0 0 8px}
.approval-intro{font-size:15px;color:#6c7780;margin-bottom:24px;line-height:1.7}
.approval-item{padding:13px 0;border-bottom:1px solid #edf0f2}
.approval-item:last-child{border-bottom:0}
.approval-item strong{display:block;font-size:14px;color:#697781;margin-bottom:5px;font-weight:500}
.approval-item p{margin:0;font-size:16px;line-height:1.85;white-space:pre-wrap;overflow-wrap:anywhere}
.approval-status{display:inline-block;font-size:12px;border-radius:4px;padding:4px 8px;background:#edf1f4;color:#62717d;margin-bottom:10px}
.approval-status.DRAFT{background:#fff3d9;color:#88631a}
.approval-status.APPROVED{background:#e7f4ef;color:#1b725a}
.approval-status.REJECTED{background:#fceeed;color:#a45850}
.role-note{padding:12px 15px;background:#edf4f1;border-radius:7px;margin:5px 0 18px;line-height:1.7;font-size:14px}
.role-note strong{display:block;color:#246451;margin-bottom:3px}
.role-note.llm{background:#edf1f8}.role-note.llm strong{color:#475f82}
.approval-gold{border-left:3px solid #cbd3d9;padding:2px 0 2px 14px;margin:18px 0;color:#596976;line-height:1.8;font-size:14px}
.approval-gold strong{display:block;color:#344651;margin-bottom:3px;font-size:15px}
.record-table-scroll{overflow-x:auto;margin:10px 0 18px;border:1px solid #e3e8ec;border-radius:7px}
.record-table{width:100%;border-collapse:collapse;font-size:14px;line-height:1.75;table-layout:fixed}
.record-table th{text-align:left;background:#f2f5f7;color:#53616b;font-weight:600}
.record-table th,.record-table td{padding:13px 16px;border-bottom:1px solid #e8edf0;vertical-align:top;overflow-wrap:anywhere;white-space:pre-wrap}
.record-table tr:last-child td{border-bottom:0}.record-table th:first-child{width:64px}
.record-table th:last-child{width:23%}
[data-testid=stVerticalBlockBorderWrapper]>div{border-color:#e3e8ec;background:#fff}
.stButton button,.stFormSubmitButton button{border-radius:7px;min-height:44px}
button[kind=primary],button[kind=primaryFormSubmit]{background:#17745f;border-color:#17745f;color:white}
h2{font-size:22px!important;letter-spacing:-.4px}h3{font-size:17px!important}
[data-testid=stForm]{border:0;padding:0;margin-top:12px}
@media(max-width:800px){[data-testid=stMainBlockContainer]{padding:1.2rem 1rem 3rem}.approval-title{font-size:27px}.record-table{min-width:700px}}
</style>
"""


def html(value):
    st.markdown(value, unsafe_allow_html=True)


def failure(stage):
    reference = uuid.uuid4().hex[:10]
    logging.getLogger('ontology_dashboard').exception('%s reference=%s', stage, reference)
    st.error(f'{stage}을 완료하지 못했습니다. 다시 확인해 주세요.')
    st.caption(f'담당자에게 전달할 확인 번호: {reference}')


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


def select_table_row(key, ids):
    # Streamlit returns original row positions, including after browser sorting.
    # Capture this table's exact ID order; never map an old event to new rows.
    selected = st.session_state.get(key, {}).get('selection', {}).get('rows', [])
    if len(selected) == 1 and type(selected[0]) is int and 0 <= selected[0] < len(ids):
        st.session_state.od_bundle = ids[selected[0]]


def record_list(rows, scope):
    snapshot = [(d['bundle_id'], d['revision'], d['work_hash'], d['status']) for d in rows]
    digest = hashlib.sha256(json.dumps(snapshot).encode()).hexdigest()[:20]
    key = 'od_table_'+scope+'_'+digest
    data = [{'항목명': d['input']['concept'],
             '상태': '초안 만들기 전' if d['status'] == 'INPUT' else LABELS[d['status']],
             '기록 수': len(d['input']['judgments']),
             '근거 원문': ' · '.join(s['anchor']['label'] for s in d['input']['originals'])}
            for d in rows]
    st.caption(f'총 {len(rows)}건 · 행 왼쪽을 선택하면 아래에서 내용을 확인할 수 있습니다.')
    st.dataframe(data, hide_index=True, use_container_width=True,
                 height=min(446, 42 + 45 * len(rows)), row_height=45,
                 column_config={'항목명': st.column_config.TextColumn(width='large'),
                                '상태': st.column_config.TextColumn(width='small'),
                                '기록 수': st.column_config.NumberColumn(width='small', format='%d건'),
                                '근거 원문': st.column_config.TextColumn(width='medium')},
                 key=key, selection_mode='single-row',
                 on_select=partial(select_table_row, key, tuple(d['bundle_id'] for d in rows)))


def judgment_table(document):
    sources = {s['id']: s for s in document['input']['originals']}
    body = []
    for number, record in enumerate(document['input']['judgments'], 1):
        judgment = record['judgment']
        values = [number, judgment.get('finding') or '판단 내용 미기록',
                  judgment.get('reason') or '사유 미기록',
                  ' · '.join(sources[i]['anchor']['label'] for i in record['source_ids'])]
        body.append('<tr>'+''.join('<td>'+escape(str(value))+'</td>' for value in values)+'</tr>')
    html('<div class="record-table-scroll"><table class="record-table" aria-label="선택한 조사 기록">'
         '<thead><tr><th scope="col">번호</th><th scope="col">판단 내용</th><th scope="col">판단 이유</th><th scope="col">근거 원문</th></tr></thead>'
         '<tbody>'+''.join(body)+'</tbody></table></div>')


def navigate(step, bid=None, review_filter=None):
    st.session_state.od_next_step = step
    if bid is not None:
        st.session_state.od_bundle = bid
    if review_filter is not None:
        st.session_state.od_next_filter = review_filter


def role(who, description, llm=False):
    html('<div class="role-note'+(' llm' if llm else '')+'"><strong>'+escape(who)+'</strong>'+escape(description)+'</div>')


def open_review(document):
    target = LABELS[document['status']]
    navigate(STEPS[2], document['bundle_id'], target if target in FILTERS else '전체')


def collected(api, rows):
    role('사람이 할 일 · 기록 선택', '초안에 사용할 원문과 조사 기록을 확인하고 다음 단계로 넘기세요.')
    st.caption('온톨로지 준비함에 등록된 기록입니다. 전체 숏컷 저장소의 자동 수집·병합은 아직 연결 전입니다.')
    if not rows:
        st.info('아직 모인 기록이 없습니다. 조사 기록이 준비함에 등록되면 여기에 나타납니다.')
        return
    ordered = sorted(rows, key=lambda d: (d['status'] != 'INPUT', d['bundle_id']))
    if st.session_state.get('od_bundle') not in [d['bundle_id'] for d in ordered]:
        st.session_state.od_bundle = ordered[0]['bundle_id']
    record_list(ordered, 'collected')
    with st.container(border=True):
        try:
            d = api.load(st.session_state.od_bundle)
            st.caption('선택한 기록')
            st.subheader(d['input']['concept'])
            st.caption(f"조사 기록 {len(d['input']['judgments'])}건 · 근거 원문 {len(d['input']['originals'])}개")
            judgment_table(d)
            with st.expander('근거 원문 보기'):
                for source in d['input']['originals']:
                    st.markdown('**'+escape(source['anchor']['label'])+'**')
                    st.text(source['text'])
            if d['status'] == 'INPUT':
                st.button('이 기록으로 초안 만들기', type='primary', use_container_width=True,
                          on_click=navigate, args=(STEPS[1], d['bundle_id']))
                st.caption('다음 화면에서 생성 버튼을 눌러야 처리가 시작됩니다.')
            else:
                st.caption('이 기록으로 만든 초안이 이미 있습니다.')
                st.button('초안 검토하기', type='primary', on_click=open_review, args=(d,))
        except Exception:
            failure('수집 기록 확인')


def generate_draft(api, rows):
    bid = st.session_state.get('od_bundle')
    if bid not in [d['bundle_id'] for d in rows]:
        st.info('먼저 초안에 사용할 기록을 선택하세요.')
        st.button('모인 기록 보기', on_click=navigate, args=(STEPS[0],))
        return
    try:
        d = api.load(bid)
    except Exception:
        failure('선택 기록 확인')
        return
    st.subheader(d['input']['concept'])
    if d['status'] != 'INPUT':
        st.success('초안이 준비됐습니다. 사람이 내용을 확인하고 승인해야 합니다.' if d['status'] == 'DRAFT' else '이미 검토한 초안입니다.')
        st.caption(f"검토할 항목 {len((d.get('proposal') or {}).get('components', []))}개 · 근거 원문 {len(d['input']['originals'])}개")
        st.button('초안 검토하기', type='primary', use_container_width=True, on_click=open_review, args=(d,))
        return
    role('사람이 할 일 · 생성 시작', '선택한 기록이 맞는지 확인한 뒤 아래 버튼을 누르세요.')
    role('LLM이 할 일 · 초안 작성', '원문과 조사 기록에서 조건·예외·근거를 정리합니다. 승인 여부는 판단하지 않습니다.', llm=True)
    st.caption(f"선택된 조사 기록 {len(d['input']['judgments'])}건 · 근거 원문 {len(d['input']['originals'])}개")
    if api.demo:
        st.info('체험 모드에서는 준비된 예시로 흐름을 확인합니다. 실제 LLM을 호출하지 않습니다.')
    key = 'od_generation_'+d['work_hash']
    attempt = st.session_state.get(key)
    if attempt:
        st.warning('생성 결과 확인이 필요합니다. 중복 생성을 막기 위해 이 화면에서는 다시 실행하지 않습니다.')
        st.caption('담당자가 저장된 생성 기록을 확인한 뒤 이어서 처리해야 합니다.')
    if api.workflow.generate is None:
        st.info('초안 생성 모델이 아직 연결되지 않았습니다. 담당자가 연결하면 사용할 수 있습니다.')
    label = '예시 초안 만들기' if api.demo else 'LLM으로 초안 만들기'
    clicked = st.button(label, type='primary', use_container_width=True,
                        disabled=bool(attempt) or api.workflow.generate is None, key='od_generate_'+d['work_hash'])
    if clicked and not attempt and api.workflow.generate is not None:
        st.session_state[key] = 'STARTED'
        try:
            with st.spinner('예시 초안을 준비하고 있습니다.' if api.demo else 'LLM이 초안을 작성하고 있습니다. 완료되면 검토할 수 있습니다.'):
                api.propose(binding(d))
        except Exception:
            st.session_state[key] = 'RESULT_CHECK_REQUIRED'
            failure('초안 생성')
            st.warning('자동으로 다시 생성하지 않습니다. 담당자가 저장 결과를 먼저 확인해 주세요.')
        else:
            st.session_state[key] = 'DRAFT_CREATED'
            st.session_state.od_notice = '예시 초안을 준비했습니다. 실제 LLM 호출은 없습니다.' if api.demo else '초안을 저장했습니다. 다음은 사람이 검토할 차례입니다.'
            st.rerun()
    st.caption('완성된 초안은 검토 대기로 저장됩니다. 자동 승인하거나 골드에 반영하지 않습니다.')


def decide(api, document, approve, reason):
    try:
        api.review(binding(document), approve, reason)
    except Exception:
        failure('승인 저장' if approve else '반려 저장')
        return
    st.session_state.od_next_filter = '승인 완료' if approve else '반려'
    st.session_state.od_notice = ('승인했습니다. 골드 반영은 담당자가 별도로 진행합니다.'
                                 if approve else '반려했습니다. 검토 의견을 저장했습니다.')
    st.rerun()


def evidence(document):
    with st.expander('근거 원문 보기'):
        for source in document['input']['originals']:
            st.markdown('**'+escape(source['anchor']['label'])+'**')
            st.text(source['text'])
            st.caption('자료 버전: '+source['anchor']['version'])
            quoted = []
            for item in document['proposal']['components']:
                for basis in item['basis']:
                    if basis['source'] == source['id'] and basis['quote'] not in quoted:
                        quoted.append(basis['quote'])
            for quote in quoted:
                st.caption('인용: '+quote)
    with st.expander('어떤 경우에 사용하는 내용인가요?'):
        by_id = {c['id']: c for c in document['proposal']['components']}
        for path in document['proposal']['paths']:
            st.markdown('**'+escape(path['title'])+'**')
            st.write(path['business_use'])
            for key, label in [('conditions', '적용 조건'), ('calculations', '산정 기준'),
                               ('outcomes', '결과'), ('notes', '검토 메모')]:
                if path[key]:
                    st.caption(label)
                    for cid in path[key]:
                        st.write(by_id[cid]['text'])


def review(api, document):
    status = document['status']
    html('<span class="approval-status '+status+'">'+LABELS[status]+'</span>')
    st.subheader(document['input']['concept'])
    st.caption(' · '.join(s['anchor']['label'] for s in document['input']['originals']))
    if status == 'INPUT':
        st.info('검토할 내용이 아직 준비되지 않았습니다.')
        return
    try:
        # Validate the complete recipe and exact sources before showing decisions.
        api.workflow.preview(document['bundle_id'])
    except Exception:
        failure('원문 확인')
        return
    for item in document['proposal']['components']:
        html('<div class="approval-item"><strong>'+escape(item['id'])+'</strong><p>'+escape(item['text'])+'</p></div>')
    st.write('')
    evidence(document)
    if status == 'DRAFT':
        role('사람이 할 일 · 검토·승인', '아래 내용과 원문을 확인하고 승인하거나, 수정할 이유를 적어 반려하세요.')
        st.divider()
        with st.form('review_'+document['bundle_id']+'_'+str(document['revision'])+'_'+document['work_hash'][:8]):
            confirmed = st.checkbox('내용과 근거 원문을 확인했습니다.', key='od_confirm_'+document['work_hash'])
            reason = st.text_area('검토 의견', placeholder='의견을 남겨 주세요. 반려할 때는 이유가 필요합니다.',
                                  height=85, max_chars=4000, key='od_reason_'+document['work_hash'])
            a, b = st.columns(2)
            approve = a.form_submit_button('승인', type='primary', use_container_width=True)
            reject = b.form_submit_button('반려', use_container_width=True)
            st.caption('승인한 내용은 골드 적재·검증을 거친 뒤 서비스에 반영됩니다.')
            if approve and not confirmed:
                st.warning('내용과 근거 원문을 확인한 뒤 체크해 주세요.')
            elif reject and not reason.strip():
                st.warning('반려 이유를 적어 주세요.')
            elif approve or reject:
                decide(api, document, approve, reason.strip() or '내용과 근거 원문을 확인하고 승인합니다.')
    elif status == 'APPROVED':
        html('<div class="approval-gold"><strong>다음 단계 · 골드 반영</strong>내용 승인은 끝났습니다. 담당자가 골드에 적재하고 검증한 뒤 서비스에 반영합니다.</div>')
        st.caption('이 화면에서는 골드 반영 완료 여부를 확인할 수 없습니다.')
    elif status == 'REJECTED':
        st.info('수정이 필요한 항목입니다. 보완한 뒤 다시 검토합니다.')
    if status in ('APPROVED', 'REJECTED'):
        try:
            events, _ = api.events(document['bundle_id'])
            decision = next((e for e in events if e['revision'] == document['revision'] and
                             e['action'] == ('APPROVED' if status == 'APPROVED' else 'REJECTED')), None)
            if decision and decision.get('reason'):
                st.caption('검토 의견')
                st.write(decision['reason'])
        except Exception:
            st.caption('검토 의견을 불러오지 못했습니다.')


def render(*, embedded=False, initial_page=None):
    html(CSS)
    html('<div class="approval-kicker">온톨로지 관리</div><div class="approval-title">기록에서 승인까지</div><div class="approval-intro">기록을 고르면 LLM이 초안을 만들고, 사람이 최종 승인합니다.</div>')
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
        failure('검토 목록 조회')
        return
    if api.demo:
        st.caption('체험용 예시 · 실제 LLM 호출과 운영 데이터 변경은 없습니다.')
    if st.session_state.get('od_notice'):
        st.success(st.session_state.pop('od_notice'))
    if st.session_state.get('od_next_filter'):
        st.session_state.od_filter = st.session_state.pop('od_next_filter')
    if st.session_state.get('od_next_step'):
        st.session_state.od_step = st.session_state.pop('od_next_step')
    if st.session_state.get('od_step') not in STEPS:
        st.session_state.od_step = STEPS[0]
    step = st.radio('진행 단계', STEPS, horizontal=True, key='od_step', label_visibility='collapsed')
    if step == STEPS[0]:
        collected(api, rows)
        return
    if step == STEPS[1]:
        generate_draft(api, rows)
        return
    if st.session_state.get('od_filter') not in FILTERS:
        st.session_state.od_filter = FILTERS[0]
    selected_filter = st.radio('보기', FILTERS, horizontal=True, key='od_filter', label_visibility='collapsed')
    visible = [d for d in rows if selected_filter == '전체' or LABELS[d['status']] == selected_filter]
    if not visible:
        st.info('검토할 항목이 없습니다.' if selected_filter == '검토 대기' else '이 상태의 항목이 없습니다.')
        return
    ids = [d['bundle_id'] for d in visible]
    if st.session_state.get('od_bundle') not in ids:
        st.session_state.od_bundle = ids[0]
    record_list(visible, 'review_'+selected_filter)
    with st.container(border=True):
        try:
            review(api, api.load(st.session_state.od_bundle))
        except Exception:
            failure('검토 내용 조회')


def main():
    st.set_page_config(page_title='기록에서 승인까지', page_icon='✓', layout='wide', initial_sidebar_state='collapsed')
    render()
