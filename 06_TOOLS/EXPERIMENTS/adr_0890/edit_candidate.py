from pathlib import Path
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0890/frontier/snapshot/02_BACKEND/semantic_runtime/legal_agent'
def edit(name,old,new):
 p=C/(name+'.py');s=p.read_text();assert s.count(old)==1,(name,old[:80],s.count(old));p.write_text(s.replace(old,new))
edit('law_navigation',"if search_window or self.p.get('window')=='law':", "if self.modern or search_window or self.p.get('window')=='law':")
edit('request_repair',"    for did, spans in spans_by_document(state, refs).items():\n",'''    acquired = spans_by_document(state, refs)
    # Native read receipts are content progress before the next model delivery.
    # Keep presentation/adoption flags unchanged; previews have no receipts here.
    for record in state.get('selected', {}).values():
        did = record.get('document_id')
        if did:
            acquired.setdefault(did, []).extend(p for e in record.get('evidence', [])
                                                for p in e.get('spans', []))
    for did, spans in acquired.items():
''')
with (C/'request_repair.py').open('a') as f:f.write('''

def no_progress_recovery(inv):
    """One durable selection, owned by the existing decision loop, per request."""
    if not inv.modern:return None
    saved = inv.p.get('no_progress_recovery')
    if saved:
        if saved['status'] == 'COMPLETED':return None
        if saved['status'] != 'RESERVED':raise ContractError('unknown no-progress recovery status')
        if (saved['binding'] != digest(inv.p['binding']) or
                saved['state_version'] != inv.p['state_version'] or
                saved['epoch'] != inv.p.get('investigation_epoch',0) or
                saved['snapshot_hash'] != digest(saved['snapshot'])):
            raise ContractError('no-progress recovery snapshot changed')
        return deepcopy(saved['snapshot'])
    data, actions = inv.view()
    useful = {'READ_ARTICLES','READ_SCOPE','READ_PARENT','SEARCH_BODY','SEARCH_STRUCTURE',
              'RESEARCH','FOLLOW_CONNECTION','OPEN_LAW','OPEN_STRUCTURE','BROWSE_STRUCTURE',
              'NEXT_ARTICLES','NEXT_LAWS','NEXT_STRUCTURE','NEXT_HITS'}
    if not any(a['action'] in useful for a in actions.values()):return None
    phase = 'source-law-navigation-'+str(inv.p['turn']+1)
    snapshot = [deepcopy(data),deepcopy(actions),phase]
    inv.p['no_progress_recovery'] = {'status':'RESERVED','binding':digest(inv.p['binding']),
        'state_version':inv.p['state_version'],'epoch':inv.p.get('investigation_epoch',0),'snapshot':snapshot,'snapshot_hash':digest(snapshot),
        'unchanged_turns':inv.p['no_progress'],'phase':phase}
    inv.s.repo.event('INVESTIGATION_NO_PROGRESS_RECOVERY',{
        'snapshot_hash':digest(snapshot),'unchanged_turns':inv.p['no_progress'],
        'max_selections':1,'counter_reset':False,'budget':inv.s.repo.budget()})
    inv.save()
    return deepcopy(snapshot)


def finish_no_progress_recovery(state, phase):
    saved = state.get('no_progress_recovery')
    if saved and saved['status']=='RESERVED' and saved['phase']==phase:
        saved['status']='COMPLETED'
''')
edit('law_navigation',"        while True:\n            acquire_basis(self)","        while True:\n            recovery = None\n            acquire_basis(self)")
edit('law_navigation',"                if self.p['no_progress']>=self.s.profile['max_no_progress']:\n                    return self.bounded_result('NO_PROGRESS')", "                if self.p['no_progress']>=self.s.profile['max_no_progress']:\n                    recovery = rr.no_progress_recovery(self)\n                    if recovery is None:return self.bounded_result('NO_PROGRESS')")
edit('law_navigation',"'investigation_epoch','decision_retry_history') if k in self.p", "'investigation_epoch','decision_retry_history','no_progress_recovery') if k in self.p")
edit('law_navigation',"                else:\n                    data, actions = self.view(); phase = 'source-law-navigation-'+str(self.p['turn']+1)","                elif recovery is not None:\n                    data, actions, phase = recovery\n                else:\n                    data, actions = self.view(); phase = 'source-law-navigation-'+str(self.p['turn']+1)")
edit('law_navigation',"            applied = self.execute(decision, data, actions)\n", "            applied = self.execute(decision, data, actions)\n            rr.finish_no_progress_recovery(self.p, phase)\n")
edit('decision_projection',"options.extend({'choice':choice,'target':k,'label':actions[k]['label']} for k in targets)", "options.extend({'choice':choice,'target':k,'label':actions[k]['label'],\n                        'scope':{n:actions[k]['identity'][n] for n in ('document_id','unit_id') if n in actions[k]['identity']}} for k in targets)")
edit('decision_projection',"        'structure_search_history':data.get('structure_search_history',[])}", """        'structure_search_history':data.get('structure_search_history',[]),
        'navigation_feedback':{
            'recent_outcomes':[{k:deepcopy(step[k]) for k in ('action','status','outcome','structure_lookup','progress') if k in step}
                               for step in inv.p.get('action_chain',{}).get('steps',[])[-3:]],
            'lookup_failure':deepcopy(inv.p.get('structure_page',{}).get('failure')),
            'unchanged_turns':inv.p.get('no_progress',0),
            'last_recovery_selection':inv.p.get('no_progress_recovery',{}).get('status')=='RESERVED'}}""")
edit('decision_projection',"RESEARCH/SEARCH_BODY는 짧은 queries로 본문을 찾는다.","""현재 단계는 필요한 원문 확보다. 이미 받은 문장의 해석은 다음 평가에서 하므로, 해석이 확정되지 않았다는 이유만으로 같은 문장을 계속 검색하지 않는다.
navigation_feedback은 실제 도구 결과다. 조회 실패는 원문 부재가 아니다. 마지막 복구 선택에서는 실패 원인을 보고 유효한 다른 경로를 고르거나 확인 범위로 종료한다.
CATALOG_SEARCH는 실제 문서명·조문번호 단서를 위한 구조 조회다. document_id가 없는 target에 일반 본문 낱말만 넣으면 문서를 찾을 수 없다. 문서를 알면 그 문서의 LOCATE로 제목/번호를 찾고, 내용만 알면 RESEARCH/SEARCH_BODY를 쓴다.
RESEARCH/SEARCH_BODY는 짧은 queries로 본문을 찾는다.""")
edit('completion_execution',"        model_sources=sources\n", "        model_sources=sources\n        model_options=options\n")
edit('completion_execution',"            context,model_sources=v5.project_assessment(context,sources,options)\n", "            context,model_sources=v5.project_assessment(context,sources,options)\n            model_sources,model_options=assessment_original_view(model_sources,options)\n")
edit('completion_execution',"'issues': self.issues, 'sources': model_sources, 'evidence_options': options,", "'issues': self.issues, 'sources': model_sources, 'evidence_options': model_options,")
with (C/'completion_execution.py').open('a') as f:f.write('''

def assessment_original_view(sources, options):
    """Host owns span/receipt verification; models receive exact originals once."""
    headers = [{k:deepcopy(row[k]) for k in ('source_id','document_name','heading',
                'evidence_refs','article_complete','read_scopes') if k in row} for row in sources]
    originals = [{'id':row['id'],'text':row['text']} for row in options]
    return headers, originals
''')
edit('completion_execution',"MODERN_ASSESS_PROMPT = \"\"\"제공된 원문 evidence_options로 현재 질문에 직접 답한다.", "MODERN_ASSESS_PROMPT = \"\"\"evidence_options의 id/text는 실제 읽은 원문이고 sources의 evidence_refs가 문서·조문과 연결한다. 위치·해시·채택 상태는 서버가 관리한다. 준용 대상도 해당 원문 text가 있으면 그 실제 내용을 답에 사용하며, 이미 제공된 text를 원문 미제공이라고 쓰지 않는다.\n제공된 원문 evidence_options로 현재 질문에 직접 답한다.")
edit('completion_v6',"    for claim in value['claims']:\n        if claim['rule'] is None:continue\n        for norm in claim['rule']['norms']:\n", "    for ci,claim in enumerate(value['claims']):\n        if claim['rule'] is None:continue\n        for ni,norm in enumerate(claim['rule']['norms']):\n")
edit('completion_v6',"                raise ProposalError('norm wording reverses the source permission/obligation/prohibition')", """                from .output_contract import DecisionConflict, issue
                raise DecisionConflict('norm wording reverses the source permission/obligation/prohibition', [
                    issue('SOURCE_MODALITY_WORDING',f'/claims/{ci}/rule/norms/{ni}/text',
                          related=(f'/claims/{ci}/rule/norms/{ni}/source_ref',),
                          expected={'claim_id':claim.get('claim_id'),'source_modality':actual,
                                    'proposed_modality':proposed,'source_refs':norm['evidence_refs'],
                                    'source_quote':quote,'proposed_text':norm['text'],
                                    'instruction':'해당 norm.text의 허용·의무·금지 표현을 원문과 대조하여 수정하라. 출처나 사실을 바꾸거나 같은 문장을 반복하지 마라.'})])""")
for p in C.glob('*.py'):compile(p.read_text(),str(p),'exec')
print('Frontier, acquired-content progress, one durable recovery, compact originals and precise correction implemented')

edit('law_navigation','if search_window else []\n','if (search_window or self.modern) else []\n')
