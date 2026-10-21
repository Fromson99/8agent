from pathlib import Path
R=Path(__file__).resolve().parents[3];P=R/'02_BACKEND/lawrag/research/candidates/adr_0881/retained/snapshot/02_BACKEND/semantic_runtime/legal_agent'
p=P/'decision_projection.py';s=p.read_text().replace('current_originals','sources')
s=s.replace("'sources':[{k:s[k] for k in ('id','document_name','heading','text','selected_scope_complete') if k in s} for s in current.values()],", "'sources':deepcopy(data.get('sources',[])), 'presentation_id':data['presentation_id'], 'state_version':data.get('state_version'),")
s=s.replace("    value=output.bounded_decision(inv.s.repo,'read-choice',payload,schema,\n        lambda p,a:inv.invoke(READ_CHOICE_PROMPT,p,schema,phase+'-read-choice'+('-repair' if a else ''),min(180,inv.left())),", "    def invoke(payload,attempt):\n        try:return inv.invoke(READ_CHOICE_PROMPT,payload,schema,phase+'-read-choice'+('-repair' if attempt else ''),min(180,inv.left()))\n        finally:\n            from . import evidence_inventory as inventory\n            if inv.control and inventory.reconcile_delivery(inv.s,inv.p,data,phase+'-read-choice'):inv.save()\n    value=output.bounded_decision(inv.s.repo,'read-choice',payload,schema,\n        invoke,")
s+='''

def requested_refs(state):
    """Available delivered context, never inferred adoption or legal relevance."""
    wanted=set(state.get('requested_originals',[]))
    return [ref for ref,b in state.get('basis_history',{}).items()
        if b.get('branch_id') in wanted and b.get('accepted') and b.get('spans')
        and state['groups'][b['branch_id']]['status'] not in ('DEFERRED','EXCLUDED')]


def retain_requested(inv,data):
    from . import evidence_inventory as inventory
    refs=set(requested_refs(inv.p));seen={p['id'] for p in data['sources']}
    used=sum(len(p.get('text','')) for p in data['sources'])
    limit=max(inv.s.profile['max_read_chars'],(inv.s.profile.get('max_context_chars') or 100000)//2)
    included=[];omitted=[]
    for gid in inv.p.get('requested_originals',[]):
        for ref,b in inv.p['basis_history'].items():
            if ref not in refs or ref in seen or b['branch_id']!=gid:continue
            group=inv.p['groups'][gid]
            # A changed selected scope/page plan must not relabel old spans.
            number=b['page']-1
            if number>=len(group['page_plan']):continue
            page=inv.render_page(group,number)
            if page['id']!=ref:continue
            inventory.check_page(inv.s,inv.p,page)
            if used+len(page['text'])>limit:omitted.append(ref);continue
            data['sources'].append(page);seen.add(ref);used+=len(page['text']);included.append(ref)
            if not any(x['id']==ref for x in data['basis']):
                data['basis'].append({k:page[k] for k in ('id','branch_id','source_id','page','total_pages')})
    if included or omitted:
        data['retained_original_context']={'included':included,'omitted_by_context_budget':omitted,'character_limit':limit,'automatic_adoption':False}
    return included
'''
p.write_text(s)
p=P/'law_navigation.py';s=p.read_text();s=s.replace("        if self.modern:\n            rr.annotate_reused_reads(self,data,actions)","        if self.modern:\n            from .decision_projection import retain_requested\n            retain_requested(self,data)\n            rr.annotate_reused_reads(self,data,actions)")
s=s.replace("                plan['completed'][target]=gid;plan['status']='STARTED';self.save()", "                requested=self.p.setdefault('requested_originals',[])\n                if gid not in requested:requested.append(gid)\n                plan['completed'][target]=gid;plan['status']='STARTED';self.save()")
s=s.replace("'structure_location','gap_rounds'):","'structure_location','gap_rounds','requested_originals'):")
needle="            current=inventory.originals_for(self.s,self.p,self.p.get('completion_basis_refs',[]) if sufficient else [])"
assert needle in s
s=s.replace(needle,"            from .decision_projection import requested_refs\n            delivered_refs=requested_refs(self.p) if self.modern and sufficient else []\n            current=inventory.originals_for(self.s,self.p,list(dict.fromkeys((self.p.get('completion_basis_refs',[]) if sufficient else [])+delivered_refs)))\n            if delivered_refs:result['original_delivery_context']={'basis_refs':delivered_refs,'automatic_adoption':False}")
p.write_text(s)
p=P/'completion_execution.py';s=p.read_text();s=s.replace('일반 규칙은 조건부로 설명하고 특정 사건 적용은 실제 사용자 사실에만 의존한다.', '일반 규칙은 GENERAL_RULE과 빈 fact_refs로 작성한다. 특정 사건 적용은 CASE_APPLICATION과 실제 제공된 사용자 사실만 쓴다. 질문 문장 자체를 사실 충족의 증거로 쓰지 않는다.')
needle="def assessment_projection(schema):";start=s.index(needle);end=s.index('\nCLOSED_STATUSES',start)
s=s[:start]+'''FLAT_CONDITION_GUIDANCE = """출력 전용 condition_tree는 null 또는 평평한 노드 배열이다. 서버가 기존 중첩 트리로 복원한다.
조건 하나는 [{"mode":"LEAF","text":"조건","evidence_refs":["S1"]}]이다.
여러 조건은 LEAF들을 먼저 쓰고 마지막에 {"mode":"ALL" 또는 "ANY" 또는 "UNKNOWN","children":[0,1]}로 앞선 노드의 0부터 시작한 위치를 연결한다.
마지막 노드가 전체 루트다. 중첩 관계도 앞선 노드 위치로 연결한다. 모든 노드를 루트에 연결하고, 순환·미래 위치·중복 children을 쓰지 않는다.
필요 없는 한 자식 묶음을 겹쳐 쓰지 않는다. 법률 내용과 조건 관계는 직접 판단하며 서버는 구조만 복원한다.
GENERAL_RULE의 fact_refs는 시스템이 빈 배열로 조립한다. JSON은 들여쓰기·빈 줄 없이 간결하게 출력하고 문자열 밖 공백을 반복하지 않는다."""


def restore_condition(nodes):
    if nodes is None:return None
    trees=[];depths=[];reachable=[]
    for index,node in enumerate(nodes):
        if node['mode']=='LEAF':
            trees.append(deepcopy(node));depths.append(0);reachable.append({index});continue
        children=node['children']
        if any(type(i) is not int or not 0<=i<index for i in children) or len(children)!=len(set(children)):
            raise ProposalError('condition children must be distinct earlier node positions')
        depth=1+max(depths[i] for i in children)
        if depth>3:raise ProposalError('condition depth exceeds canonical contract')
        trees.append({'mode':node['mode'],'children':[deepcopy(trees[i]) for i in children]})
        depths.append(depth);reachable.append({index}.union(*(reachable[i] for i in children)))
    if not nodes or reachable[-1]!=set(range(len(nodes))):raise ProposalError('all condition nodes must belong to the final root')
    return trees[-1]


def assessment_projection(schema):
    """Same semantic tree and model coverage; host owns control/structure fields."""
    wire=deepcopy(schema)
    wire['properties'].pop('disposition');wire['required'].remove('disposition')
    row=wire['properties']['issue_assessments']['items']
    row['properties'].pop('reason');row['required'].remove('reason')
    wire['properties']['gaps']['items']['properties']['reason']['maxLength']=512
    def leaf(node):
        if isinstance(node,dict):
            if node.get('properties',{}).get('mode',{}).get('const')=='LEAF':return deepcopy(node)
            for v in node.values():
                found=leaf(v)
                if found:return found
        elif isinstance(node,list):
            for v in node:
                found=leaf(v)
                if found:return found
    def visit(node):
        if isinstance(node,list):
            for v in node:visit(v)
        elif isinstance(node,dict):
            for v in list(node.values()):visit(v)
            props=node.get('properties',{})
            if 'condition_tree' not in props or 'fact_refs' not in props:return
            atomic=leaf(props['condition_tree'])
            if atomic is None:raise ContractError('condition wire missing canonical leaf contract')
            group=cc.obj({'mode':{'enum':['ALL','ANY','UNKNOWN']},'children':{'type':'array','minItems':1,'maxItems':8,'uniqueItems':True,'items':{'type':'integer','minimum':0,'maximum':584}}})
            props['condition_tree']={'anyOf':[{'type':'null'},{'type':'array','minItems':1,'maxItems':585,'items':{'type':'object','anyOf':[atomic,group]}}]}
            general=deepcopy(node);general['properties']['kind']={'const':'GENERAL_RULE'};general['properties']['fact_refs']['maxItems']=0
            application=deepcopy(node);application['properties']['kind']={'const':'CASE_APPLICATION'}
            node['anyOf']=[general,application]
    visit(wire)
    def expand(raw):
        output.validate_shape(raw,wire)
        value=deepcopy(raw)
        for claim in value['claims']:
            if claim.get('rule') is not None:claim['rule']['condition_tree']=restore_condition(claim['rule']['condition_tree'])
        for row in value['issue_assessments']:
            claims=sum(row['issue_id'] in c['issue_refs'] for c in value['claims'])
            gaps=sum(g['issue_id']==row['issue_id'] for g in value['gaps'])
            row['reason']=f"판단 상태 {row['status']}; 근거 주장 {claims}개, 미확인 {gaps}개."
        value['disposition']=('NEEDS_INVESTIGATION' if any(g['material'] and g['kind']!='MISSING_FACT' for g in value['gaps']) else
            'ANSWER' if all(r['status']=='COVERED' for r in value['issue_assessments']) else 'LIMITED_ANSWER')
        output.validate_shape(value,schema)
        return value
    return wire,expand

''' +s[end:]
s=s.replace("+('\\n'+narrative.ASSESS_GUIDANCE if rich else ''), {**context,", "+('\\n'+narrative.ASSESS_GUIDANCE if rich else '')+('\\n'+FLAT_CONDITION_GUIDANCE if modern else ''), {**context,")
p.write_text(s)
for p in P.glob('*.py'):compile(p.read_text(),str(p),'exec')
print('Retained delivered originals, exact compact-choice receipt, flat condition restoration and general-rule host facts implemented')
