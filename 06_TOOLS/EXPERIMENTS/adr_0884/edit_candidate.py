from pathlib import Path
R=Path(__file__).resolve().parents[3];S=R/'02_BACKEND/lawrag/research/candidates/adr_0884/focused/snapshot';P=S/'02_BACKEND/semantic_runtime/legal_agent'
def replace(name,old,new):
 p=P/name;s=p.read_text();assert old in s,(name,old[:80]);p.write_text(s.replace(old,new))
guidance='''질문의 주체·행위·업무 문맥을 함께 대조한다. 기간·비율 같은 숫자만 같은 다른 주체의 규정을 직접 근거로 고르지 않는다.
산정 방법을 물으면 분자·분모·합산·환산·제외 기준까지, 분류를 물으면 해당 분류의 조건과 제외·특례까지 원문에서 확인한다. 원문이 그 내용을 다른 조문에 위임했으면 준용 문구만으로 답을 확보한 것이 아니다. 현재 원문이 참조하는 필요한 조문을 연결해서 읽거나 실제 제목·번호로 찾는다. 관련 없는 참조 전체를 읽지는 않는다.
일반 규칙의 조건을 묻는 질문은 확인된 조건별로 답한다. 구체 사건 사실이 없다는 이유로 일반 규칙 답변을 미루지 않는다. 조사 한도에 이르면 확인된 범위와 실제 미확보를 남긴다. 종료 자체를 막는 새로운 의미 검증은 없다.'''
replace('decision_projection.py','부분 원문만으로 조사를 끝낼 필요가 있으면',guidance+'\n부분 원문만으로 조사를 끝낼 필요가 있으면')
replace('decision_projection.py','reason/missing_need는 한 문장으로 쓴다.', '''SEARCH: 적합한 읽기 후보가 없으면 주체·행위 중심의 짧은 검색어를 선택한다. 날짜·기간·비율의 낱말만 넓게 찾지 않는다. 실제 없는 법령명을 추측하지 않는다.
CONNECT: 현재 받은 원문이 필요한 조건·예외·계산을 다른 조문으로 넘겼으면 제공된 연결 도구를 열어 그 조문을 찾는다.
reason/missing_need는 한 문장으로 쓴다.''')
replace('decision_projection.py',"    if not candidates and not basis:return None", "    tools={k:a for k,a in actions.items() if a['action'] in ('RESEARCH','FOLLOW_CONNECTION')}\n    if not candidates and not basis:return None")
replace('decision_projection.py',"key=digest([data['presentation_id'],candidates,basis])", "key=digest([data['presentation_id'],candidates,basis,tools])")
replace('decision_projection.py',"    schema={'type':'object','anyOf':alternatives}",'''    for choice,kind in (('SEARCH','RESEARCH'),('CONNECT','FOLLOW_CONNECTION')):
        targets=[k for k,a in tools.items() if a['action']==kind]
        if not targets:continue
        props={'choice':{'const':choice},'target':{'enum':targets},'issue_id':{'enum':issues},
            'missing_need':reason,'relation':{'enum':['DIRECT','DEPENDENCY'] if current else ['DIRECT']},
            'source_ref':{'type':['string','null'],'enum':[None]+list(current)}}
        if choice=='SEARCH':props['queries']={'type':'array','minItems':1,'maxItems':2,'items':{'type':'string','minLength':2,'maxLength':180}}
        alternatives.append(obj(props))
    schema={'type':'object','anyOf':alternatives}''')
replace('decision_projection.py',"'assessment_gaps':data.get('assessment_gaps',[])}", "'assessment_gaps':data.get('assessment_gaps',[]),\n        'exploration_tools':[{'target':k,'action':a['action'],'label':a['label']} for k,a in tools.items()],\n        'previous_searches':deepcopy(inv.p.get('query_surface_history',[])),\n        'reference_overview':data.get('reference_overview',{})}")
replace('decision_projection.py',"        if value['choice']=='READ':\n            pairs=", "        if value['choice'] in ('SEARCH','CONNECT') and value['relation']=='DEPENDENCY' and value['source_ref'] not in current:\n            raise ProposalError('dependency must select a currently delivered original source_ref')\n        if value['choice']=='READ':\n            pairs=")
replace('decision_projection.py',"kind='READ_ARTICLES' if value['choice']=='READ' else 'FINISH'", "kind={'READ':'READ_ARTICLES','FINISH':'FINISH','SEARCH':'RESEARCH','CONNECT':'FOLLOW_CONNECTION'}[value['choice']]")
replace('decision_projection.py',"    else:\n        issue_map={i['id']:i for i in data['issues']}", "    else:\n        if value['choice'] in ('SEARCH','CONNECT'):\n            value={**value,'selections':[{k:value[k] for k in ('target','issue_id','missing_need','relation','source_ref') }]}\n        issue_map={i['id']:i for i in data['issues']}")
replace('decision_projection.py',"    inv.validate(decision,data,actions)\n", "    if kind=='RESEARCH':decision['queries']=list(value['queries'])\n    inv.validate(decision,data,actions)\n")
# Compact explorations use the same existing tool, receipt, journal and retry limits.
replace('law_navigation.py',"        limit=2 if self.policy['compact_input'] and self.p.get('window')=='search' else 8", "        limit=8")
replace('law_navigation.py',"        from . import investigation_scope\n        if investigation_scope.enabled(data):system+=", "        system+='\\n'+"+repr(guidance)+"\n        from . import investigation_scope\n        if investigation_scope.enabled(data):system+=")
replace('request_entry.py','queries는 최대4개·각180자 이내다.', 'queries는 최대4개·각180자 이내다. 첫 검색어는 업무 문맥을 포함한 주체·핵심 행위 중심으로 짧게 만든다. 기간·비율·연장 같은 일반 낱말만 따로 추가하면 다른 제도가 섞이므로 핵심 주체·행위를 유지한다. 모르는 법령 이름을 만들어 검색하지 않는다.')
replace('completion_execution.py','주체·대상·적용 범위·예외를 보존한다.', '''질문이 일반적인 분류·산식·조건을 묻는다면 사건 적용으로 바꾸지 않는다. 사용자 질문의 가정된 주체는 설명 범위이며 특정 사건 사실을 입증하지 않는다.
분류는 본문과 현재 읽은 예외를 함께 대조해 제외되는 범위와 실제 적용될 범위를 명확히 설명한다. 예외를 읽었는데도 포괄적 일반 규칙만 결론으로 반복하지 않는다. 산식·방법 질문은 준용 근거 이름만 말하지 말고 실제 계산 구조를 설명하며, 그 원문을 못 읽었으면 필요한 조사 gap을 남긴다.
주체·대상·적용 범위·예외를 보존한다.''')
print('Candidate edits only: compact search/connect plus original-based completeness')
