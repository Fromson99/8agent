from common import *
from shutil import copyfile
S=ROOT/read(DES/'candidate.json')['snapshot'];B=S/'02_BACKEND/semantic_runtime/legal_agent'
def edit(n,a,b):
 p=B/n;s=p.read_text();assert a in s,(n,a[:100]);p.write_text(s.replace(a,b))
p=B/'source_goal_control.py';s=p.read_text()
s=s.replace("PROMPT='''", "VERSION='source-goal-execution-v2'\n\nPROMPT='''",1)
s=s.replace('source_targets에는 이번에 반드시 확보할 원문의 lookup_target(해당 문서의 조회 T번호)', 'source_targets에는 이번에 반드시 확보할 원문의 document_id(허용된 문서 ID)')
s=s.replace('서버가 선언한 목표의 정확 조회와 READ를 우선 실행한다.', '기존 목표는 SOURCE_GOAL의 goal_id만 선택한다. 서버가 문서와 좌표를 현재 도구 번호에 연결하며 이미 확정된 목표는 모델 선택 전에 조회·READ를 집행한다.')
s=s.replace("targets=[r['lookup_target'] for r in options(data,actions)]", "targets=list(dict.fromkeys(r['document_id'] for r in options(data,actions)))")
s=s.replace("target=obj({'lookup_target':{'enum':targets}", "target=obj({'document_id':{'enum':targets}")
s=s.replace("        if row['lookup_target'] not in offered:raise ContractError('source target is outside the offered document scope')\n        if offered[row['lookup_target']]['document_id'] not in inv.s.scope:raise ContractError('source target document unauthorized')", """        did=target_document(row,offered)['document_id']
        if did not in inv.s.scope:raise ContractError('source target document unauthorized')""")
s=s.replace("doc=offered[row['lookup_target']];coordinate=", "doc=target_document(row,offered);coordinate=")
s=s.replace("'origin_gap_id':gap['gap_id']", "'origin_gap_id':gap['gap_id'],'expected':deepcopy(binding.get('expected',[]))")
# Never infer a complete original from a target list and some other completed target.
a=s.index('    for goal in goals:\n        if goal[\'status\'] not in');b=s.index('    receipts.append(signature)',a)
s=s[:a]+"    refresh(inv,goals)\n"+s[b:]
s=s.replace("    return {'goals':deepcopy(state(inv,data).get('source_goals',[])),", "    return {'version':VERSION,'goals':deepcopy(state(inv,data).get('source_goals',[])),")
a=s.index("        acquired=[]\n",s.index('def after_execute'));b=s.index("    row['status']=",a)
s=s[:a]+"""        refresh(inv,[goal])
        if goal['status']!='ACQUIRED':
            goal['status']='BLOCKED';goal['route_failure']='READ_INCOMPLETE_ORIGINAL_COVERAGE'
"""+s[b:]
s+='''

def target_document(row,offered):
    # Legacy internal adapters are accepted only if their tool still has the exact document.
    if 'document_id' in row:
        matches=[r for r in offered.values() if r['document_id']==row['document_id']]
        if not matches:raise ContractError('source target is outside the offered document scope')
        if 'lookup_target' in row and offered.get(row['lookup_target'],{}).get('document_id')!=row['document_id']:
            raise ContractError('source goal document/tool mismatch')
        return matches[0]
    if row.get('lookup_target') not in offered:raise ContractError('source target is outside the offered document scope')
    return offered[row['lookup_target']]


def refresh(inv,goals):
    """Exact coordinate AND full verified span coverage; arrival is not a judgment."""
    from . import evidence_inventory as inventory
    for goal in goals:
        if goal['status'] not in ('REQUIRED','BLOCKED'):continue
        acquired=[]
        for plan in inv.p.get('read_plans',{}).values():
            if plan.get('status')!='ACQUIRED':continue
            identities=[x for x in plan.get('targets',[]) if matches(inv,x,goal)]
            if not identities:continue
            for gid in plan.get('completed',{}).values():
                record=inv.p.get('selected',{}).get(gid)
                if not record or record.get('document_id')!=goal['document_id']:continue
                # A batch receipt for another target cannot satisfy this target.
                offer=record.get('offer',{})
                identity={'source_id':record.get('source_id'),'document_id':record['document_id'],'unit_id':offer.get('unit_id')}
                if not matches(inv,identity,goal):continue
                expected=[p for p in goal.get('expected',[]) if p.get('document_id',goal['document_id'])==goal['document_id']]
                if not expected and offer.get('block_ids'):
                    expected=inventory.expected(inv.s,goal['document_id'],offer['block_ids'])
                actual=[p for e in record.get('evidence',[]) for p in e.get('spans',[])]
                if not expected or not inventory.covers(expected,actual):continue
                # Validate original bytes through the same request source verifier.
                for e in record['evidence']:inv.s.repo.verify_evidence(e) if hasattr(inv.s.repo,'verify_evidence') else None
                acquired.append(gid)
        if acquired:
            goal['status']='ACQUIRED';goal['arrivals']=sorted(set(acquired))


def native_decision(inv,data,actions,choice):
    """Mechanical assembly only; existing decision validator owns execution rights."""
    from .law_navigation import decision_schema
    kind='READ_ARTICLES' if choice['choice']=='READ' else 'SEARCH_STRUCTURE'
    schema=decision_schema(data,actions,{b['id'] for b in data['branches']})
    branches=[b for b in schema['anyOf'] if b['properties']['next_action']['const']==kind]
    branch=next(b for b in branches if kind=='READ_ARTICLES' or ('structure_filter' in b['properties'])==('structure_filter' in choice))
    decision={}
    for name,rule in branch['properties'].items():
        if 'const' in rule:decision[name]=deepcopy(rule['const'])
        elif len(rule.get('enum',[]))==1:decision[name]=deepcopy(rule['enum'][0])
        elif rule.get('type')=='array':decision[name]=[]
    rows=choice['selections'] if kind=='READ_ARTICLES' else [choice]
    rows=[{k:r[k] for k in ('target','issue_id','missing_need','relation','source_ref')} for r in rows]
    decision.update(next_action=kind,notes='',targets=[r['target'] for r in rows],issue_refs=list(dict.fromkeys(r['issue_id'] for r in rows)),
        reason='; '.join(r['missing_need'] for r in rows),evidence_sufficient=False,sufficiency_reason='확정된 원문을 확보한 뒤 판단한다.')
    if 'exploration' in branch['properties']:
        issues={i['id']:i for i in data['issues']}
        decision['exploration']=[{**r,'request_quote':issues[r['issue_id']].get('request_quote',inv.question),'source_quote':''} for r in rows]
    for name in ('queries','structure_filter'):
        if name in choice:decision[name]=deepcopy(choice[name])
    inv.validate(decision,data,actions)
    return decision


def prepare(inv,data,actions):
    """Import only current, server-bound ASSESS targets before the selector."""
    if not enabled(inv):return None
    st=state(inv,data)
    if st.get('pending'):raise ContractError('cannot bypass unknown pending supervisor outcome')
    record({},inv,data,actions,st)
    refresh(inv,st.get('source_goals',[]));commit(inv,st)
    return st


def preselect(inv,data,actions):
    st=prepare(inv,data,actions)
    if st is None or not any(g['status'] in ('REQUIRED','BLOCKED') for g in st.get('source_goals',[])):return None
    # No model proposal or rejected judgment enters this call. resolve uses the
    # exact existing executor/menu, durable intent, budget and resume receipts.
    return resolve(inv,data,actions,{}, {},{'next_action':'FINISH'},
        lambda value:native_decision(inv,data,actions,value),st)
'''
p.write_text(s)
# Native preselection precedes decision_stop, retries and model projection.
edit('law_navigation.py',"    def request_decision(self, data, actions, phase):\n", "    def request_decision(self, data, actions, phase):\n        from . import source_goal_control as source_goals\n        required=source_goals.preselect(self,data,actions)\n        if required is not None:return required\n")
# No-source gate is shared with explicit grounded exclusions, not prose status.
edit('request_repair.py',"        if status in ('NOT_NEEDED', 'UNRESOLVED'):\n", "        if status == 'NOT_NEEDED' and investigation.policy.get('source_goal_control'):\n            from .source_goal_control import validate_gap_closure\n            validate_gap_closure(investigation,data,row)\n            continue\n        if status in ('NOT_NEEDED', 'UNRESOLVED'):\n")
edit('request_repair.py',"        if status != 'RESOLVED': raise ProposalError('unknown gap resolution')\n", "        if status != 'RESOLVED': raise ProposalError('unknown gap resolution')\n        if investigation.policy.get('source_goal_control'):\n            from .source_goal_control import validate_gap_closure\n            validate_gap_closure(investigation,data,row)\n")
# Stop wire projection from deleting proof on NOT_NEEDED (old modern mode also permits full evidence).
edit('decision_projection.py',"if status in ('NOT_NEEDED','UNRESOLVED')", "if status=='UNRESOLVED'")
# Remaining wording describes actual evidence-based semantics.
edit('law_navigation.py',"불필요한 대상은 NOT_NEEDED와 이유를 쓴다.","불필요한 대상은 NOT_NEEDED와 현재 원문 basis_refs 및 대상·쟁점을 연결한 이유를 쓴다.")
p=B/'source_goal_control.py';s=p.read_text()+'''

def validate_gap_closure(inv,data,row):
    """Use the same original proof for gap and source-goal closure."""
    gap=next(g for g in data['assessment_gaps'] if g['gap_id']==row['gap_id'])
    refs=set(row.get('basis_refs',[]));pages={p['id']:p for p in data.get('sources',[]) if p.get('text') and p.get('spans')}
    if not refs or not refs<=pages.keys() or not row.get('reason','').strip():
        raise ProposalError(row['status']+' requires current original basis_refs and target-specific reason; otherwise UNRESOLVED')
    from . import evidence_inventory as inventory
    for ref in refs:inventory.check_presented_page(inv.s,inv.p,pages[ref])
    st=state(inv,data)
    goals=[g for g in st.get('source_goals',[]) if g.get('origin_gap_id')==row['gap_id']]
    if row['status']=='RESOLVED' and any(g['status'] not in ('ACQUIRED','EXCLUDED') for g in goals):
        raise ProposalError('RESOLVED cannot erase an unacquired exact original; read it or give a grounded exclusion')
    # Binding of the issue is structural, legal relevance remains the model's opinion.
    from . import read_judgment
    contexts=read_judgment.context(inv,data,'source-goal-closure') if read_judgment.enabled(inv) else None
    if contexts:
        heads=contexts.get('judgments',[])
        if not any(gap['issue_id'] in h.get('issue_refs',[]) and refs & set(h.get('basis_refs',[])) for h in heads):
            raise ProposalError('gap closure must connect the issue to a retained judgment and current original evidence')


def close_gaps(inv,data,value):
    if not enabled(inv):return
    st=state(inv,data)
    for row in value.get('gap_resolutions',[]):
        if row['status'] not in ('RESOLVED','NOT_NEEDED'):continue
        validate_gap_closure(inv,data,row)
        for goal in st.get('source_goals',[]):
            if goal.get('origin_gap_id')!=row['gap_id']:continue
            if row['status']=='NOT_NEEDED':goal['status']='EXCLUDED';goal['exclusion']=deepcopy(row)
            goal['resolution']=deepcopy(row)
    commit(inv,st)
''';p.write_text(s)
edit('decision_projection.py',"    original=deepcopy(value);correction=None", "    if goals.enabled(inv):goals.close_gaps(inv,data,value)\n    original=deepcopy(value);correction=None")
print('source preselection, full original receipts and closure connected')
