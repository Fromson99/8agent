from pathlib import Path
R=Path(__file__).resolve().parents[3]
C=R/'02_BACKEND/lawrag/research/candidates/adr_0889/scoped/snapshot/02_BACKEND/semantic_runtime/legal_agent'
def edit(name,old,new):
 p=C/(name+'.py');s=p.read_text();assert old in s,(name,old[:80]);p.write_text(s.replace(old,new,1))
edit('relation_read_policy',"REVISION = 'relation-reading-policy-20261006-r2'","REVISION = 'relation-reading-policy-20261018-r3'")
edit('relation_read_policy','적용 여부가 불명확하면 DEFER 또는 FOLLOW다. REQUIRED는 FOLLOW 또는 DEFER만 가능하다.', '적용 여부가 불명확하면 DEFER 또는 FOLLOW다. REQUIRED도 문언상 읽기 단서이며 질문에 대한 적용 결론은 아니다. 질문과 무관하다고 판단하면 DOES_NOT_APPLY와 구체적 사유를 기록하여 SKIP할 수 있다. 필요한 준용·정의의 범위를 임의로 줄이지 않는다.')
edit('relation_read_policy',"            if obligation == 'REQUIRED':\n                raise ValueError('required relation cannot be skipped')\n            if obligation == 'CHECK_APPLICABILITY' and (", "            if obligation in ('REQUIRED', 'CHECK_APPLICABILITY') and (")
edit('decision_projection',"if len(reviewed)>=8 or budget['model_limit']-budget['finalization_reserve']-budget['model_reserved']<3:return None", "if budget['model_limit']-budget['finalization_reserve']-budget['model_reserved']<3:return None")
edit('decision_projection',"payload={'request':inv.question,'issues':data['issues'],'read_candidates':rows,'tool_options':options,\n        'sources':deepcopy(data.get('sources',[])),", "payload={'request':inv.question,'issues':data['issues'],'sources':deepcopy(data.get('sources',[])),\n        'read_candidates':rows,'tool_options':options,")
edit('decision_projection','READ는 read_candidates에서 필요한 본문 최대4개를 읽는다.', 'READ는 read_candidates에서 필요한 본문 최대4개를 읽는다. 일부 항만 받은 상태와 조문 전체 열람은 다르다. 일반적인 방법·조건·위임 여부를 물었고 필요한 답이 아직 없으면, 같은 조문의 미열람 항·호를 포함한 전체 읽기 후보를 먼저 검토한다. 다른 문서 재검색이나 주변 연결 순회로 대신하지 않는다.')
edit('decision_projection','관련 없는 참조를 전부 순회하지 않는다. 이미 읽은 참조는 다시 요청하지 않는다.', '관련 없는 참조를 전부 순회하지 않는다. 이미 읽은 참조는 다시 요청하지 않는다. 질문이 기한·기간·비율·담당자 등 유한한 내용을 요구하고 그 값과 적용 조건을 확인했으면 FINISH한다. 아직 확인하지 않은 다른 예외가 있을 수 있다는 추측만으로 계속 조사하지 않는다. 원문에 구체적인 미확인 조건·위임이 있으면 그 필요한 범위를 확인한다. 특정 항·호만 준용하면 그 범위를 넘는 다른 항·호의 산식·정의를 자동으로 끌어오지 않는다.')
p=C/'decision_projection.py';s=p.read_text();mark='\ndef requested_refs(state):'
helper='''
def offer_partial_articles(inv, data, actions):
    """Expose native whole-article reads after partial acquisition, never adoption."""
    from . import evidence_inventory as inventory, tool_availability as available
    from . import law_candidates as candidates
    records=inv.read_records()
    selected={r['source_id'] for gid,r in inv.p['selected'].items()
              if inv.p['groups'][gid]['status']!='EXCLUDED'}
    offered=[]
    for sid in dict.fromkeys(p['source_id'] for p in data['sources']):
        if sid not in selected:continue
        src=inv.s.tools.sources.get(sid)
        if not src:continue
        identity={'source_id':sid,'document_id':src['document_id']}
        plan,unavailable=available.article_plan(inv.s,identity)
        if unavailable:continue
        hit,scope=plan
        actual=[p for r in records.values() if r['source_id']==sid
                for e in r['evidence'] for p in e['spans']]
        actual.extend(p for b in inv.p['basis_history'].values()
                      if b.get('accepted') and b['source_id']==sid for p in b.get('spans',[]))
        if inventory.covers(inventory.expected(inv.s,src['document_id'],scope['block_ids']),actual):continue
        target=candidates.token(inv.s,'T',['READ_ARTICLES',identity])
        action={'id':target,'action':'READ_ARTICLES','identity':identity,
                'label':src.get('document_name','')+' '+src.get('heading','')+' 미열람 항·호를 포함한 전체 원문 읽기'}
        if inv.recovery_blocked(action):continue
        signature=digest({'action':action,'query':inv.p['catalogue']['query_fingerprint']})
        if signature in inv.p.get('seen_actions',[]):continue
        if target not in actions:
            actions[target]=action
            data['actions'].append({k:action[k] for k in ('id','action','label')})
        offered.append(target)
    data['partial_article_read_options']=offered


def gap_resolution_wire(schema):
    """Declare inactive proof fields as literals; never invent a receipt."""
    wire=deepcopy(schema)
    def visit(node):
        if isinstance(node,list):
            for v in node:visit(v)
        elif isinstance(node,dict):
            for v in list(node.values()):visit(v)
            props=node.get('properties',{})
            if not {'gap_id','status','reason','basis_refs','action_refs'}<=set(props):return
            branches=[]
            for status in props['status'].get('enum',[]):
                branch=deepcopy(node);branch['properties']['status']={'const':status}
                fixed=('basis_refs','action_refs') if status in ('NOT_NEEDED','UNRESOLVED') else ('basis_refs',) if status=='NOT_AVAILABLE' else ()
                for name in fixed:
                    branch['properties'][name]={'type':'array','maxItems':0,'items':deepcopy(props[name]['items'])}
                    if name not in branch['required']:branch['required'].append(name)
                branches.append(branch)
            if branches:node['anyOf']=branches
    visit(wire)
    return wire

'''
assert mark in s;s=s.replace(mark,'\n'+helper+mark,1)
s=s.replace("    def expand(raw):\n        validate(raw,wire)","    wire=gap_resolution_wire(wire)\n    def expand(raw):\n        validate(raw,wire)",1);p.write_text(s)
edit('law_navigation','            retain_requested(self,data)\n            rr.annotate_reused_reads', '            retain_requested(self,data)\n            from .decision_projection import offer_partial_articles\n            offer_partial_articles(self,data,actions)\n            rr.annotate_reused_reads')
edit('completion_execution','다른 항에 붙은 단서를 전체 조문에 확대하지 않는다. 같은 claim을 중복 생성하지 않는다.', '''다른 항에 붙은 단서를 전체 조문에 확대하지 않는다. 일반 방법 질문에는 기본 규칙과 특례 방법을 구분하며, 특례만으로 전체 질문에 답하지 않는다.
서로 다른 요건·효과의 규칙은 별도 claim으로 표현한다. 조건·norms·exceptions를 먼저 작성하고 그 범위에 맞는 action 결론을 마지막에 작성한다. 문구가 다른 취득방법이라는 이유만으로 두 규칙을 배타적이라고 추론하지 않는다.
특정 의무의 제외 규정은 그 의무에 대한 제외다. 재량적 PERMISSION이나 전체 행위의 허용으로 바꾸지 않는다. 예외의 성립에 다른 독립 규칙의 요건까지 충족해야 한다는 조건을 추가하지 않는다. 모의 예: A가 X를 제외하고 B가 Y일 때 적용되면, X는 A에서 제외되며 B는 Y 충족 여부로 별도 판단한다.
질문의 넓은 실무 용어가 특정 법정 자격과 같은 뜻인지 단정하지 않는다. 해당 자격이면 어떤 규칙인지, 아니라면 어떤 조건을 확인해야 하는지 구분해 답한다. ‘각각’이 가리키는 문장 속 대상 범주를 개별 구성원 전체로 확대하지 않는다.
특정 항·호만 준용된 경우 그 항·호의 실제 내용만 연결한다. 인접한 항의 분모·산식·정의나 다른 제도의 적용 범위를 함께 끌어오려면 별도 근거가 필요하다. 한정 준용 범위 밖 조항을 읽지 않았다는 사실만으로 material gap을 만들지 않는다.
필요한 적용 조건과 효과가 원문에 완결되어 있으면 확인된 범위로 답한다. 아직 알지 못하는 다른 예외가 있을지도 모른다는 추측은 원문 부족의 근거가 아니다. 구체적으로 미확인인 요청 사항이나 원문이 명시한 필요한 위임 범위만 gap에 쓴다. 같은 claim을 중복 생성하지 않는다.''')
edit('completion_execution',"            general=deepcopy(node);general['properties']['kind']", "            node['properties']={k:props[k] for k in props if k!='action'}\n            node['properties']['action']=props['action']\n            general=deepcopy(node);general['properties']['kind']")
edit('narrative_answer','새 의무·금액·기한·제재·예외·출처를 만들지 않는다.', '새 의무·금액·기한·제재·예외·출처를 만들지 않는다. 원문의 ‘4.’ 같은 항목 번호만 보고 ‘제4항’으로 바꾸지 않는다. 제공된 문서·조문 표기를 정확히 쓰고 항·호의 계층이 확인되지 않으면 추측하지 않는다. 출처 표시의 정확한 위치는 서버가 제공한다.')
print('Scoped source access, applicability and compact decision changes ready')
