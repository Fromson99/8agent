from pathlib import Path
import json
R=Path(__file__).resolve().parents[3];S=R/'02_BACKEND/lawrag/research/candidates/adr_0912/answer-first/snapshot';B=S/'02_BACKEND/semantic_runtime/legal_agent'
def edit(name,old,new):
 p=B/name;s=p.read_text();assert old in s,(name,old);p.write_text(s.replace(old,new,1))
edit('law_candidates.py',"'definition_entry': False}","'definition_entry': False, 'answer_first': False}")
edit('law_candidates.py',"'compact_input','definition_entry'))", "'compact_input','definition_entry','answer_first'))")
edit('law_candidates.py',"    if result['compact_input'] and", "    if result['answer_first'] and not result['compact_input']:raise ContractError('answer-first requires compact completion input')\n    if result['compact_input'] and")
p=B/'law_candidates.py';p.write_text(p.read_text()+'''

def answer_first(profile):
    """Ordinary user RAG; workflow research retains its parent's return contract."""
    from .workflow_execution import task_context
    return bool(profile.get('candidate_navigation', {}).get('answer_first')) and not task_context()
''')
edit('evidence_inventory.py', '\ndef _pack(session, state, sources, gathered):', '''
def acquired_originals_for(session, state, limit):
    """Prepare verified acquired spans for ASSESS, without navigation delivery receipts."""
    from .decision_projection import original_groups
    sources={};gathered=defaultdict(list);evidence={};used=0;omitted=[]
    for gid in original_groups(state):
        group=state['groups'][gid];record=state['selected'][gid]
        if group['status']=='EXCLUDED' or not record['complete']:continue
        if record['document_id'] not in session.scope:raise ContractError('acquired original inaccessible')
        for e in record['evidence']:
            session.source.verify(e)
            if e['evidence_id'] in evidence:continue
            size=sum(len(p['text']) for p in e['spans'])
            if used+size>limit:
                omitted.append(e['evidence_id']);continue
            used+=size;evidence[e['evidence_id']]=e
            sources[record['source_id']]=record
            gathered[record['source_id']].extend({**p,'evidence_id':e['evidence_id']} for p in e['spans'])
    originals=_pack(session,state,sources,gathered)
    for source in originals:source['delivered_context_only']=True
    return originals,list(evidence.values()),omitted


def _pack(session, state, sources, gathered):''')
edit('law_navigation.py','    def run(self):\n', '''    def assessment_handoff(self):
        if not (self.modern and self.completion and lc.answer_first(self.s.profile)):
            return None
        if self.p.get('accepted') or self.p.get('decision_retry'):return None
        limit=max(self.s.profile['max_read_chars'],(self.s.profile.get('max_context_chars') or 100000)//2)
        originals,evidence,omitted=inventory.acquired_originals_for(self.s,self.p,limit)
        if not originals:return None
        signature=digest({'question':self.question,'originals':originals})
        if signature in self.p.get('assessment_handoffs',[]):return None
        self.p.setdefault('assessment_handoffs',[]).append(signature)
        self.s.repo.event('ACQUIRED_ORIGINALS_TO_ASSESS',{'material_hash':signature,
            'source_ids':[s['source_id'] for s in originals],'omitted_evidence_ids':omitted,
            'navigation_delivery_claimed':False,'automatic_adoption':False,'evidence_sufficient':False})
        self.save()
        result=self.result({'next_action':'FINISH','queries':[],'reason':'확보 원문의 답변 가능 범위를 먼저 판단',
            'sufficiency_reason':'충분성과 현재 질문에 대한 적용성은 ASSESS가 판단','evidence_sufficient':False})
        result.update(selected_originals=originals,selected_evidence=evidence,
            final_ids=[s['source_id'] for s in originals],final_evidence_ids=[e['evidence_id'] for e in evidence],
            final_packets=[{'packet_id':'acquired-assessment','evidence':evidence}],
            stop_reason=None,answer_coverage='UNASSESSED')
        return result

    def run(self):
''')
# self.question exists? confirmed by constructor field separately.
edit('law_navigation.py','            acquire_basis(self)\n            if self.completion', '            acquire_basis(self)\n            handoff=self.assessment_handoff()\n            if handoff is not None:return handoff\n            if self.completion')
edit('completion_execution.py',"        if fresh and count < limit and can_investigate:", "        from .law_candidates import answer_first\n        defer_to_user = modern and answer_first(self.s.sources.profile) and bool(result['claims'])\n        if fresh and not defer_to_user and count < limit and can_investigate:")
edit('completion_execution.py',"        if fresh:\n            stop_reason", "        if fresh and defer_to_user:\n            stop_reason = 'USER_FOLLOWUP_RESEARCH'\n            self.s.work.event('ASSESSMENT_RESEARCH_DEFERRED_TO_USER', {\n                'gaps': [cc.gap_key(g) for g in fresh], 'supported_claim_ids': [c['claim_id'] for c in result['claims']],\n                'reason': 'publish supported current-question scope with unresolved limitations'})\n        elif fresh:\n            stop_reason")
# The system handles selection and completion; don't infer legal need from reason keywords.
edit('completion_execution.py',"        generation_schema,expand_assessment=", "        from .law_candidates import answer_first\n        answer_policy = ('\\n현재 사용자 질문에 직접 답하는 검증 가능한 주장만 작성한다. 확보한 일반 원칙·수치·조건으로 답할 수 있으면 그 범위를 먼저 답한다. 모든 가능한 예외를 조사한 것으로 말하지 않는다. 실제로 부족한 사항은 gaps에 그대로 남긴다. 질문에 답하는 주장이 하나라도 있으면 추가 조사는 자동 실행하지 않고 사용자의 후속 질문으로 이어진다. 현재 질문에 답할 주장이 전혀 없으면 claims를 비우고 구체적으로 필요한 원문만 요청한다. 후속 질문은 그 질문의 요청 범위를 기준으로 판단하고 이전 질문의 답만 반복하지 않는다.' if modern and answer_first(self.s.sources.profile) else '')\n        generation_schema,expand_assessment=")
edit('completion_execution.py',"+('\\n'+CONDITION_GUIDANCE if modern else ''),", "+('\\n'+CONDITION_GUIDANCE if modern else '')+answer_policy,")
p=S/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json';v=json.loads(p.read_text());v['candidate_navigation']['answer_first']=True;p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
for p in B.glob('*.py'):compile(p.read_text(),str(p),'exec')
print('Candidate edits compiled')
