"""Profile authoring and staged publication in the existing authenticated screen."""
import json
from .configuration import domain_workflow
from .ui import actor
from ..legal_agent.errors import ContractError


def render():
    import streamlit as st
    st.caption('기록 구조화 → 원문 대조·누적 → 내용 승인 → 게시 준비 → 소비 확인 → 활성 전환')
    try:
        w = domain_workflow(actor=actor())
    except Exception as exc:
        st.error('도메인 설정·용어집·운영자 연결을 확인하세요: ' + str(exc)[:400]); return
    try:
        _render(st, w)
    except Exception as exc:
        st.error('작업이 완료되지 않았습니다: ' + str(exc)[:700])
    finally:
        w.glossary.reader.close()


def _render(st, w):
    def visible(prefix):
        result = []
        for row in w.repo.list(prefix=prefix):
            try:
                result.append(w.load(row['bundle_id']))
            except ContractError:
                continue
        return result

    with st.expander('도메인·업무 프로필 등록 및 검토'):
        domain = st.file_uploader('도메인 프로필', type=['json'], key='dp_domain')
        business = st.file_uploader('업무 프로필 (선택)', type=['json'], key='dp_business')
        revision = st.number_input('기존 프로필 작업 판본 (신규는 0)', min_value=0, step=1)
        if domain and st.button('프로필 검증·등록'):
            st.json(w.save_profile(json.loads(domain.getvalue()), json.loads(business.getvalue()) if business else None,
                                   expected_revision=int(revision)))
        for d in visible('dp-'):
            st.write(d['bundle_id'], d['status'], d['revision'])
            st.json({'review': d['profile']['validation_plan'], 'purposes': d['profile']['assembly_plan']})
            reason = st.text_input('프로필 검토 의견', key=d['bundle_id'] + '_reason')
            if d['status'] == 'DRAFT' and st.button('이 프로필 승인', key=d['bundle_id'] + '_approve', disabled=not reason.strip()):
                w.review_profile(d['bundle_id'], d['revision'], d['work_hash'], True, reason); st.rerun()
    profiles = [d for d in visible('dp-') if d['status'] == 'APPROVED']
    if not profiles:
        st.info('승인한 프로필을 등록하면 구조화·누적 작업을 시작할 수 있습니다.'); return
    by_profile = {p['bundle_id']: p for p in profiles}
    chosen = st.selectbox('사용할 승인 프로필', list(by_profile)); profile = by_profile[chosen]
    with st.expander('실제 기록 가져오기·구조화'):
        file = st.file_uploader('기록 JSON: payload, event_id, run_id, sequence', type=['json'], key='dp_raw')
        if file and st.button('원본 기록 저장'):
            st.json(w.import_payload(**json.loads(file.getvalue())))
        raws = visible('raw-')
        if raws:
            raw = st.selectbox('구조화할 원본', [r['bundle_id'] for r in raws])
            labels = st.text_input('용어집에서 조회할 표기 (쉼표로 구분)')
            if st.button('공통 LLM 구조화', disabled=w.generate is None):
                st.json(w.normalize(raw, profile_id=chosen, profile_work_hash=profile['work_hash'],
                                    labels=[s.strip() for s in labels.split(',') if s.strip()]))
    with st.expander('여러 질문의 관찰 누적'):
        observations = visible('obs-')
        ids = st.multiselect('추가할 관찰', [r['bundle_id'] for r in observations])
        originals = st.file_uploader('검토할 원문 배열 JSON', type=['json'], key='dp_originals')
        bid = st.text_input('지식 묶음 ID', value='cb-kb-new')
        rev = st.number_input('현재 지식 작업 판본 (신규는 0)', min_value=0, step=1)
        if st.button('원문 대조·변경안 생성', disabled=not ids or not originals or w.generate is None):
            st.json(w.accumulate(bundle_id=bid, expected_revision=int(rev), profile_id=chosen,
                profile_work_hash=profile['work_hash'], observation_ids=ids, originals=json.loads(originals.getvalue())))
    knowledge = visible('cb-kb-')
    if not knowledge:
        st.info('아직 검토할 지식 묶음이 없습니다.'); return
    selected = st.selectbox('검토할 지식 묶음', [d['bundle_id'] for d in knowledge])
    d = w.load(selected); head = w.repo.head(selected)
    st.write(f"작업 판본 {d['revision']} · {d['status']} · {d['review_state']}")
    st.json(d['diff'])
    with st.expander('원래 관찰·반박·변경 이력·용어 연결'):
        st.json({'observations': d['observation_ledger'], 'history': d['comparison_history'], 'glossary': d['glossary_refs']})
    for source in d['originals']:
        with st.expander(source['anchor']['label']):
            st.text(source['text'])
    preview = w.preview(selected)
    for path in preview['paths']:
        st.subheader(path['title']); st.text(path['body'])
        st.json({'nodes': path['nodes'], 'edges': path['edges'], 'unresolved': path['unresolved']})
    reason = st.text_input('문장·범위·산정·예외·반례 검토 의견', key=selected + str(d['revision']))
    reviewed = st.checkbox('원문과 변경 이력을 확인했습니다.')
    if d['status'] == 'DRAFT':
        yes, no = st.columns(2)
        if yes.button('내용 승인', disabled=not reviewed or not reason.strip()):
            w.review(selected, d['revision'], d['work_hash'], True, reason); st.rerun()
        if no.button('반려', disabled=not reason.strip()):
            w.review(selected, d['revision'], d['work_hash'], False, reason); st.rerun()
    if d['status'] == 'APPROVED' and st.button('승인 판본 게시 준비'):
        receipt = w.stage_publication(selected, d['revision'], d['work_hash'], head['sequence'])
        st.session_state['domain_staged_' + selected] = receipt; st.json(receipt)
    staged = st.session_state.get('domain_staged_' + selected)
    if staged:
        st.write('준비된 게시 ID', staged['publication_id'])
        if st.button('저장·현재 원문·소비 경로 확인'):
            checked = w.verify_publication(staged['publication_id'])
            st.session_state['domain_checked_' + selected] = checked; st.json(checked)
        checked = st.session_state.get('domain_checked_' + selected)
        if checked and st.button('확인한 게시본 사용 전환'):
            st.json(w.activate_publication(staged['publication_id'], head['sequence'], checked)); st.rerun()
    st.caption('소비 경로 확인은 저장·원문 연결 검사입니다. 실모델의 답변 사용·법률 품질 통과를 뜻하지 않습니다.')
