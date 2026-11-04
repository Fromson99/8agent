"""Source-bound semantic dependency proposals; pure data-layer compilation.

No database access, model invocation, approval, source acquisition or eval.
A research proposal remains a proposal. Runtime originals must independently
match the source snapshot before any semantic content is exposed.
"""
from copy import deepcopy
import hashlib
import json
from jsonschema import Draft202012Validator
from ..contracts import digest
from .errors import ContractError

VERSION = 'ontology-semantic-proposal-v1'
KIND = ['MEASURE','CALCULATION','CONDITION','SCOPE','DEFINITION','EFFECT','EXCEPTION']
TYPE = ['NUMBER','BOOLEAN','DATE','TEXT','SET']
MODALITY = ['NONE','OBLIGATION','PERMISSION','PROHIBITION','PRESUMPTION','DEEMING','EXCLUSION','OTHER']

def obj(properties):
    return {'type':'object','additionalProperties':False,'required':list(properties),'properties':properties}
def arr(item, maximum=64, minimum=0):
    return {'type':'array','items':item,'maxItems':maximum,'minItems':minimum}
def string(maximum=1600):return {'type':'string','minLength':1,'maxLength':maximum}
REF = string(64)
BASIS = obj({'source':REF,'quote':string(2400)})
EDGE = obj({'node':REF,'role':{'enum':['INPUT','CONDITION','SCOPE','DEFINITION']},'reason':string(800),'basis':arr(BASIS,8,1)})
NODE = obj({'id':REF,'kind':{'enum':KIND},'concept':string(240),'value_type':{'enum':TYPE},'unit':string(80),
 'scope':string(1200),'time_basis':string(800),'aggregation':string(500),'expression':string(2400),
 'modality':{'enum':MODALITY},'dependencies':arr(EDGE,24),'exception_targets':{**arr(REF,16),'description':'Only an EXCEPTION node may use this field: IDs of EFFECT/CALCULATION/CONDITION nodes that THIS exception modifies. EFFECT must have []. Never list an exception on its normal effect.'},
 'basis':arr(BASIS,12,1),'judgment_refs':arr(REF,12,1)})
SCHEMA = obj({'schema_version':{'const':VERSION},'nodes':arr(NODE,64,1),'goals':arr(REF,32,1),
 'unresolved':arr(obj({'description':string(1600),'source_refs':arr(REF,16)}),32)})
PROMPT = '''원문 중심 온톨로지 작업 제안을 만든다. 입력의 judgments는 과거 에이전트 의견이며 오류가 있을 수 있다. 실제 originals를 우선해 측정 대상, 산정 입력/결과와 방식, 합산/제외 범위, 기준 시점, 조건, 법적 효과와 예외 대상을 구조화한다. 질문별 정답을 만들지 않는다. 금액의 의미가 다르면 단위가 같아도 별개 노드다. dependencies는 현재 노드가 사용하는 선행 입력/조건/범위/정의이며 모든 연결을 나열하지 않는다. exception_targets는 현재 EXCEPTION 노드가 변경하는 EFFECT/CALCULATION/CONDITION 노드 ID다. EXCEPTION 이외 역할은 반드시 빈 배열이다. 정상 효과가 자기에게 붙는 예외를 가리키는 역방향 목록이 아니다. 예: E(정상효과)의 exception_targets=[], X(예외)의 exception_targets=[E]. 역할이나 원문 의미를 바꾸어 형식을 맞추지 않는다. dependencies는 효과가 실제로 요구하는 선행 조건과 산정 입력을 가리킨다. 원문에 없는 연결·수치·식은 제안하지 않는다. basis.quote는 해당 original.text의 연속된 정확한 구절을 그대로 복사한다. 각 노드와 의존관계에 근거를 붙인다. judgment_refs는 발견 단서가 된 제공된 판단 ID이다. 과거 의견이 원문과 충돌하면 원문에 맞추되 불명확한 점은 unresolved에 남긴다. 사건 적용 사실·계산값·최종 결론을 생성하지 않는다. expression은 원문에 근거한 식/조건의 명시적 설명이고 실행 코드는 금지한다. 단위를 정할 수 없으면 unit=UNSPECIFIED, 시점이 없으면 time_basis=UNSPECIFIED, 합산이 무관하면 aggregation=NOT_APPLICABLE이다. 계산 노드는 필요한 측정 입력을 별도 노드로 만들고 dependencies로 연결한다. goals는 이 개념의 최종 효과 및 독립적인 검토 목적 노드다. 순환 의존을 만들지 않는다. 제공된 근거 밖 내용은 조회 필요로 남긴다. 이것은 운영 승인된 지식이 아닌 실험용 제안이다.'''

def _hash(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()

def validate(proposal, originals, judgments):
    if not isinstance(proposal,dict) or len(json.dumps(proposal,ensure_ascii=False))>150000:
        raise ContractError('semantic proposal size/type')
    errors=sorted(Draft202012Validator(SCHEMA).iter_errors(proposal),key=lambda e:str(e.path))
    if errors:raise ContractError('semantic schema: '+errors[0].message[:600])
    source={x['id']:x for x in originals};known={x['id'] for x in judgments}
    if len(source)!=len(originals) or len(known)!=len(judgments):raise ContractError('duplicate semantic input identity')
    for s in source.values():
        if _hash(s['text'])!=s['anchor']['content_sha256']:raise ContractError('semantic original hash mismatch')
    nodes={n['id']:n for n in proposal['nodes']}
    if len(nodes)!=len(proposal['nodes']):raise ContractError('duplicate semantic node')
    def basis(rows):
        for b in rows:
            s=source.get(b['source'])
            if not s or not b['quote'].strip() or b['quote'] not in s['text']:
                raise ContractError('semantic quote/source mismatch: '+b['source'])
    for n in nodes.values():
        basis(n['basis'])
        if not set(n['judgment_refs'])<=known:raise ContractError('unknown semantic judgment')
        refs=[x['node'] for x in n['dependencies']]
        if len(refs)!=len(set(refs)):raise ContractError('duplicate semantic dependency')
        for e in n['dependencies']:
            if e['node'] not in nodes:raise ContractError('unknown semantic dependency')
            basis(e['basis'])
        if not set(n['exception_targets'])<=nodes.keys():raise ContractError('unknown exception target')
        if n['exception_targets'] and n['kind']!='EXCEPTION':raise ContractError('nodes['+n['id']+'].exception_targets='+repr(n['exception_targets'])+' on kind='+n['kind']+': only EXCEPTION may list the EFFECT/CALCULATION/CONDITION it modifies; the normal effect must not list its exceptions. Preserve original legal meaning and correct the direction explicitly.')
        if any(nodes[t]['kind'] not in ('EFFECT','CALCULATION','CONDITION') for t in n['exception_targets']):
            raise ContractError('exception target must be an effect/calculation/condition')
        if n['id'] in n['exception_targets']:raise ContractError('self exception')
    if not set(proposal['goals'])<=nodes.keys():raise ContractError('unknown semantic goal')
    for u in proposal['unresolved']:
        if not set(u['source_refs'])<=source.keys():raise ContractError('unknown unresolved source')
    _order(nodes,list(nodes))
    return proposal

def _order(nodes,targets):
    done=set();visiting=set();ordered=[]
    def visit(key):
        if key in visiting:raise ContractError('cyclic semantic dependency')
        if key in done:return
        visiting.add(key)
        for e in nodes[key]['dependencies']:visit(e['node'])
        visiting.remove(key);done.add(key);ordered.append(key)
    for t in targets:visit(t)
    return ordered

def bind(proposal, originals, judgments):
    validate(proposal,originals,judgments)
    return {'schema_version':'ontology-semantic-binding-v1','authority':'EXPERIMENT_PROPOSAL_NOT_APPROVED',
      'proposal':deepcopy(proposal),'originals':deepcopy(originals),'judgments':deepcopy(judgments),
      'proposal_sha256':digest(proposal),'originals_sha256':digest(originals),'judgments_sha256':digest(judgments)}

def compile_plan(binding, fragments, *, goals=None):
    """Compile a purpose closure using only newly verified, authorized fragments.

    Missing sources withhold the affected node and downstream semantics; their
    identities/reasons remain visible. Registered exception targets are included
    when their target enters the closure. Never traverse arbitrary catalogue edges.
    """
    if binding.get('authority')!='EXPERIMENT_PROPOSAL_NOT_APPROVED':raise ContractError('semantic authority mismatch')
    p=binding['proposal'];originals=binding['originals'];judgments=binding['judgments']
    for key in ('proposal','originals','judgments'):
        if digest(binding[key])!=binding[key+'_sha256']:raise ContractError('semantic binding changed')
    validate(p,originals,judgments)
    nodes={n['id']:n for n in p['nodes']};targets=list(goals if goals is not None else p['goals'])
    if not targets or not set(targets)<=nodes.keys():raise ContractError('unknown/empty compile goal')
    order=_order(nodes,targets)
    while True:
        extra=[n['id'] for n in p['nodes'] if set(n['exception_targets']).intersection(order) and n['id'] not in order]
        if not extra:break
        order=_order(nodes,order+extra)
    source_by_anchor={digest(s['anchor']):s for s in originals};available={}
    for f in fragments:
        source=source_by_anchor.get(digest(f['anchor']))
        if source is None:continue # Unrelated verified originals are not semantic inputs.
        if source['id'] in available:raise ContractError('duplicate semantic original')
        if f['text']!=source['text'] or _hash(f['text'])!=source['anchor']['content_sha256']:
            raise ContractError('semantic runtime source changed')
        refs=f.get('evidence_refs')
        if not isinstance(refs,list) or not refs or any(not isinstance(x,str) or not x for x in refs):
            raise ContractError('semantic runtime source refs missing')
        available[source['id']]=refs
    steps=[];blocked=set()
    for key in order:
        n=nodes[key];all_basis=n['basis']+[b for e in n['dependencies'] for b in e['basis']]
        missing=sorted({b['source'] for b in all_basis}-available.keys())
        dependencies=[e['node'] for e in n['dependencies']]
        blocked_inputs=[x for x in dependencies if x in blocked]
        if missing or blocked_inputs:
            blocked.add(key);steps.append({'id':key,'status':'UNKNOWN','missing_originals':missing,'blocked_inputs':blocked_inputs});continue
        node=deepcopy(n)
        for b in node['basis']+[b for e in node['dependencies'] for b in e['basis']]:
            b['source_refs']=list(available[b['source']])
        node.update(status='REVIEW_REQUIRED',source_refs=list(dict.fromkeys(r for b in all_basis for r in available[b['source']])) )
        steps.append(node)
    unresolved=[deepcopy(u) for u in p['unresolved'] if set(u['source_refs'])<=available.keys()]
    return {'contract':'ontology-semantic-plan-v1','authority':binding['authority'],
      'proposal_sha256':binding['proposal_sha256'],'goals':targets,'ordered_steps':steps,
      'unresolved':unresolved,'withheld_unresolved_count':len(p['unresolved'])-len(unresolved),
      'status':'PARTIAL' if blocked else 'SOURCES_BOUND_REVIEW_REQUIRED',
      'numeric_execution':False,'automatic_legal_adoption':False}
