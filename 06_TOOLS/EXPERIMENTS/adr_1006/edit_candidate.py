from common import *
C=ROOT/read(ART/'stage.json')['roots']['candidate']
p=C/'02_BACKEND/semantic_runtime/legal_agent/answer_progress.py';t=p.read_text()
t=t.replace("REVISION = 'answer-progress-v1'", "REVISION = 'answer-progress-v1'\nCONTENT_REVISION = 'source-content-completion-v1'")
t=t.replace('def request_key(inv, data):', '''def content_enabled(inv):
    return enabled(inv) and bool(inv.policy.get('source_content_review', False))


CONTENT_PROMPT = 'pending'


def request_key(inv, data):''')
# Keep the actual prompt in the product language; no case IDs or expected answers.
a=t.index('CONTENT_PROMPT = ');b=t.index('\n\n\ndef request_key',a)
t=t[:a]+"CONTENT_PROMPT = "+repr('''source_checks는 answer_progress.basis_refs 각각의 원문이 질문에 필요한 내용을 직접 제공하는지 검토한 의견이다. 한 원문당 한 행을 쓴다.
질문의 종류·범위·항목·요건을 설명하는 데 필요한 내용이 다른 규정에 위임되어 있으면, 위임 문구나 큰 항목 이름만 재진술한 것은 내용 확인 완료가 아니다. 사용자가 큰 항목의 명칭만 또는 특정 조문의 문언만 요청한 경우가 아니면, 질문의 대상 내용을 구체화하는 연결 원문까지 확인한다. 사용자 질문에 없는 '법률의 항목 이름만 묻는 질문'이라는 제한을 임의로 붙이지 않는다.
SELF_CONTAINED는 이 원문에 해당 질문의 필요한 내용이 직접 있는 경우, NEED_ORIGINAL은 필요한 내용이 다른 원문에 있고 아직 그 내용을 읽지 않은 경우, CONTENT_READ는 해당 내용을 sources의 실제 원문에서 확인한 경우, OUTSIDE_REQUEST는 특정 주체·사안·특례처럼 이번 질문에 불필요한 경우다. NEED_ORIGINAL이면 delegation_quote에 현재 원문의 정확한 위임·참조 문구와 reason에 필요한 내용을 쓰고 연결 원문을 선택한다. CONTENT_READ는 실제 확인한 read_refs를 제시한다. 연결 카드의 제목·참조 발췌는 대상 내용을 읽은 것으로 보지 않는다. OUTSIDE_REQUEST는 질문과의 관계를 설명하고 조사하지 않는다.
연결 카드가 특정 항·호만 가리키더라도 그 부분이 질문의 내용과 다르면 같은 조의 whole_article_read_action을 선택해 해당 조의 다른 항·호를 확인할 수 있다. read_action과 whole_article_read_action은 별개 범위이며 필요한 쪽을 직접 선택한다. 모든 연결·예외를 읽을 필요는 없다. 제목·좌표·연결 존재만으로 적용이나 내용 확인을 확정하지 않는다.
현재 필요한 원문 대상이 read_candidates나 연결 카드에 있으면 그 READ를 사용한다. 이미 특정한 대상 대신 NEXT_LAWS/NEXT_TERM_MATCHES로 주변 목록을 더 넘기지 않는다. 다음 경로가 대상을 좁힐 때만 탐색을 계속한다.
status는 도구에서 시스템이 추정하는 값이 아니라 네가 직접 출력할 종료 판단이다. 필요한 내용이 남으면 NEEDS_SOURCE와 그 내용에 대한 행동, 충분하면 ANSWERABLE과 FINISH, 조회 실패·예산·진전 없음이면 NO_PROGRESS와 제한 종료를 고른다. '필요 없음'이라고 판단하고 탐색을 선택하지 않는다. 필요한 연결 내용을 확인한 다음에는 그 답을 바꾸지 않는 부수 연결을 펼치지 말고 종료한다.''')+t[b:]
t=t.replace("return digest([REVISION, inv.p['binding']", "return digest([CONTENT_REVISION if content_enabled(inv) else REVISION, inv.p['binding']")
t=t.replace("    alternatives = []\n    for branch", """    if content_enabled(inv):
        refs = {'type':'array','maxItems':min(4,len(current)),'uniqueItems':True,
                'items':{'enum':list(current)}} if current else {'type':'array','maxItems':0,'items':{'type':'string'}}
        review['properties']['source_checks'] = {'type':'array','maxItems':min(4,len(current)),
            'items':obj({'source_ref':{'enum':list(current)} if current else {'type':'string'},
                'content_state':{'enum':['SELF_CONTAINED','NEED_ORIGINAL','CONTENT_READ','OUTSIDE_REQUEST']},
                'delegation_quote':{'type':'string','maxLength':300},
                'read_refs':refs, 'reason':{'type':'string','minLength':1,'maxLength':400}})}
        review['required'].append('source_checks')
    alternatives = []
    for branch""")
t=t.replace("opinion['properties']['status'] = {'const': status}", """# A semantic stop opinion must remain explicit on the generation wire.
            # allOf has identical validation semantics, but is not a host literal.
            opinion['properties']['status'] = ({'type':'string','allOf':[{'const':status}]}
                if content_enabled(inv) else {'const': status})""")
needle="    if set(review['basis_refs']) - set(current):\n        raise ContractError('progress review refers to an unoffered original')"
t=t.replace(needle,needle+"""
    if 'source_checks' in review:
        checks=review['source_checks'];refs=[c['source_ref'] for c in checks]
        if len(refs)!=len(set(refs)) or set(refs)!=set(review['basis_refs']):
            raise ProposalError('source_checks must review each selected basis original exactly once')
        for check in checks:
            source=current[check['source_ref']]
            quote=check['delegation_quote']
            if quote and quote not in source['text']:
                raise ProposalError('delegation_quote must be an exact substring of the selected original')
            if set(check['read_refs'])-set(current):
                raise ContractError('content review claims an undelivered original')
            if check['content_state']=='CONTENT_READ' and not check['read_refs']:
                raise ProposalError('CONTENT_READ requires actual delivered original read_refs')
            if check['content_state']=='NEED_ORIGINAL':
                if not quote:raise ProposalError('NEED_ORIGINAL requires the actual reference or delegation quote')
                if review['status']=='ANSWERABLE' or value.get('evidence_sufficient') is True:
                    raise ProposalError('necessary connected original is still unread; READ it or retain a limited unresolved answer')
""")
t=t.replace("'handoff': handoff, 'legal_claim_approved': False}","""'handoff': handoff, 'legal_claim_approved': False,
               'source_bindings': {s['id']:{k:s.get(k) for k in ('source_id','document_id','scope_id')}
                    for s in data.get('sources',[]) if s.get('text')}}""")
p.write_text(t)
p=C/'02_BACKEND/semantic_runtime/legal_agent/decision_projection.py';t=p.read_text()
t=t.replace("(progress.PROMPT+'\\n' if progress_enabled else '')+EXECUTABLE_CHOICE_PROMPT", "(progress.PROMPT+'\\n'+(progress.CONTENT_PROMPT+'\\n' if progress.content_enabled(inv) else '') if progress_enabled else '')+EXECUTABLE_CHOICE_PROMPT")
p.write_text(t)
p=C/'02_BACKEND/semantic_runtime/legal_agent/connection_scope.py';t=p.read_text()
t=t.replace("            cards.append(card)\n", """            if inv.policy.get('source_content_review') and plan and not decision:
                offer_whole_article(inv,scope,connection,group,plan,card,actions)
            cards.append(card)
""")
where='\ndef validate_inline_read(inv, identity, data, reason):'
code='''
def offer_whole_article(inv, scope, connection, group, endpoint, card, actions):
    """Offer a distinct, explicit parent scope; never silently widen a READ."""
    from . import tool_availability as available, law_candidates as lc, unit_relations as rel
    target=group['target'];identity={k:target[k] for k in ('source_id','document_id')}
    plan,unavailable=available.article_plan(inv.s,identity)
    if unavailable:return
    hit,offer=plan
    if set(offer['block_ids'])==set(endpoint[1]['block_ids']):return
    actual=[p for r in inv.read_records().values() if r['source_id']==target['source_id']
            for e in r['evidence'] for p in e['spans']]
    if inventory.covers(inventory.expected(inv.s,target['document_id'],offer['block_ids']),actual):return
    identity['connection']={'scope_id':scope['id'],'reference_id':connection['reference_id'],
        'group_signature':rel.group_signature(inv.question,group),'witness_sha256':connection['witness_sha256'],
        'endpoint_block_ids':connection['endpoint_block_ids'],'endpoint_unit_id':endpoint[1]['unit_id'],
        'whole_article_scope':digest(offer)}
    ident=lc.token(inv.s,'T',['READ_ARTICLES',identity])
    action={'id':ident,'action':'READ_ARTICLES','identity':identity,
            'label':target['document_name']+' '+target['heading']+' — 연결 항·호가 속한 조 전체 원문 읽기'}
    if inv.recovery_blocked(action):return
    actions[ident]=action
    card['whole_article_read_action']=ident
    card['whole_article_scope']={'source_id':target['source_id'],'unit_id':offer['unit_id'],
        'extent':offer['extent'],'scope_hash':digest(offer),'automatic_selection':False}

'''
t=t.replace(where,'\n'+code+where)
t=t.replace("str(identity['unit_id'])", "str(link.get('endpoint_unit_id',identity.get('unit_id')))")
needle="    if not matching:\n        raise ContractError('stale inline connection endpoint')"
t=t.replace(needle,needle+"""
    if 'whole_article_scope' in link:
        from .tool_availability import article_plan
        plan,unavailable=article_plan(inv.s,identity)
        if unavailable or identity.get('unit_id') is not None or digest(plan[1])!=link['whole_article_scope']:
            raise ContractError('stale explicitly selected whole-article scope')
""")
p.write_text(t)
p=C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json';v=read(p)
v['candidate_navigation'].update(answer_progress_control=True,source_content_review=True)
v.update(max_model_attempts=14,max_transport_retries=0);save(p,v)
save(ART/'failure-contract.json',{'owner':'existing read-choice bounded_decision','class':'semantic opinion or contradictory proposal','repair_limit':1,'max_physical_calls':14,'finalization_reserve':3,'transport_retries':0,'semantic_status':'explicit model field, never host inferred','pending_content':'READ or limited unresolved finish; no source invention','whole_scope':'separate model selected parent action; revalidate original witness, endpoint, parent scope, ACL','fatal':['ACL','source hash','state binding'],'resume':'existing request budgets, receipts, original delivery and source-bound review history persist','extra_monitor_calls':0})
