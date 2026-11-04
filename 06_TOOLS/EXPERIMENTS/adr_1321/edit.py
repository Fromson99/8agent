from common import *
C=ROOT/read(DES/'candidate-path.json')['candidate']/'snapshot';P=C/'02_BACKEND/semantic_runtime/legal_agent'
p=P/'corrected_memory.py';s=p.read_text();s=s.replace("        from .law_candidates import answer_first\n        agent=getattr(getattr(getattr(self.executor,'model',None),'pipeline',None),'term_agent',None)\n", "        # Conversation continuity is independent of navigation/answer-first policy.\n")
s=s.replace("continuation = ('''", "continuation = '''").replace("''' if answer_first(getattr(agent,'profile',{})) else '')", "'''")
p.write_text(s)
p=P/'output_contract.py';s=p.read_text();s=s.replace("('method_id','choice','next_action','operation','kind','status','disposition')", "('method_id','choice','next_action','operation','kind','status','disposition','id','target_id','issue_id')");p.write_text(s)
p=P/'read_judgment_final.py';s=p.read_text();start=s.index('def repair_choices(');end=s.index('\ndef independent_core',start)
s=s[:start]+'''def repair_choices(value, error):
    """Explain conflicting model decisions; never adopt or erase a legal claim.

    Accept canonical rows and the failed shared-link wire form so expansion
    failures receive the same bounded feedback. Evidence overlap is diagnostic,
    not proof that a provisional opinion belongs in the final answer.
    """
    if not isinstance(value,dict):return []
    from .output_contract import diagnostics
    relevant = {'SCOPE_CLAIM_EVIDENCE','SCOPE_USE_UNSUPPORTED_RANGE','NEED_CLAIM_LINK',
                'FINAL_REVIEW_UNRESOLVED_GAP'}
    issues = diagnostics(error).get('issues',[])
    if not any(i['code'] in relevant or i.get('path','').startswith('/'+FIELD+'/judgments/') for i in issues):return []
    claims = value.get('claims',[])
    review = value.get(FIELD,{})
    if not isinstance(review,dict):return []
    shared = value.get('review_links')
    links = {r['id']:r for r in shared if isinstance(r,dict) and 'id' in r} if isinstance(shared,list) else {}
    rows = []
    for i,row in enumerate(review.get('judgments',[])):
        refs = links.get(row.get('link_ref'),row)
        if 'basis_refs' not in refs or 'claim_refs' not in refs:continue
        path = '/'+FIELD+'/judgments/'+str(i)
        if row.get('disposition') in ('USE','CONDITIONAL') and not refs['claim_refs']:
            rows.append({'path':path, 'judgment_id':row.get('id'),
                'cause':'ADOPTED_WITHOUT_CLAIM', 'current_disposition':row['disposition'],
                'link_ref':row.get('link_ref'), 'actual_claim_ids':[c.get('claim_id') for c in claims],
                'alternatives':[
                    '이번 답변에 쓰지 않는 판단이면 NOT_USED와 제외 이유·원래 목적 검토를 직접 작성한다. 중요한 미확인은 UNRESOLVED 및 gaps로 남긴다.',
                    '실제 답변에 채택한 판단이면 USE/CONDITIONAL과 존재하는 주장·현재 원문을 연결한다.'],
                'constraint':'제외한다는 잠정 의견을 유지하는 것과 답변 주장으로 채택하는 것은 다르다. 형식을 통과하려고 원문이나 주장을 만들지 않는다.'})
        elif row.get('disposition') in ('UNRESOLVED','NOT_USED'):
            overlaps = [c.get('claim_id') for c in claims if set(c.get('evidence_refs',[])) & set(refs['basis_refs'])]
            if not overlaps:continue
            rows.append({'path':path, 'judgment_id':row.get('id'),
                'cause':'UNADOPTED_SHARED_EVIDENCE','current_disposition':row['disposition'],
                'claims_sharing_evidence':overlaps,
                'alternatives':[
                    '현재 원문 판단을 실제 답에 채택했다면 USE 또는 CONDITIONAL과 실제 주장·근거 연결을 직접 선택한다.',
                    '채택하지 않았다면 UNRESOLVED/NOT_USED와 이유를 유지하고, 충돌하는 USE 범위·해결 연결을 검토한다. 중요한 미확인은 gaps에 남긴다.'],
                'constraint':'같은 원문을 썼다는 이유만으로 판단을 채택하지 않는다. claim·인용·질문 요구를 임의 삭제하지 않는다.'})
    return rows

''' +s[end:];p.write_text(s)
print('Followup directive always delivered; exact id diagnostics and wire/canonical review feedback; legal validation unchanged')
