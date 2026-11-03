"""Bound final change accounting; a valid receipt is not semantic certification."""
from copy import deepcopy
from ..contracts import digest
from .completion_contracts import obj
from . import read_judgment as rj
from .reference_bundles import attach_context

PROMPT = '''read_judgments.change_review가 true이면 각 판단의 change_from(이전 긍정 의견)과 review_purposes(원문을 읽게 된 각각의 목적)를 함께 검토한다. 이전 의견은 바꿀 수 있다. 단, NOT_USED로 제외할 때 change_review에 이전 version과 finding의 정확한 인용을 넣고 모든 purpose_id를 한 번씩 처리한다. source_quote는 각 목적에 제시된 문구 그대로다. 정의 탐색 실패만으로 적용 조건·예외 참조를 불필요하다고 할 수 없다.
REINTERPRETED는 원래 목적을 현재 원문으로 재검토하여 해석을 수정한 경우이며 해당 조항과 origin_evidence_refs의 원문을 basis_refs로 연결한다. COVERED_ELSEWHERE는 같은 쟁점의 실제 claim_refs와 그 근거로 해당 목적을 이미 다룬 경우다. UNRESOLVED는 해당 목적이 아직 미확인인 경우이며 같은 쟁점의 material gap_indices(1부터)를 연결한다. 판단 자체가 UNRESOLVED이면 미확인을 같은 쟁점의 핵심 gaps에 보존한다. 목적별 reason으로 변경 이유를 설명한다. 이전 의견·근거·목적은 삭제되지 않으며 새 조문 번호를 추측하거나 이유 한 문장만으로 완료 처리하지 않는다.'''
PROMPT += '\nROLE_ONLY는 이전 finding의 해석은 유지하면서 이번 답변에서의 사용 역할만 바꾼 경우다. 현재 원문과 목적을 basis_refs로 연결하고 claim_refs/gap_indices는 비운다. 보조 근거를 미사용으로 바꿨다는 사실만으로 REINTERPRETED라고 쓰지 않는다. 사용을 유지하며 해석을 바꾸는 경우도 실제 claims에 변경된 해석과 조건을 적으며 사용 역할 검사는 의미 정확성 인증이 아니다.'


def bind_context(heads,state,investigation,options,issues):
    attach_context(heads,investigation,options,issues)
    prior={}
    for receipt in state.get('receipts',{}).values():
        for change in receipt.get('changes',[]):
            for row in (change.get('previous'),change.get('current')):
                if row and row.get('use') in ('CORE','SUPPORT') and row.get('version',0)>prior.get(row['id'],{}).get('version',-1):prior[row['id']]=row
    for h in heads.values():
        if h.get('use') in ('CORE','SUPPORT'):prior[h['id']]=h
        positive=prior.get(h['id'])
        if positive:h['change_from']={k:deepcopy(positive[k]) for k in ('version','finding','reason','use')}
        purposes=[]
        for p in h.get('reference_purposes',[]):
            purposes.append({'id':'P'+digest([p['id'],p['target_coordinate']])[:24],
                'source_quote':p['source_quote'],'purpose':p['purpose'],
                'issue_refs':[p['issue_id']],'origin_evidence_refs':p['origin_evidence_refs'],
                'target_coordinate':p['target_coordinate'],'acquisition_status':p['acquisition_status'],'target_present':p['target_present'],'target_evidence_refs':p['target_evidence_refs']})
        if positive:
            purposes.insert(0,{'id':'P'+digest([h['id'],positive['version'],positive['finding']])[:24],
                'source_quote':positive['finding'],'purpose':positive['reason'],
                'issue_refs':list(h['issue_refs']),'origin_evidence_refs':[]})
        h['review_purposes']=purposes


def schema(ctx,options):
    return obj({'prior_version':{'type':'integer','minimum':0},'prior_finding_quote':{'type':'string'},
        'purpose_reviews':{'type':'array','uniqueItems':True,'items':obj({
            'purpose_id':{'type':'string'},'source_quote':{'type':'string'},
            'status':{'enum':['ROLE_ONLY','REINTERPRETED','COVERED_ELSEWHERE','UNRESOLVED']},
            'basis_refs':rj.strings([o['id'] for o in options]),
            'claim_refs':{'type':'array','uniqueItems':True,'items':{'type':'string'}},
            'gap_indices':{'type':'array','uniqueItems':True,'items':{'type':'integer','minimum':1}},
            'reason':rj.TEXT})}})


def validate_changes(value,ctx,options,fail):
    heads={r['id']:r for r in ctx['judgments']};claims={c['claim_id']:c for c in value['claims']};gaps=value.get('gaps',[])
    for i,row in enumerate(value['read_judgment_review']['judgments']):
        if row['id'] not in heads:continue
        h=heads[row['id']];purposes=h.get('review_purposes',[]);path='/read_judgment_review/judgments/'+str(i)+'/change_review'
        def invalid(code,expected):fail(code,path,'final exclusion must account for the original purpose and changed finding',expected)
        if row['disposition']=='UNRESOLVED' and purposes:
            if not any(g['material'] and g['issue_id'] in h['issue_refs'] for g in gaps):invalid('FINAL_REVIEW_UNRESOLVED_GAP',{'issue_refs':h['issue_refs'],'material_gap_required':True})
        if row['disposition']!='NOT_USED' or not purposes:continue
        c=row.get('change_review');before=h.get('change_from',{'version':0,'finding':''})
        if not c:
            invalid('FINAL_REVIEW_PURPOSE_CHANGE',{'prior_version':before['version'],'purpose_ids':[p['id'] for p in purposes]});continue
        quote=c['prior_finding_quote']
        if c['prior_version']!=before['version'] or (before['finding'] and (not quote.strip() or quote not in before['finding'])) or (not before['finding'] and quote):
            invalid('FINAL_REVIEW_CHANGE_BINDING',{'version':before['version'],'finding':before['finding']})
        selected=c['purpose_reviews'];ids=[p['purpose_id'] for p in selected];expected={p['id'] for p in purposes}
        if len(set(ids))!=len(ids) or set(ids)!=expected:invalid('FINAL_REVIEW_PURPOSE_COVERAGE',{'purpose_ids':sorted(expected)})
        by_id={p['id']:p for p in purposes}
        for p in selected:
            if p['purpose_id'] not in by_id:continue
            origin=by_id[p['purpose_id']];own=set(h['available_evidence_refs']);refs=set(p['basis_refs'])
            if p['source_quote']!=origin['source_quote'] or not p['reason'].strip():invalid('FINAL_REVIEW_PURPOSE_QUOTE',{'purpose_id':origin['id'],'source_quote':origin['source_quote']})
            if p['status']!='UNRESOLVED' and origin.get('target_coordinate'):
                if not origin.get('target_present') or not set(origin.get('target_evidence_refs',[]))<=refs:
                    invalid('FINAL_REVIEW_TARGET_RANGE',{'purpose_id':origin['id'],'target_coordinate':origin['target_coordinate'],'target_present':origin.get('target_present',False),'target_evidence_refs':origin.get('target_evidence_refs',[])})
            if p['status'] in ('ROLE_ONLY','REINTERPRETED'):
                if not (own&refs) or not set(origin['origin_evidence_refs'])<=refs or p['claim_refs'] or p['gap_indices']:
                    invalid('FINAL_REVIEW_REINTERPRET_BASIS',{'own_evidence_refs':sorted(own),'origin_evidence_refs':origin['origin_evidence_refs']})
            elif p['status']=='COVERED_ELSEWHERE':
                selected_claims=[claims[c] for c in p['claim_refs'] if c in claims]
                if not selected_claims or len(selected_claims)!=len(p['claim_refs']) or p['gap_indices'] or not refs or any(not (set(c['issue_refs'])&set(origin['issue_refs'])) or not (refs&set(c['evidence_refs'])) for c in selected_claims):
                    invalid('FINAL_REVIEW_PURPOSE_CLAIM',{'actual_claim_ids':list(claims),'issue_refs':origin['issue_refs']})
            else:
                selected_gaps=[gaps[g-1] for g in p['gap_indices'] if 1<=g<=len(gaps)]
                if not selected_gaps or len(selected_gaps)!=len(p['gap_indices']) or p['claim_refs'] or any(not g['material'] or g['issue_id'] not in origin['issue_refs'] for g in selected_gaps):
                    invalid('FINAL_REVIEW_PURPOSE_GAP',{'issue_refs':origin['issue_refs'],'material_gap_required':True})
