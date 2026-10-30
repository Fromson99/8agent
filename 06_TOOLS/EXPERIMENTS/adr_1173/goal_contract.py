from common import *
S=ROOT/read(DES/'candidate.json')['snapshot'];B=S/'02_BACKEND/semantic_runtime/legal_agent'
def edit(n,a,b):
 p=B/n;s=p.read_text();assert a in s,(n,a[:70]);p.write_text(s.replace(a,b))
edit('source_goal_control.py',"                offer=record.get('offer',{})\n                identity={'source_id':record.get('source_id'),'document_id':record['document_id'],'unit_id':offer.get('unit_id')}\n                if not matches(inv,identity,goal):continue", """                offer=record.get('offer',{})
                exact=[x for x in identities if x.get('source_id')==record.get('source_id')]
                if not exact:continue""")
edit('source_goal_control.py',"                if not expected and offer.get('block_ids'):\n                    expected=inventory.expected(inv.s,goal['document_id'],offer['block_ids'])", """                if not expected:
                    from . import unit_reading
                    identity=exact[0];uid=identity.get('unit_id')
                    if uid is None:uid=inv.s.matcher.sources[identity['source_id']].get('unit_id')
                    if uid is None:continue
                    blocks=unit_reading.blocks(inv.s,goal['document_id'],str(uid),'subtree')
                    expected=inventory.expected(inv.s,goal['document_id'],blocks)""")
edit('source_goal_control.py',"                for e in record['evidence']:inv.s.repo.verify_evidence(e) if hasattr(inv.s.repo,'verify_evidence') else None", "                for e in record['evidence']:\n                    if e['document_id']!=record['document_id'] or e['source_id']!=record['source_id']:raise ContractError('source goal original identity changed')\n                    inv.s.source.verify(e)")
# Explicit model goal IDs mechanically dispatch to native target.
edit('decision_projection.py',"    schema={'type':'object','anyOf':alternatives}\n", """    from . import source_goal_control as goals
    if goals.enabled(inv):
        goal_ids=[g['goal_id'] for g in goals.state(inv,data).get('source_goals',[]) if g['status'] in ('REQUIRED','BLOCKED')]
        if goal_ids:alternatives.append(obj({'choice':{'const':'SOURCE_GOAL'},'goal_id':{'enum':goal_ids}}))
    schema={'type':'object','anyOf':alternatives}
""")
edit('decision_projection.py',"        choice=value['choice'];branch=bindings[choice];kind=branch['properties']['next_action']['const']", """        choice=value['choice']
        if choice=='SOURCE_GOAL':return goals.from_goal_id(inv,data,actions,value['goal_id'])
        branch=bindings[choice];kind=branch['properties']['next_action']['const']""")
# Keep tool identity on server. Model lists only document/coordinate selection.
for name in ('decision_projection.py','investigation_supervisor.py'):
 edit(name,"goals.options(data,actions)","goals.public_options(data,actions)")
p=B/'source_goal_control.py';s=p.read_text()+'''

def public_options(data,actions):
    return [{'document_id':r['document_id'],'document_name':r['document_name']} for r in options(data,actions)]

def from_goal_id(inv,data,actions,goal_id):
    goal=next((g for g in state(inv,data).get('source_goals',[]) if g['goal_id']==goal_id and g['status'] in ('REQUIRED','BLOCKED')),None)
    if goal is None:raise ProposalError('source goal is not currently offered')
    common={'issue_id':goal['issue_id'],'missing_need':goal['reason'],'relation':'DIRECT','source_ref':None}
    reads=[k for k,a in actions.items() if a['action']=='READ_ARTICLES' and matches(inv,a['identity'],goal)]
    if len(reads)==1 and 'READ' not in goal['routes']:
        return native_decision(inv,data,actions,{'choice':'READ','selections':[dict(common,target=reads[0])]})
    lookups=[k for k,a in actions.items() if a['action']=='SEARCH_STRUCTURE' and a['identity'].get('document_id')==goal['document_id']]
    if lookups and 'LOOKUP' not in goal['routes']:
        return native_decision(inv,data,actions,dict(common,choice='LOCATE',target=lookups[0],structure_filter={'coordinate':goal['coordinate'],'coordinate_scope':goal['coordinate_scope'],'title':''}))
    raise ProposalError('source goal has no remaining authorized exact route; retain UNRESOLVED')
''';p.write_text(s)
# Goal dispatch after a validated declaration uses mechanical native expansion,
# not a synthetic model review that could be blocked by irrelevant revisions.
edit('source_goal_control.py',"        try:accepted=expand(chosen)", "        try:accepted=native_decision(inv,data,actions,chosen) if hasattr(inv,'modern') else expand(chosen)")
# Do not bypass pending transport, ACL, hash or stale state. In normal operation
# existing goals are drained before output_contract/independent_read_recovery.
# Declared proof is checked in both goal and gap validators.
edit('source_goal_control.py',"            raise ProposalError('source_goal_exclusions require an existing goal, reason and current original evidence')", "            raise ProposalError('source_goal_exclusions require an existing goal, reason and current original evidence')\n        if hasattr(inv,'modern'):\n            from .evidence_inventory import check_presented_page\n            for ref in row['basis_refs']:check_presented_page(inv.s,inv.p,next(p for p in data['sources'] if p['id']==ref))")
# Add routing module to engine hashes for actual selected server consumers.
p=Path(__file__).parent/'freeze.py';s=p.read_text().replace("d['files']['02_BACKEND/semantic_runtime/legal_agent/source_goal_control.py']=sha(S/'02_BACKEND/semantic_runtime/legal_agent/source_goal_control.py')", "d['files']['02_BACKEND/semantic_runtime/legal_agent/source_goal_control.py']=sha(S/'02_BACKEND/semantic_runtime/legal_agent/source_goal_control.py');d['files']['02_BACKEND/semantic_runtime/legal_agent/provider_routing.py']=sha(S/'02_BACKEND/semantic_runtime/legal_agent/provider_routing.py')")
p.write_text(s)
print('goal ID selection and original verification connected')
