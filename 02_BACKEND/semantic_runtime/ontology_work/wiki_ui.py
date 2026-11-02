"""Profile-free list/editor; compilation uses the existing review/publication ports."""
import json
import uuid
from .configuration import workspace_workflow, domain_workflow
from .wiki_contracts import scope_key


def reference_pins(w, d, extra=()):
    content = d['content']
    ids = [d['bundle_id'], *content.get('statement_refs', []), *content.get('member_refs', []),
           *(r['target'] for r in content.get('navigation_links', [])), *extra]
    return {bid: {k: w.item(bid)[k] for k in ('revision', 'work_hash')} for bid in dict.fromkeys(ids)}


def layout_controls(st, w, d, entries):
    """Human navigation edits stay separate from statement revisions and approval."""
    with st.expander('연결·주제 보기'):
        st.caption('항목을 묶거나 연결해도 문장과 승인된 의미는 바뀌지 않습니다.')
        for i, link in enumerate(d['content']['navigation_links']):
            target = w.item(link['target'])
            if target['kind'] == 'ENTRY':
                if st.button(link['label'] + ' → ' + target['content']['title'], key='wiki_follow_' + str(i)):
                    st.session_state.wiki_selected = target['bundle_id']; st.rerun()
            else: st.write(link['label'], target['content'])
            if st.button('연결 제거', key='wiki_unlink_' + str(i)):
                w.apply(change_id=uuid.uuid4().hex, expected=reference_pins(w, d), operations=[
                    {'op': 'UNLINK', 'target': d['bundle_id'], 'value': {k: link[k] for k in ('label', 'target')}}]); st.rerun()
        options = {row['bundle_id']: row['title'] for row in entries}
        target = st.selectbox('연결할 항목', list(options), format_func=options.get)
        label = st.text_input('연결 설명', key='wiki_link_label')
        if st.button('탐색 연결 추가', disabled=not label.strip()):
            w.apply(change_id=uuid.uuid4().hex, expected=reference_pins(w, d, [target]), operations=[
                {'op': 'LINK', 'target': d['bundle_id'], 'value': {'label': label, 'target': target}}]); st.rerun()
        title = st.text_input('새 주제 보기 이름', key='wiki_view_title')
        if st.button('이 항목으로 주제 보기 만들기', disabled=not title.strip()):
            w.apply(change_id=uuid.uuid4().hex, expected=reference_pins(w, d), operations=[
                {'op': 'CREATE_VIEW', 'target': '@view', 'value': {'title': title, 'member_refs': [d['bundle_id']]}}]); st.rerun()
        view_page = w.list_items(kind='VIEW', query=st.text_input('주제 보기 검색', key='wiki_view_query'))
        if view_page['cursor']: st.caption('더 많은 주제 보기가 있습니다. 이름으로 검색 범위를 좁히세요.')
        for row in view_page['items']:
            view = w.item(row['bundle_id']); choices = dict(options)
            for member in view['content']['member_refs']:
                item = w.item(member); choices[member] = item['content'].get('title', item['content'].get('text', ''))[:120]
            members = st.multiselect(view['content']['title'] + ' · 포함 항목', list(choices),
                default=view['content']['member_refs'], format_func=choices.get, key='wiki_members_' + row['bundle_id'] + str(row['revision']))
            if st.button('보기 구성 저장', key='wiki_view_save_' + row['bundle_id']):
                w.apply(change_id=uuid.uuid4().hex, expected=reference_pins(w, view, members), operations=[
                    {'op': 'REVISE_VIEW', 'target': row['bundle_id'], 'value': {'member_refs': members}}]); st.rerun()
            for member in view['content']['member_refs']:
                if w.item(member)['kind'] == 'ENTRY' and st.button('열기: ' + choices[member], key='wiki_member_' + row['bundle_id'] + member):
                    st.session_state.wiki_selected = member; st.rerun()


def render():
    import streamlit as st
    from .ui import actor
    st.caption('기록을 자유롭게 모으고, 재사용할 문장만 원문과 함께 검토합니다.')
    try:
        w = workspace_workflow(actor=actor())
        page = w.list_items(query=st.text_input('항목 검색', key='wiki_query'), cursor=st.session_state.get('wiki_cursor'))
    except Exception as exc:
        st.session_state.pop('wiki_cursor', None)
        st.error('작업공간 연결·권한 또는 목록 판본을 확인하세요: ' + str(exc)[:240])
        return
    with st.expander('새 기록 남기기', expanded=not page['items']):
        title = st.text_input('항목 이름', key='wiki_new_title')
        body = st.text_area('기록·설명', key='wiki_new_body')
        if st.button('기록 저장', disabled=not title.strip() or not body.strip()):
            change = st.session_state.setdefault('wiki_new_change', uuid.uuid4().hex)
            try:
                raw = w.import_payload(body, run_id='workspace-note', event_id=change, format_description='사용자가 작성한 원기록; 원문 지지 미검토')
                result = w.apply(change_id=change, raw_ids=[raw['bundle_id']], operations=[
                    {'op': 'ADD_STATEMENT', 'target': '@statement', 'value': {'text': body, 'origin_refs': [raw['bundle_id']]}},
                    {'op': 'CREATE_ENTRY', 'target': '@entry', 'value': {'title': title, 'body': body, 'statement_refs': ['@statement']}}])
                st.session_state.wiki_selected = result['handles']['@entry']
                st.session_state.pop('wiki_new_change', None); st.rerun()
            except Exception as exc: st.error('저장 상태를 확인하세요: ' + str(exc)[:300])
    with st.expander('원기록·원문에서 변경안 만들기'):
        raw_file = st.file_uploader('원기록 가져오기 JSON', type=['json'], key='wiki_raw_import')
        source_file = st.file_uploader('확인할 원문 JSON 목록', type=['json'], key='wiki_originals')
        if st.button('항목 변경안 만들기', disabled=raw_file is None or w.generate is None):
            try:
                spec = json.loads(raw_file.getvalue()); raw = w.ingest(spec) if 'raw_event_id' in spec else w.import_payload(**spec)
                originals = json.loads(source_file.getvalue()) if source_file else []
                change = 'ingest-' + raw['work_hash']
                st.session_state.wiki_proposal = w.propose(change_id=change, raw_ids=[raw['bundle_id']], originals=originals)
            except Exception as exc: st.error('변경안 생성 상태를 확인하세요: ' + str(exc)[:300])
        proposal = st.session_state.get('wiki_proposal')
        if proposal:
            st.json(proposal['operations'])
            st.caption('변경안 적용은 초안 저장입니다. 법률 내용 승인·게시와 구분됩니다.')
            if st.button('변경안 적용'):
                try:
                    st.json(w.apply(**proposal)); st.session_state.pop('wiki_proposal', None); st.rerun()
                except Exception as exc: st.error('반영 상태를 확인하세요: ' + str(exc)[:300])
    if page['cursor'] and st.button('다음 항목'):
        st.session_state.wiki_cursor = page['cursor']; st.rerun()
    if st.session_state.get('wiki_cursor') and st.button('처음부터 보기'):
        st.session_state.pop('wiki_cursor', None); st.rerun()
    selected = st.session_state.pop('wiki_selected', None)
    if selected and selected not in {r['bundle_id'] for r in page['items']}:
        try:
            item = w.item(selected)
            if item['kind'] == 'ENTRY': page['items'].append({**item, 'title': item['content']['title']})
        except Exception as exc: st.error('연결 항목을 열 수 없습니다: ' + str(exc)[:240])
    if not page['items']: st.info('저장된 항목이 없습니다.'); return
    st.dataframe([{'항목명': r['title'], '상태': r['state'], '판본': r['revision']} for r in page['items']], hide_index=True)
    ids = [r['bundle_id'] for r in page['items']]
    if selected in ids: st.session_state.wiki_entry_choice = selected
    bid = st.selectbox('내용 보기', ids, key='wiki_entry_choice', format_func=lambda key: next(r['title'] for r in page['items'] if r['bundle_id'] == key))
    d = w.item(bid); st.write(d['content']['body'])
    try: layout_controls(st, w, d, page['items'])
    except Exception as exc: st.error('연결·보기 변경 상태를 확인하세요: ' + str(exc)[:300])
    with st.expander('제목·설명 수정'):
        title = st.text_input('제목', d['content']['title'], key='wiki_title_' + bid + str(d['revision']))
        body = st.text_area('설명', d['content']['body'], key='wiki_body_' + bid + str(d['revision']))
        if st.button('새 판본 저장'):
            try:
                expected = {bid: {k: d[k] for k in ('revision', 'work_hash')}}
                for sid in d['content']['statement_refs']:
                    row = w.item(sid); expected[sid] = {k: row[k] for k in ('revision', 'work_hash')}
                for link in d['content']['navigation_links']:
                    row = w.item(link['target']); expected[row['bundle_id']] = {k: row[k] for k in ('revision', 'work_hash')}
                w.apply(change_id=uuid.uuid4().hex, expected=expected, operations=[{'op': 'REVISE_ENTRY', 'target': bid, 'value': {'title': title, 'body': body}}])
                st.rerun()
            except Exception as exc: st.error(str(exc)[:300])
    statements = [w.item(sid) for sid in d['content']['statement_refs']]
    for item in statements:
        with st.expander(item['content']['text'][:120]):
            st.write(item['content']['text']); st.write(item['content']['open_items'])
            for basis in item['content']['source_basis']:
                st.caption(basis['anchor']['label']); st.text(basis['quote'])
            if not item['content']['source_basis']: st.info('원문 근거 미검토 · 자유 기록으로 보존 중')
            if w.can_publish:
                reason = st.text_input('철회 이유', key='wiki_withdraw_' + item['bundle_id'])
                if st.button('이 문장 철회', key='wiki_retract_' + item['bundle_id'], disabled=not reason.strip()):
                    try:
                        w.apply(change_id=uuid.uuid4().hex, expected={item['bundle_id']: {k: item[k] for k in ('revision', 'work_hash')}},
                                operations=[{'op': 'RETRACT', 'target': item['bundle_id'], 'value': {'reason': reason}}]); st.rerun()
                    except Exception as exc: st.error(str(exc)[:300])
    if not st.checkbox('재사용 준비·승인·게시 열기', key='wiki_compile_controls'): return
    domain = None
    try:
        domain = domain_workflow(actor=actor())
        profiles = []
        for row in domain.repo.list(prefix='dp-'):
            try:
                current = domain.load(row['bundle_id'])
                if current['status'] == 'APPROVED': profiles.append(current)
            except Exception: continue
        if not profiles: st.info('기존 도메인 설정 화면에서 사용할 프로필을 검토·승인하세요.'); return
        profile = st.selectbox('컴파일 설정', profiles, format_func=lambda row: row['profile']['domain']['profile_id'])
        chosen = st.multiselect('재사용할 문장', [s['bundle_id'] for s in statements], format_func=lambda sid: next(s['content']['text'][:120] for s in statements if s['bundle_id'] == sid))
        purpose = st.text_input('재사용 목적', key='wiki_purpose')
        if st.button('선택 문장 컴파일', disabled=not chosen or not purpose.strip() or w.generate is None):
            from .wiki_projection import compile_selection
            with st.spinner('원문·의미·누락을 확인하고 조립합니다.'):
                result = compile_selection(domain, w, statement_ids=chosen, purpose=purpose,
                    profile_id=profile['bundle_id'], profile_work_hash=profile['work_hash'])
            st.session_state.wiki_compiled = result['bundle_id']
        rows = domain.repo.list(prefix='cb-kb-ws-' + scope_key(w.scope()) + '-')
        if not rows: return
        compiled = st.selectbox('검토할 컴파일 묶음', [r['bundle_id'] for r in rows])
        work = domain.load(compiled); package = domain.preview(compiled)
        for path in package['paths']:
            st.write(path['title'] + ' · ' + path['status']); st.text(path['body']); st.write(path['unresolved'])
        st.write(package['graph']['unresolved'])
        st.json(work['workspace_projection']['coverage'])
        reason = st.text_input('검토 의견', key='wiki_review_reason')
        if work['status'] == 'DRAFT':
            approve = st.checkbox('원문·포함 범위·미확인 내용을 검토했습니다.')
            if st.button('재사용 묶음 승인', disabled=not approve or not reason.strip()):
                domain.review(compiled, work['revision'], work['work_hash'], True, reason); st.rerun()
            if st.button('반려', disabled=not reason.strip()):
                domain.review(compiled, work['revision'], work['work_hash'], False, reason); st.rerun()
        if work['status'] == 'APPROVED' and w.can_publish and st.button('소비 검증 후 게시 활성화'):
            head = domain.repo.head(compiled)
            stage = domain.stage_publication(compiled, work['revision'], work['work_hash'], head['sequence'])
            receipt = domain.verify_publication(stage['publication_id'])
            st.json(domain.activate_publication(stage['publication_id'], head['sequence'], receipt))
            st.success('게시가 활성화됐습니다. 허용된 작업공간을 읽는 RAG 요청에서 사용할 수 있습니다.')
    except Exception as exc: st.error('재사용 준비 상태를 확인하세요: ' + str(exc)[:300])
    finally:
        if domain is not None: domain.glossary.reader.close()
