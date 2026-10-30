from common import *
S=ROOT/read(DES/'candidate.json')['root']/'snapshot';b=S/'02_BACKEND/semantic_runtime/legal_agent'
p=b/'source_goal_control.py';s=p.read_text().replace("    from .unit_reading import blocks\n    wanted=", "    if not binding.get('expected'):return []\n    from .unit_reading import blocks\n    wanted=")
s+='''

def pending_before_selection(inv):
    """Only durable exact goals can precede model/no-progress handoff."""
    if not enabled(inv):return False
    goals=[]
    from .investigation_supervisor import seal
    for st in inv.p.get('investigation_supervisor',{}).values():
        if st.get('state_hash')!=seal(st):raise ContractError('source goal priority state changed')
        goals.extend(st.get('source_goals',[]))
    if any(g['status'] in ('REQUIRED','BLOCKED') for g in goals):return True
    for gap in inv.p.get('assessment_gaps',[]):
        if not gap.get('material') or gap.get('kind')=='MISSING_FACT' or gap.get('target_binding',{}).get('status')!='EXACT':continue
        for pair in gap['target_binding']['pairs']:
            node=inv.s.matcher.units.get((pair['document_id'],str(pair['unit_id'])))
            if node and node.get('coordinate_scope'):
                identity=digest([gap['issue_id'],pair['document_id'],pair['coordinate'],node['coordinate_scope']])
                if not any(g['identity']==identity and g['status'] in ('ACQUIRED','EXCLUDED') for g in goals):return True
    return False
''';p.write_text(s)
p=b/'law_navigation.py';s=p.read_text().replace("            handoff=self.assessment_handoff()", "            from .source_goal_control import pending_before_selection\n            required_priority=pending_before_selection(self)\n            handoff=None if required_priority else self.assessment_handoff()")
s=s.replace("if budget['model_limit']-budget['finalization_reserve']-budget['model_reserved']<2:","if not required_priority and budget['model_limit']-budget['finalization_reserve']-budget['model_reserved']<2:")
s=s.replace("if self.p['no_progress']>=self.s.profile['max_no_progress']:","if not required_priority and self.p['no_progress']>=self.s.profile['max_no_progress']:")
p.write_text(s)
