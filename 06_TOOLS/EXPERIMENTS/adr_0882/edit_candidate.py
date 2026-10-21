from pathlib import Path
R=Path(__file__).resolve().parents[3]; C=R/'02_BACKEND/lawrag/research/candidates/adr_0882/expressions/snapshot/02_BACKEND/semantic_runtime/legal_agent'
p=C/'completion_execution.py';s=p.read_text();a=s.index('FLAT_CONDITION_GUIDANCE =');b=s.index('\ndef assessment_projection',a)
s=s[:a]+'''CONDITION_GUIDANCE = """출력 전용 condition_tree는 null 또는 {"leaves":[{"text":"조건 A","evidence_refs":["S1"]},{"text":"조건 B","evidence_refs":["S2"]}],"expression":"ANY(1,2)"}다.
leaves에 조건을 한 번씩 쓰고 expression은 1부터 시작한 조건 위치로 관계만 표시한다. 하나는 1, 모두는 ALL(1,2), 하나 이상은 ANY(1,2), 관계 미확인은 UNKNOWN(1,2), 중첩은 ALL(1,ANY(2,3))이다.
모든 조건을 관계식에 포함한다. 최대 중첩 3단계, 그룹마다 1~8개 자식이다. 서버는 조건·원문 ID·ALL/ANY/UNKNOWN 관계를 그대로 복원한다.
GENERAL_RULE의 fact_refs 및 gap 종류에 따라 확정되는 고정값은 시스템이 조립한다. 법률 내용과 실제 부족 종류는 직접 판단한다.
JSON은 들여쓰기·빈 줄 없이 간결하게 출력한다."""


def restore_condition(value):
    """Parse an explicit bounded relation; never infer a missing connective."""
    if value is None:return None
    import re
    leaves=value['leaves'];expression=value['expression']
    if not 1<=len(leaves)<=585 or len(expression)>4096:
        raise ProposalError('condition leaves/expression exceeds bounded contract')
    tokens=[];cursor=0
    for match in re.finditer(r'ALL|ANY|UNKNOWN|[0-9]+|[(),]',expression):
        if expression[cursor:match.start()].strip():
            raise ProposalError(f'condition expression invalid token at character {cursor}')
        tokens.append(match.group());cursor=match.end()
    if expression[cursor:].strip():raise ProposalError(f'condition expression invalid token at character {cursor}')
    pos=0;used=set()
    def parse(depth):
        nonlocal pos
        if depth>3:raise ProposalError('condition expression exceeds canonical depth 3')
        if pos>=len(tokens):raise ProposalError('condition expression missing operand')
        token=tokens[pos];pos+=1
        if token.isdigit():
            index=int(token)
            if not 1<=index<=len(leaves):raise ProposalError(f'condition leaf {index} outside 1..{len(leaves)}')
            used.add(index)
            return {'mode':'LEAF',**deepcopy(leaves[index-1])}
        if token not in ('ALL','ANY','UNKNOWN') or pos>=len(tokens) or tokens[pos]!='(':
            raise ProposalError(f'condition expression expected leaf or operator at token {pos}')
        pos+=1;children=[parse(depth+1)]
        while pos<len(tokens) and tokens[pos]==',':
            pos+=1
            if len(children)>=8:raise ProposalError('condition group exceeds 8 children')
            children.append(parse(depth+1))
        if pos>=len(tokens) or tokens[pos]!=')':raise ProposalError('condition expression missing closing parenthesis')
        pos+=1
        return {'mode':token,'children':children}
    tree=parse(0)
    if pos!=len(tokens):raise ProposalError('condition expression has trailing tokens')
    if used!=set(range(1,len(leaves)+1)):raise ProposalError('condition expression must include every provided leaf')
    return tree

''' +s[b:]
a=s.index("            group=cc.obj(");b=s.index("            general=",a)
s=s[:a]+'''            atomic['properties'].pop('mode');atomic['required'].remove('mode')
            props['condition_tree']={'anyOf':[{'type':'null'},cc.obj({
                'leaves':{'type':'array','minItems':1,'maxItems':585,'items':atomic},
                'expression':{'type':'string','minLength':1,'maxLength':4096}})]}
'''+s[b:]
s=s.replace("            if 'condition_tree' not in props or 'fact_refs' not in props:return",'''            if {'kind','material_id','suggested_action','missing_target'}<=set(props):
                branches=[]
                for kind in props['kind']['enum']:
                    branch=deepcopy(node);bp=branch['properties'];bp['kind']={'const':kind}
                    if kind=='MISSING_FACT':
                        bp['material_id']={'const':None};bp['missing_target']={'const':''}
                        bp['suggested_action']={'const':'REQUEST_FACT'}
                    else:bp['suggested_action']['enum']=[a for a in bp['suggested_action']['enum'] if a!='REQUEST_FACT']
                    branches.append(branch)
                node['anyOf']=branches
            if 'condition_tree' not in props or 'fact_refs' not in props:return''')
a=s.index('    def expand(raw):');b=s.index('    return wire,expand',a)
block=s[a:b];block=block.replace('    def expand(raw):','    def decode(raw):')
block+='''    def expand(raw):
        try:return decode(raw)
        except (ProposalError,ValidationError) as exc:
            exc.proposal=deepcopy(raw)
            raise
'''
s=s[:a]+block+s[b:]
s=s.replace("            cached = decision_journal.reserve(attempt)\n            try:","            cached = decision_journal.reserve(attempt)\n            value = None\n            try:")
s=s.replace('FLAT_CONDITION_GUIDANCE if modern','CONDITION_GUIDANCE if modern')
s=s.replace("            except (ProposalError, ValidationError) as exc:\n                if not cached:decision_journal.reject(attempt,exc,value)","            except (ProposalError, ValidationError) as exc:\n                value=getattr(exc,'proposal',value)\n                if not cached:decision_journal.reject(attempt,exc,value)")
p.write_text(s)
p=C/'request_entry.py';s=p.read_text();a=s.index('        if scoped:\n            request_schema,');b=s.index("        work.event('WORKFLOW_TASK_CONTEXT'",a);s=s[:a]+s[b:];a=s.index('    prepared={}');s=s[:a]+'''    if scoped:
        request_schema,data['request_quote_options']=bind_task_quotes(request_schema,context['utterance'])
        task_prompt+=' 각 issue의 request_quote는 시스템이 질문 원문 전체로 고정한다. 목적과 쟁점은 요청 범위에서 별도로 판단한다.'
'''+s[a:];p.write_text(s)
print('four product files isolated; exact host contracts prepared')
