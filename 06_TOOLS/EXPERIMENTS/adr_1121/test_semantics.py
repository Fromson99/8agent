from copy import deepcopy
import pytest
from semantic_runtime.legal_agent import ontology_semantics as sem
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.contracts import digest

def fixture():
    text='합성: 같은 거래의 계약금액을 합산한다. 합산 금액이 기준 이상이면 승인한다. 면제 조건이면 승인을 제외한다.'
    originals=[{'id':'P1','anchor':{'document_id':'d','version':'v','unit_id':'1','content_sha256':sem._hash(text),'label':'합성규정'},'text':text}]
    judgments=[{'id':'J1','judgment':'합산 범위와 승인 기준을 확인했다'}]
    def node(i,kind,deps=(),targets=()):
        return {'id':i,'kind':kind,'concept':i,'value_type':'NUMBER' if kind in ('MEASURE','CALCULATION') else 'BOOLEAN','unit':'KRW' if kind in ('MEASURE','CALCULATION') else 'BOOLEAN','scope':'합성 거래','time_basis':'UNSPECIFIED','aggregation':'원문 기준','expression':'합성 원문 표현','modality':'EXCLUSION' if kind=='EXCEPTION' else 'NONE','dependencies':[{'node':x,'role':'INPUT','reason':'합성 선행 입력','basis':[{'source':'P1','quote':'계약금액을 합산한다'}]} for x in deps],'exception_targets':list(targets),'basis':[{'source':'P1','quote':'합성:'}],'judgment_refs':['J1']}
    p={'schema_version':sem.VERSION,'nodes':[node('C','EFFECT',['B']),node('B','CALCULATION',['A']),node('A','MEASURE'),node('X','EXCEPTION',targets=['C']),node('Z','MEASURE')],'goals':['C'],'unresolved':[]}
    return sem.bind(p,originals,judgments),[{'anchor':originals[0]['anchor'],'text':text,'evidence_refs':['S1']}]

def test_purpose_closure_order_and_exception():
    b,f=fixture();r=sem.compile_plan(b,f)
    assert [n['id'] for n in r['ordered_steps']]==['A','B','C','X']
    assert r['numeric_execution'] is False and r['automatic_legal_adoption'] is False
    assert r['authority']=='EXPERIMENT_PROPOSAL_NOT_APPROVED'
    assert r['ordered_steps'][-1]['exception_targets']==['C']
    assert all(n['source_refs']==['S1'] for n in r['ordered_steps'])

def test_missing_original_blocks_dependents_without_inventing_values():
    b,f=fixture();r=sem.compile_plan(b,[])
    assert r['status']=='PARTIAL'
    assert all(x['status']=='UNKNOWN' and 'expression' not in x for x in r['ordered_steps'])
    assert r['ordered_steps'][1]['blocked_inputs']==['A']

@pytest.mark.parametrize('change',['quote','source','judgment','cycle','unknown','duplicate','exception','goal','source_hash'])
def test_invalid_proposals_fail_closed(change):
    b,f=fixture();p=b['proposal'];n=p['nodes'][0]
    if change=='quote':n['basis'][0]['quote']='존재하지 않는 조건'
    if change=='source':n['basis'][0]['source']='P9'
    if change=='judgment':n['judgment_refs']=['J9']
    if change=='cycle':p['nodes'][2]['dependencies']=deepcopy(n['dependencies'])
    if change=='unknown':n['dependencies'][0]['node']='N9'
    if change=='duplicate':p['nodes'].append(deepcopy(n))
    if change=='exception':n['exception_targets']=['A']
    if change=='goal':p['goals']=['N9']
    if change=='source_hash':b['originals'][0]['text']+='변조'
    with pytest.raises(ContractError):sem.validate(p,b['originals'],b['judgments'])

@pytest.mark.parametrize('change',['proposal','originals','judgments'])
def test_frozen_binding_tamper(change):
    b,f=fixture();b[change+'_sha256']='0'*64
    with pytest.raises(ContractError):sem.compile_plan(b,f)

@pytest.mark.parametrize('change',['text','version','refs','duplicate'])
def test_current_source_integrity(change):
    b,f=fixture();f=deepcopy(f)
    if change=='text':f[0]['text']+='변조'
    if change=='version':
        f[0]['anchor']['version']='new'
        r=sem.compile_plan(b,f);assert r['status']=='PARTIAL';return
    if change=='refs':f[0]['evidence_refs']=[]
    if change=='duplicate':f.append(deepcopy(f[0]))
    with pytest.raises(ContractError):sem.compile_plan(b,f)

def test_distinct_measure_concepts_and_idempotence():
    b,f=fixture();b['proposal']['goals']=['A','Z'];b['proposal']['nodes'][2]['concept']='거래금액';b['proposal']['nodes'][4]['concept']='위험액';b['proposal_sha256']=digest(b['proposal'])
    before=deepcopy((b,f));r=sem.compile_plan(b,f)
    assert [n['concept'] for n in r['ordered_steps']]==['거래금액','위험액']
    assert sem.compile_plan(b,f)==r and (b,f)==before

def test_unknown_unresolved_text_not_exposed():
    b,f=fixture();b['proposal']['unresolved']=[{'description':'미확보 의미','source_refs':['P1']}];b['proposal_sha256']=digest(b['proposal'])
    r=sem.compile_plan(b,[]);assert r['unresolved']==[] and r['withheld_unresolved_count']==1
