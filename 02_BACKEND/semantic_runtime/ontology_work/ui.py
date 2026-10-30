"""Real workflow panels embedded into the existing Legal Knowledge Streamlit app."""
import json,os
from ..legal_agent.errors import ContractError
from .configuration import workflow,settings

STATUS={'INPUT':'생성 대기','DRAFT':'승인 대기','APPROVED':'승인됨 · 게시 가능','REJECTED':'반려'}
def actor():
    cfg=settings()
    if cfg.get('environment')=='local':
        return os.environ.get('GENOS_ONTOLOGY_OPERATOR','')
    import dataiku
    # Identity comes from the authenticated browser session, not project API user.
    import streamlit as st
    auth=dataiku.api_client().get_auth_info_from_browser_headers(dict(st.context.headers),with_secrets=False)
    return auth.get('authIdentifier','')

def render(*,simulation=False):
    import streamlit as st
    st.header('시나리오 검증' if simulation else '온톨로지 관리')
    if not simulation and st.radio('작업 방식',['기존 시나리오','도메인 프로필·판단 축적'],horizontal=True)=='도메인 프로필·판단 축적':
        from .domain_ui import render as render_domain
        render_domain();return
    st.caption('원문과 판단 → 시나리오 생성 → 검토 승인 → DB 게시 → RAG 경로 선택')
    try:
        w=workflow(actor=actor())
        rows=w.repo.list(prefix='cb-')
        visible=[]
        for row in rows:
            try:
                d=w.load(row['bundle_id']);w.verify_sources(d['input']);visible.append(row)
            except ContractError:continue
    except Exception as e:
        st.error('연결 또는 운영자 권한을 확인하세요. '+type(e).__name__)
        return
    if not simulation:
        with st.expander('원문·에이전트 판단에서 새 시나리오 만들기',expanded=not visible):
            file=st.file_uploader('원문·판단 작업 JSON',type=['json'],key='ont_input')
            if file is not None:
                try:
                    work=json.loads(file.getvalue());w.verify_sources(work)
                    st.write(work['concept']);st.caption(f"원문 {len(work['originals'])}개 · 판단 {len(work['judgments'])}개")
                    if st.button('시나리오 초안 생성',disabled=w.generate is None):
                        with st.spinner('원문에 근거한 초안을 생성합니다.'):
                            result=w.propose(work)
                        st.session_state.ont_selected=result['bundle_id'];st.rerun()
                except Exception as e:st.error('초안 생성이 완료되지 않았습니다: '+str(e)[:500])
            if w.generate is None:st.info('생성 모델 연결 전입니다. 검토·승인·게시 기능은 저장된 초안을 사용할 수 있습니다.')
    if not visible:
        st.info('아직 검토할 시나리오가 없습니다.');return
    ids=[r['bundle_id'] for r in visible];chosen=st.session_state.get('ont_selected',ids[0])
    bid=st.selectbox('검토할 묶음',ids,index=ids.index(chosen) if chosen in ids else 0,
        format_func=lambda k:k+' · '+STATUS[next(r['status'] for r in visible if r['bundle_id']==k)])
    d=w.load(bid);head=w.repo.head(bid)
    st.caption(f"작업 판본 {d['revision']} · {STATUS[d['status']]} · 현재 게시: {head['publication_id'] or '없음'}")
    st.subheader(d['input']['concept'])
    for source in d['input']['originals']:
        with st.expander(source['anchor']['label']):st.text(source['text'])
    with st.expander('발견 근거와 에이전트 판단'):st.json(d['input']['judgments'])
    if d['status']=='INPUT':
        if st.button('저장된 판단으로 시나리오 생성',disabled=w.generate is None):
            try:
                w.propose(d['input'],bundle_id=bid,expected_revision=d['revision']);st.rerun()
            except Exception as e:st.error('생성 결과를 확인하세요: '+str(e)[:500])
        if w.generate is None:st.info('생성 모델을 연결하면 이 작업의 초안을 만들 수 있습니다.')
        return
    try:
        package=w.preview(bid)
        for path in package['paths']:
            with st.container(border=True):
                st.markdown('**'+path['title']+'**');st.write(path['business_use']);st.text(path['body'])
        st.success('원문 인용·판본·의존 순환·조립 검사를 통과했습니다. 적용 타당성은 검토자가 확인합니다.')
    except Exception as e:
        st.error('원문 또는 시나리오 검사가 실패했습니다: '+str(e)[:500]);return
    if simulation:
        ids=[p['id'] for p in package['paths']]
        picked=st.multiselect('업무에 필요한 경로를 함께 선택',ids)
        for p in package['paths']:
            if p['id'] in picked:st.text(p['body'])
        if not picked:st.info('맞는 경로가 없으면 RAG는 기존 원문 탐색으로 돌아갑니다.')
        st.caption('이 화면은 사전 조립과 수동 선택 검증입니다. LLM의 선택 품질 평가 결과가 아닙니다.')
        return
    with st.expander('시나리오 수정'):
        edit=st.text_area('레시피 JSON',json.dumps(d['proposal'],ensure_ascii=False,indent=2),height=300,key='recipe_'+bid+str(d['revision']))
        if st.button('새 판본으로 저장'):
            try:w.save(d['input'],json.loads(edit),bundle_id=bid,expected_revision=d['revision']);st.rerun()
            except Exception as e:st.error(str(e)[:500])
    reason=st.text_input('검토 의견',key='review_'+bid+str(d['revision']))
    if d['status']=='DRAFT':
        ok=st.checkbox('조립된 경로와 조건·산정·예외의 원문 근거를 확인했습니다.')
        a,b=st.columns(2)
        for button,col,approve in [('승인',a,True),('반려',b,False)]:
            if col.button(button,disabled=not reason.strip() or (approve and not ok)):
                try:w.review(bid,d['revision'],d['work_hash'],approve,reason);st.rerun()
                except Exception as e:st.error(str(e)[:500])
    if d['status']=='APPROVED' and st.button('승인 판본을 DB에 게시',type='primary'):
        try:
            receipt=w.publish(bid,d['revision'],d['work_hash'],head['sequence'])
            st.success('DB 게시를 확인했습니다. 온톨로지 ON인 새 요청부터 사용합니다.');st.json(receipt)
        except Exception as e:st.error('게시 성공을 확인하지 못했습니다. 자동 재시도하지 않습니다. 게시 상태를 조회해 확인하세요. '+type(e).__name__)
    if head['publication_id'] and st.button('현재 게시 중지'):
        try:w.repo.activate(bid,None,head['sequence'],w.actor);st.rerun()
        except Exception as e:st.error(str(e)[:500])
