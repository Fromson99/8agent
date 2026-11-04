from common import *
d=read(DES/'after-path.json');S=ROOT/d['candidate']/'snapshot'/d['code_relative'];p=S/'02_BACKEND/semantic_runtime/legal_agent/investigation_supervisor.py';s=p.read_text()
helper='''def ready_for_assessment(inv,data,value,decision,st):
    """Honor a checked terminal proposal; this does not approve a legal answer.

    Source-goal control runs first. Read judgments are checked AFTER the current
    proposal is recorded, rather than using its stale pre-proposal wire view.
    Historical need declarations remain available to the final assessment.
    """
    if value.get('choice')!='FINISH' or decision.get('next_action')!='FINISH':return False
    if any(st.get(k) for k in ('pending','halt','page_pending')):return False
    goals=st.get('goals',[]);issues=[i['id'] for i in data.get('issues',[])]
    if not issues or len(goals)!=len(issues) or {g['issue_id'] for g in goals}!=set(issues):return False
    if any(g['status']!='ANSWERABLE' or g.get('material_need') or g.get('next_answer_change') or not g.get('basis_refs') for g in goals):return False
    if any(g['status'] in ('REQUIRED','BLOCKED') for g in st.get('source_goals',[])):return False
    if progress.assessment_requirements(data,inv) or any(g.get('material') for g in data.get('assessment_gaps',[])):return False
    from . import read_judgment
    if not read_judgment.enabled(inv):return False
    state=read_judgment.state_for(inv,data)
    if not state:return False
    if any(row.get('status')=='OPEN' for name in ('needs','conflicts') for row in state.get(name,{}).values()):return False
    visible=read_judgment.originals(inv,data)
    if not visible:return False
    for jid,row in visible.items():
        head=state.get('heads',{}).get(jid,{})
        if set(row['material'])-set(head.get('seen_material',[])) or head.get('use')=='DEFER':return False
    return True

'''
assert 'def ready_for_assessment' not in s;s=s.replace('def gate(inv,data,actions,payload,value,decision,action_schema,expand,key,*,prepare_page=None):',helper+'def gate(inv,data,actions,payload,value,decision,action_schema,expand,key,*,prepare_page=None):')
old="        if controlled is not None:return controlled\n    if st['halt']"
new="""        if controlled is not None:return controlled
    if ready_for_assessment(inv,data,value,decision,st):
        inv.validate(decision,data,actions)
        old.update(resolved=deepcopy(decision),handoff_reason='VALIDATED_FINISH_NO_CURRENT_INVESTIGATION_NEED')
        inv.s.repo.event('SUPERVISOR_FINISH_HANDOFF',{'originals_preserved':True,
            'legal_sufficiency_approved':False,'final_assessment_required':True,'extra_model_calls':0})
        authorize(inv,data,decision,st);return decision
    if st['halt']"""
assert old in s;s=s.replace(old,new,1);p.write_text(s);print('Isolated supervisor finish handoff updated')
