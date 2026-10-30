"""A single approval inbox, shared by Dataiku and the standalone demo."""
from html import escape
from pathlib import Path
import logging
import os
import sys
import uuid

import streamlit as st
from ontology_dashboard_model import Dashboard, binding

FILTERS = ['검토 대기', '승인 완료', '반려', '전체']
LABELS = {'INPUT': '준비 중', 'DRAFT': '검토 대기', 'APPROVED': '승인 완료', 'REJECTED': '반려'}
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
.approval-gold{border-left:3px solid #cbd3d9;padding:2px 0 2px 14px;margin:18px 0;color:#596976;line-height:1.8;font-size:14px}
.approval-gold strong{display:block;color:#344651;margin-bottom:3px;font-size:15px}
[data-testid=stVerticalBlockBorderWrapper]>div{border-color:#e3e8ec;background:#fff}
.stButton button,.stFormSubmitButton button{border-radius:7px;min-height:44px}
button[kind=primary],button[kind=primaryFormSubmit]{background:#17745f;border-color:#17745f;color:white}
h2{font-size:22px!important;letter-spacing:-.4px}h3{font-size:17px!important}
[data-testid=stForm]{border:0;padding:0;margin-top:12px}
@media(max-width:800px){[data-testid=stMainBlockContainer]{padding:1.2rem 1rem 3rem}.approval-title{font-size:27px}}
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


def select_item(bid):
    st.session_state.od_bundle = bid


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
    html('<div class="approval-kicker">온톨로지 관리</div><div class="approval-title">지식 승인</div><div class="approval-intro">등록할 내용을 확인하고 승인 또는 반려하세요.</div>')
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
        st.caption('체험용 예시 · 실제 데이터에는 반영되지 않습니다.')
    if st.session_state.get('od_notice'):
        st.success(st.session_state.pop('od_notice'))
    if st.session_state.get('od_next_filter'):
        st.session_state.od_filter = st.session_state.pop('od_next_filter')
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
    inbox, detail = st.columns([1, 2.25], gap='large')
    with inbox:
        st.caption(f'{selected_filter} · {len(visible)}건')
        for d in visible:
            with st.container(border=True):
                st.button(d['input']['concept'], key='open_'+d['bundle_id'], use_container_width=True,
                          type='primary' if d['bundle_id'] == st.session_state.od_bundle else 'secondary',
                          on_click=select_item, args=(d['bundle_id'],))
                st.caption(LABELS[d['status']]+' · '+str(len(d['input']['originals']))+'개 원문')
    with detail, st.container(border=True):
        try:
            review(api, api.load(st.session_state.od_bundle))
        except Exception:
            failure('검토 내용 조회')


def main():
    st.set_page_config(page_title='지식 승인', page_icon='✓', layout='wide', initial_sidebar_state='collapsed')
    render()
