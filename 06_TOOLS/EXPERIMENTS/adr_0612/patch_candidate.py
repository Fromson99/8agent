from pathlib import Path
R=Path(__file__).resolve().parents[3];B=R/'02_BACKEND/lawrag/research/candidates/adr_0612/bounded-memory/snapshot/02_BACKEND/semantic_runtime/legal_agent'
p=B/'corrected_memory.py';s=p.read_text();s=s.replace("'method_id': choice(list(METHODS)),","'method_id': choice(list(METHODS)),\n    'document_scope_mode': choice(['KEEP','AUTHORIZED','EXPLICIT']),")
s=s.replace("RESOLVE = '''",'''# Model-facing and persisted commands share explicit finite bounds.
COMMAND['properties']['queries'].update(maxItems=4)
COMMAND['properties']['queries']['items']['maxLength']=180
COMMAND['properties']['document_ids'].update(maxItems=160,uniqueItems=True)
COMMAND['properties']['document_ids']['items']['maxLength']=64
COMMAND['properties']['facts'].update(maxItems=16)
FACT['properties']['name']['maxLength']=100
FACT['properties']['value']['maxLength']=600
COMMAND['properties']['restore_fields'].update(maxItems=5,uniqueItems=True)
COMMAND['properties']['task']['maxLength']=600
COMMAND['properties']['reason']['maxLength']=600
RESOLVE = \''' ''')
s=s.replace('조건/결론 유지와 설명/표 변환은 PRESENT/COMPOSE다.','조건/결론 유지와 표 변환은 ANSWER_PRESENT다. 실제 수정 이력·과정 설명은 HISTORY_EXPLAIN이다.')
s=s.replace('한국어 reason과 schema JSON만 출력한다.','한국어 reason과 schema JSON만 출력한다. 검색어는 최대4개, 각180자 이하이며 동의어를 끝없이 나열하지 않는다. document_scope_mode는 기본 AUTHORIZED(새 질문/새 대화 재사용) 또는 KEEP(기존 질문 유지)다. AUTHORIZED와 KEEP이면 document_ids=null이다. 법령명을 언급한 것은 검색 초점일 뿐 문서 접근 제한이 아니다. 사용자가 그 문서만 보라고 명시한 경우에만 EXPLICIT와 해당 document_ids를 쓴다. 단서·시행규칙·시행세칙 등 참조된 근거는 허용 범위 내에서 조사한다.')
s=s.replace('유효한 명령을 거절하기 위한 새로운 규칙을 만들지 않는다.',"document_scope_mode=EXPLICIT는 사용자가 특정 문서만으로 범위를 제한했을 때만 허용한다. 법령명 언급이나 업무 문맥만으로 EXPLICIT를 제안하면 false다. AUTHORIZED는 제공된 허용 문서만 검색 가능하다는 뜻으로 새로운 사건 조건이 아니다. goals가 비어 있고 정정/복원 대상이 없으면 NEED_TARGET은 유효하다. 유효한 명령을 거절하기 위한 새로운 규칙을 만들지 않는다.")
p.write_text(s)
p=B/'memory_methods.py';s=p.read_text();s=s.replace("c=dict(c);method=METHODS.get(c.get('method_id'))",'''c=dict(c)
    mode=c.get('document_scope_mode')
    key=c.get('method_id')
    if mode=='KEEP':
        if c.get('document_ids') is not None:raise ValueError('KEEP scope must not change document IDs')
    elif mode=='AUTHORIZED':
        if key not in ('CASE_START','EXPERIENCE_REUSE','RESEARCH_REPLAN'):raise ValueError('authorized scope change requires a new question, reuse or replan')
        if c.get('document_ids') is not None:raise ValueError('AUTHORIZED scope is host-owned; document_ids must be null')
        if c.get('target') is not None:
            if key!='RESEARCH_REPLAN':raise ValueError('existing experience reuse must keep scope')
            c['document_ids']=[d['id'] for d in context['allowed_documents']]
    elif mode=='EXPLICIT':
        if not c.get('document_ids'):raise ValueError('explicit scope requires document IDs')
    else:raise ValueError('document_scope_mode required')
    method=METHODS.get(c.get('method_id'))''');p.write_text(s)
p=B/'memory_rag.py';s=p.read_text();s=s.replace("'law_names':[d['name'] for d in self.host.catalogue(self.s.sources.scope)],'binding':self.host.binding}","'law_names':[self.s.sources.matcher.documents[d['id']] for d in self.s.sources.matcher.starts(self.host.question(state),self.s.sources.scope)['documents']],'binding':self.host.binding}")
start=s.index("            result=self.invoke('현재 목적·사실과 제공된 원문으로만 판단한다.")
end=s.index('\n        else:',start)
s=s[:start]+'''            feedback=None
            for attempt in range(2):
                result=self.invoke('현재 목적·사실과 제공된 원문으로만 판단한다. 원칙과 단서, 위임된 세칙의 예외를 함께 검토한다. claims의 text는 판단, source_id는 실제 원문 ID, quote는 해당 원문에서 한 글자도 바꾸지 않고 그대로 복사한 인용이다. 현재 사실에 없는 자격이나 기간은 확정하지 말고 조건부 결론과 limitations에 남긴다. 과거 정답은 사용하지 않는다. repair_feedback이 있으면 지적된 잘못을 원문으로 수정한다. JSON만 출력한다.',{**data,'sources':sources,'repair_feedback':feedback},ASSESS,'memory-assess' if not attempt else 'memory-assess-repair')
                try:
                    self.verify_claims(result['claims'],sources)
                    check=self.invoke(JUDGE,{**data,'sources':sources,'assessment':result},CHECK,'memory-assess-check')
                    if not check['valid']:raise MemoryError('judgment check: '+check['reason'])
                    break
                except MemoryError as exc:
                    if attempt:raise
                    feedback={'error':str(exc),'rejected_assessment':result}
''' +s[end:]
s=s.replace("ANSWER=object_schema", "ASSESS['properties']['claims']['maxItems']=12\nASSESS['properties']['limitations']['maxItems']=8\nANSWER=object_schema")
p.write_text(s)
for p in B.glob('*.py'):compile(p.read_text(),str(p),'exec')
print('Candidate patched before freeze.')
