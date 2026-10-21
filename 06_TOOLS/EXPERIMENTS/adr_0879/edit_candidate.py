from pathlib import Path
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0879/focused/snapshot';P=C/'02_BACKEND/semantic_runtime/legal_agent'
p=P/'decision_projection.py';s=p.read_text();s=s.replace("if single:single_actions.add(kind)","if single:\n                single_actions.add(kind)\n                if len(issue_quotes)==1:exploration['maxItems']=1")
s+='''

READ_CHOICE_PROMPT = """현재 질문에 필요한 원문을 읽을 대상을 고른다. 아래는 조회 가능한 본문 읽기 선택지이며 아직 원문 근거가 아니다.
질문의 문서·조문 또는 그 질문을 답하는 데 필요한 조문이 있으면 selections에 target과 issue_id, 짧은 missing_need를 고른다.
선택하면 서버가 제목만이 아니라 지정된 조문의 본문을 읽는다. sources가 아직 없다는 것은 읽어야 할 이유이며 재검색이나 종료 이유가 아니다.
내용이 부족할지는 본문을 읽은 다음 판단한다. 후보 전체 순회는 하지 않는다. 필요한 대상만 최대 네 개 고른다.
모든 후보가 질문과 무관하거나 이미 읽었다면 selections를 비우고 skip_reason에 구체 이유 한 문장만 쓴다. 선택한 경우 skip_reason은 빈 문자열이다.
법률 답변이나 검색식을 쓰지 않는다. 같은 target과 issue_id 조합은 한 번만 쓴다."""


def choose_read(inv, data, actions, phase):
    """Bounded relevance choice before source-free navigation; no inferred read."""
    from . import output_contract as output
    from .completion_contracts import obj
    if not inv.modern or data.get('sources') or not data.get('issues'):return None
    candidates={k:a for k,a in actions.items() if a['action']=='READ_ARTICLES'}
    if not candidates:return None
    # Existing operation receipts remove already presented actions from this menu.
    key=digest([data['presentation_id'],candidates])
    reviewed=inv.p.setdefault('read_choice_reviews',{})
    if key in reviewed and reviewed[key].get('skipped'):return None
    if key not in reviewed:
        budget=inv.s.repo.budget()
        if len(reviewed)>=4 or budget['model_limit']-budget['finalization_reserve']-budget['model_reserved']<3:return None
        reviewed[key]={'started':True};inv.save()
    rows=[]
    def walk(value,doc=''):
        if isinstance(value,dict):
            doc=value.get('document_name',value.get('name',doc))
            handle=value.get('read_action')
            if handle in candidates:
                rows.append({'target':handle,'document':doc,**{k:value[k] for k in ('article','heading','preview','coordinate') if k in value}})
            for name,v in value.items():
                if name not in ('sources','investigation_chain'):walk(v,doc)
        elif isinstance(value,list):
            for v in value:walk(v,doc)
    walk(data.get('laws',[]));walk(data.get('structure_catalogue',{}))
    known={r['target'] for r in rows}
    rows.extend({'target':k,'label':a['label'],'document_id':a['identity'].get('document_id')} for k,a in candidates.items() if k not in known)
    rows=list({r['target']:r for r in rows}.values())
    schema=obj({'selections':{'type':'array','maxItems':4,'items':obj({
        'target':{'type':'string','enum':list(candidates)},'issue_id':{'type':'string','enum':[i['id'] for i in data['issues']]},
        'missing_need':{'type':'string','minLength':1,'maxLength':240}})},
        'skip_reason':{'type':'string','maxLength':320}})
    payload={'request':inv.question,'issues':data['issues'],'read_candidates':rows,
             'already_read':data.get('saved_inventory',[])}
    def verify(value):
        validate(value,schema)
        pairs=[(r['target'],r['issue_id']) for r in value['selections']]
        if len(pairs)!=len(set(pairs)):raise ProposalError('one row per target and issue')
        if not pairs and not value['skip_reason'].strip():raise ProposalError('empty selection requires a concrete skip reason')
    value=output.bounded_decision(inv.s.repo,'read-choice',payload,schema,
        lambda p,a:inv.invoke(READ_CHOICE_PROMPT,p,schema,phase+'-read-choice'+('-repair' if a else ''),min(180,inv.left())),
        verify,identity={'binding':inv.p['binding'],'presentation':data['presentation_id'],'key':key})
    if not value['selections']:
        reviewed[key].update(skipped=True,reason=value['skip_reason']);inv.save()
        inv.s.repo.event('READ_CHOICE_SKIPPED',{'key':key,'reason':value['skip_reason'],'absence_proven':False})
        return None
    from .law_navigation import decision_schema
    canonical=decision_schema(data,actions,{b['id'] for b in data['branches']})
    branch=next(b for b in canonical['anyOf'] if b['properties']['next_action']['const']=='READ_ARTICLES')
    decision={}
    for name,rule in branch['properties'].items():
        if 'const' in rule:decision[name]=rule['const']
        elif len(rule.get('enum',[]))==1:decision[name]=rule['enum'][0]
        elif rule.get('type')=='array':decision[name]=[]
    issue_map={i['id']:i for i in data['issues']}
    decision.update(next_action='READ_ARTICLES',targets=list(dict.fromkeys(r['target'] for r in value['selections'])),
        issue_refs=list(dict.fromkeys(r['issue_id'] for r in value['selections'])),reason='; '.join(r['missing_need'] for r in value['selections']),
        notes='',evidence_sufficient=False,sufficiency_reason='선택한 원문을 읽은 뒤 충분성을 판단한다.')
    if 'exploration' in branch['properties']:
        request=(data.get('investigation_scope') or {}).get('request',inv.question)
        decision['exploration']=[{**r,'request_quote':issue_map[r['issue_id']].get('request_quote',request),'relation':'DIRECT','source_quote':''} for r in value['selections']]
    inv.validate(decision,data,actions)
    inv.s.repo.event('READ_CHOICE_SELECTED',{'key':key,'selected':value['selections'],'canonical_hash':digest(decision),'automatic_adoption':False})
    return decision
'''
p.write_text(s)
p=P/'law_navigation.py';s=p.read_text();needle="        system=SELECTABLE_SYSTEM if self.policy['selectable_search'] else SYSTEM";assert s.count(needle)==1;s=s.replace(needle,"        from .decision_projection import choose_read\n        read_choice=choose_read(self,data,actions,phase)\n        if read_choice is not None:return read_choice\n"+needle);p.write_text(s)
p=P/'completion_execution.py';s=p.read_text();insert='''
MODERN_ASSESS_PROMPT = """제공된 원문 evidence_options로 현재 질문에 직접 답한다. 각 쟁점의 첫 claim은 직접 결론으로 쓰고 요건·예외·차이는 한 번만 설명한다.
일반 규칙은 조건부로 설명하고 특정 사건 적용은 실제 사용자 사실에만 의존한다. 법령으로 사실 충족을 증명하지 않는다.
주체·대상·적용 범위·예외를 보존한다. 일부 요건 충족이나 금지 제외만으로 전체 적법성을 단정하지 않는다.
다른 항에 붙은 단서를 전체 조문에 확대하지 않는다. 같은 claim을 중복 생성하지 않는다. 인용은 제공된 ID만 선택한다.
issue_assessments에는 해당 쟁점의 충족 상태만 선택한다. disposition과 쟁점별 진단 reason은 서버가 조립한다. 상태 선택의 내부 검토나 반복 설명은 쓰지 않는다.
요청에 필요한 미확인 내용만 gaps에 남긴다. gap reason은 부족한 내용 한 문장이다. 법령 원문 미확인은 사용자 사실 부족이 아니다.
일반 규칙 질문에는 특정 사건 사실을 요구하지 않는다. 요청에 필요 없는 참조는 조사하지 않아도 된다.
같은 부족은 previous_gap_key로 연결하고 material=true를 보존한다. 조사 재개 가능 여부와 최종 상태는 서버가 결정한다.
이미 읽은 원문을 미확보라고 쓰지 않는다. 현재 sources와 evidence_options가 실제 근거이며 목록·미리보기·과거 답변은 근거가 아니다.
법률 내용은 claim, 부족은 gap에 한 번씩 쓴다. repair_feedback의 구체 오류만 수정한다."""


def assessment_projection(schema):
    """Keep model coverage judgment; derive only redundant control diagnostics."""
    wire=deepcopy(schema)
    wire['properties'].pop('disposition');wire['required'].remove('disposition')
    row=wire['properties']['issue_assessments']['items']
    row['properties'].pop('reason');row['required'].remove('reason')
    wire['properties']['gaps']['items']['properties']['reason']['maxLength']=512
    def expand(raw):
        output.validate_shape(raw,wire)
        value=deepcopy(raw)
        for row in value['issue_assessments']:
            claims=sum(row['issue_id'] in c['issue_refs'] for c in value['claims'])
            gaps=sum(g['issue_id']==row['issue_id'] for g in value['gaps'])
            row['reason']=f"판단 상태 {row['status']}; 근거 주장 {claims}개, 미확인 {gaps}개."
        value['disposition']=('NEEDS_INVESTIGATION' if any(g['material'] and g['kind']!='MISSING_FACT' for g in value['gaps']) else
            'ANSWER' if all(r['status']=='COVERED' for r in value['issue_assessments']) else 'LIMITED_ANSWER')
        output.validate_shape(value,schema)
        return value
    return wire,expand

'''
s=s.replace("CLOSED_STATUSES =",insert+"CLOSED_STATUSES =")
needle="        for attempt in range(start,2):";s=s.replace(needle,"        generation_schema,expand_assessment=assessment_projection(schema) if modern else (schema,lambda v:v)\n"+needle)
s=s.replace("self.invoke(ASSESS_PROMPT+task_instructions()", "expand_assessment(self.invoke((MODERN_ASSESS_PROMPT if modern else ASSESS_PROMPT)+task_instructions()")
s=s.replace("'repair_feedback': feedback}, schema,\n                    'memory-assess' if not attempt else 'memory-assess-repair')","'repair_feedback': feedback}, generation_schema,\n                    'memory-assess' if not attempt else 'memory-assess-repair'))")
p.write_text(s)
for p in P.glob('*.py'):compile(p.read_text(),str(p),'exec')
print('Three isolated product files edited; model relevance remains model-owned')
