from common import *
C=ROOT/read(ART/'stage.json')['root']
B=C/'02_BACKEND/semantic_runtime/legal_agent'
def edit(name, old, new):
 p=B/name; t=p.read_text(); assert old in t,(name,old[:100]); p.write_text(t.replace(old,new,1))
edit('decision_projection.py','    progress_enabled = progress.enabled(inv)', '''    from . import read_judgment as judgment
    judgment_context = judgment.context(inv,data,key) if judgment.enabled(inv) else None
    if judgment_context is not None:schema=judgment.attach(schema,judgment_context,current,issues)
    progress_enabled = progress.enabled(inv)''')
edit('decision_projection.py','    def expand(value):\n        validate(value,schema)\n        if progress_enabled:', '''    def expand(value):
        validate(value,schema)
        if judgment_context is not None:judgment.validate_review(value,judgment_context,current,issues)
        if progress_enabled:''')
edit('decision_projection.py',"selected=value['selections'] if choice=='READ' else [{k:value[k] for k in ('target','issue_id','missing_need','relation','source_ref')}]", "selected=[{k:r[k] for k in ('target','issue_id','missing_need','relation','source_ref')} for r in value['selections']] if choice=='READ' else [{k:value[k] for k in ('target','issue_id','missing_need','relation','source_ref')}]")
edit('decision_projection.py',"try:return inv.invoke((progress.PROMPT+'\\n' if progress_enabled else '')+EXECUTABLE_CHOICE_PROMPT", "try:return inv.invoke((judgment.PROMPT+'\\n' if judgment_context is not None else '')+(progress.PROMPT+'\\n' if progress_enabled else '')+EXECUTABLE_CHOICE_PROMPT")
edit('decision_projection.py',"    if progress_enabled:payload['answer_progress_context']=progress.context(inv,data)","    if judgment_context is not None:payload['read_judgments']=judgment_context\n    if progress_enabled:payload['answer_progress_context']=progress.context(inv,data)")
edit('decision_projection.py','    decision=expand(value)\n    original=deepcopy(value);correction=None', '    decision=expand(value)\n    if judgment_context is not None:judgment.record(inv,data,value,key,judgment_context,actions)\n    original=deepcopy(value);correction=None')
edit('law_navigation.py',"for key in ('connection_directories','selected_connection_scope','connection_scope_history'):","for key in ('connection_directories','selected_connection_scope','connection_scope_history','read_judgments'):")
edit('connection_scope.py',"    if not inv.policy.get('small_connection_context'):\n        return []", "    if not inv.policy.get('small_connection_context') or inv.policy.get('read_judgment'):\n        return []")
edit('law_candidates.py',"'small_connection_context': False}","'small_connection_context': False, 'read_judgment': False}")
edit('law_candidates.py',"'definition_context','small_connection_context')):","'definition_context','small_connection_context','read_judgment')):")
edit('law_candidates.py',"    if result['structure_first'] and result['mode'] != 'law-first-v1':", """    if result['read_judgment'] and (not result['compact_input'] or not result['investigation_control']
            or result['mode'] != 'law-first-v1' or result['answer_first'] or result['answer_progress_control']
            or result['completion_policy_version'] == 'investigation-completion-v4'):
        raise ContractError('read judgment requires modern compact navigation without automatic answer-progress handoff')
    if result['structure_first'] and result['mode'] != 'law-first-v1':""")
p=C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json';v=read(p);v['candidate_navigation']['read_judgment']=True;save(p,v)
edit('read_judgment.py',"digest(p.get('text', ''))", "digest(p['text'])")
edit('read_judgment.py',"'conflicts': list(deepcopy(state.get('conflicts', {})).values()),", "'conflicts': list(deepcopy(state.get('conflicts', {})).values()),\n        'previous_final_review': deepcopy(state.get('final_reviews', [])[-1:]),")
edit('read_judgment.py',"    for field, known in [('need_updates', ctx['needs']),", """    reobserved = {'N' + digest([r['judgment_id'], ' '.join(t.split())])[:24]
                  for r in review['judgments'] for t in r['missing']}
    if any(u['id'] in reobserved and u['status'] != 'OPEN' for u in review['need_updates']):
        problems.append('same response cannot reopen and close the same need')
    for field, known in [('need_updates', ctx['needs']),""")
