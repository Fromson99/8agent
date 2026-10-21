from pathlib import Path
R=Path(__file__).resolve().parents[3];B=R/'02_BACKEND/lawrag/research/candidates/adr_0914/retained/snapshot/02_BACKEND/semantic_runtime/legal_agent'
p=B/'evidence_inventory.py';s=p.read_text();a=s.index('def acquired_originals_for(');b=s.index('\n\ndef _pack',a)
s=s[:a]+'''def acquired_originals_for(session, state, limit):
    """Prepare acquired originals with governing context; never invent delivery."""
    from .decision_projection import original_groups
    sources={};gathered=defaultdict(list);evidence={};used=0;omitted=[]
    for gid in original_groups(state):
        group=state['groups'][gid];record=state['selected'][gid]
        if group['status']=='EXCLUDED' or not record['complete']:continue
        sid=record['source_id'];did=record['document_id']
        if did not in session.scope:raise ContractError('acquired original inaccessible')
        records=[record]+[r for r in state.get('contexts',{}).values() if r['source_id']==sid]
        bundle={}
        for r in records:
            if not r['complete'] or r['document_id']!=did:raise ContractError('governing context binding changed')
            for e in r['evidence']:
                if e['source_id']!=sid or e['document_id']!=did:
                    raise ContractError('acquired evidence record identity changed')
                session.source.verify(e)
                if e['evidence_id'] not in evidence:bundle[e['evidence_id']]=e
        size=sum(len(p['text']) for e in bundle.values() for p in e['spans'])
        if used+size>limit:
            # Never deliver a subordinate rule while omitting its acquired conditions.
            # Existing paginated investigation remains available for a large bundle.
            omitted.extend(bundle);continue
        used+=size;sources[sid]=record
        for ident,e in bundle.items():
            evidence[ident]=e
            gathered[sid].extend({**p,'evidence_id':ident} for p in e['spans'])
    originals=_pack(session,state,sources,gathered)
    for source in originals:source['delivered_context_only']=True
    return originals,list(evidence.values()),list(dict.fromkeys(omitted))
''' +s[b:];p.write_text(s)
p=B/'law_navigation.py';s=p.read_text();old="            stop_reason=None,answer_coverage='UNASSESSED')\n        return result";new="""            stop_reason=None,answer_coverage='UNASSESSED',recovered_ids=[s['source_id'] for s in originals],
            original_delivery_context={'prepared_for':'ASSESS','navigation_delivery_claimed':False,
                'automatic_adoption':False,'source_absence_proven':False,'character_limit':limit,
                'omitted_evidence_ids':omitted})
        from .investigation_diagnostics import selection_report
        result['diagnostics']=selection_report(result)
        return result""";assert old in s;p.write_text(s.replace(old,new,1))
p=B/'corrected_memory.py';s=p.read_text();old="    def resolve(self,context):\n        context=";new="""    def resolve(self,context):
        from .law_candidates import answer_first
        agent=getattr(getattr(getattr(self.executor,'model',None),'pipeline',None),'term_agent',None)
        continuation = ('''\\n같은 조문·제도·사건을 두고 적용 조건, 예외, 제외 사유, 근거를 추가로 묻는 후속 요청은 제공된 기존 goal을 보완한다. 질문 문장이 달라졌거나 확인 범위가 넓어졌다는 이유만으로 CASE_START를 선택하지 않는다. 기존 목표와 관계없는 별도 주제, 사용자가 별도 새 질문으로 시작하도록 요청한 경우에 CASE_START를 사용한다.
같은 goal의 요청 범위가 바뀌면 그 target을 선택하고 PURPOSE_REVISE로 task를 현재 요청에 맞게 수정한다. 검색계획도 바꿔야 하면 RESEARCH_REPLAN으로 task와 queries를 함께 갱신할 수 있다. 실제로 변하지 않은 facts와 문서 범위는 유지한다. 예전 답변을 현재 후속 질문의 답으로 반복하지 않는다. 현재 요청의 대상과 기존 goal의 관계를 근거로 판단하며, 확정할 수 없는 대상을 추측하지 않는다. 이 정책은 기존 원문·이력을 검증해 재사용할 수 있도록 같은 조사에 연결하는 것이고, 이전 결론을 정답으로 승인하는 것이 아니다.''' if answer_first(getattr(agent,'profile',{})) else '')
        context=""";assert old in s;s=s.replace(old,new,1).replace("self.invoke(RESOLVE+'\\n명령", "self.invoke(RESOLVE+continuation+'\\n명령",1).replace("self.invoke(VERIFY_COMMAND,", "self.invoke(VERIFY_COMMAND+continuation,",1);p.write_text(s)
for p in B.glob('*.py'):compile(p.read_text(),str(p),'exec')
print('Governing context bundles, source identity, handoff diagnostics and opt-in follow-up guidance implemented')
