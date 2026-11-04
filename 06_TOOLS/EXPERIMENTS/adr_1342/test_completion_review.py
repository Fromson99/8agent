from copy import deepcopy
from pathlib import Path
import gzip, json, importlib.util
import pytest
from semantic_runtime.legal_agent import connection_scope as cs, read_judgment_final as final
from semantic_runtime.legal_agent import investigation_supervisor as su, answer_progress as ap, output_contract as oc
from semantic_runtime.legal_agent.errors import ProposalError
from test_final_connection_selection import setup

ROOT=Path(__file__).resolve().parents[3]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
scope_fixture=module('exact_scope_fixture1342','05_TESTS/CONTRACTS/test_scope_review.py').fixture
finish_fixture=module('finish_fixture1342','06_TOOLS/EXPERIMENTS/adr_1312/test_finish.py').fixture

def choose_scope(monkeypatch,inv,data,uid,status='COMPLETE'):
    monkeypatch.setattr(cs,'preview',lambda *a,**kw:dict(status=status,groups=[],connection_count=0,absence_proven=False))
    scope=next(s for s,_ in cs.candidates(inv,data) if s['structural_selection']['unit_id']==uid)
    cs.accept(inv,scope,data,'선택한 원문의 연결 확인')
    cs.offer_choices(inv,data,{})
    return scope

@pytest.mark.parametrize('status',['COMPLETE','PARTIAL','FAILED'])
def test_unrelated_inspection_cannot_cover_answer_basis(monkeypatch,status):
    inv,data=setup(monkeypatch);choose_scope(monkeypatch,inv,data,'10',status)
    before=deepcopy(data);result=cs.finish_review(data,{'basis_refs':[data['sources'][0]['id']]})
    assert not data['connection_review']['required_before_finish']
    assert result['supervision_required'] and len(result['uninspected_basis'])==1
    assert result['uninspected_basis'][0]['source_id']=='article92'
    assert not result['all_connections_required'] and data==before

@pytest.mark.parametrize('uid,pending',[('4',False),('6',True),('7',True),('10',True)])
def test_exact_selected_spans_and_ancestor_context(monkeypatch,uid,pending):
    inv,data=setup(monkeypatch);choose_scope(monkeypatch,inv,data,uid)
    value={'answer_progress':{'goals':[{'basis_refs':[data['sources'][0]['id']]}]}}
    assert cs.finish_review(data,value)['supervision_required'] is pending
    inv.p=json.loads(json.dumps(inv.p));cs.offer_choices(inv,data,{})
    assert cs.finish_review(data,value)['supervision_required'] is pending

def test_unrelated_unused_source_does_not_require_exhaustive_traversal(monkeypatch):
    inv,data=setup(monkeypatch);choose_scope(monkeypatch,inv,data,'10')
    result=cs.finish_review(data,{'basis_refs':[data['sources'][1]['id']]})
    assert not result['supervision_required'] and not result['uninspected_basis']

@pytest.mark.parametrize('available',[False,True])
def test_uninspected_basis_runs_bounded_supervisor_instead_of_fast_finish(available):
    inv,data,value,decision,_=finish_fixture()
    data['connection_review']={'required_before_finish':False,'source_inspections':[
        {'source_ref':'E1','inspected_scope_ids':[],'offered_scope_ids':['scope'], 'read_actions':['follow'] if available else []}]}
    st=su.state_for(inv,data);st['calls']=1;su.save(inv,st);calls=[]
    def invoke(prompt,body,schema,*args):
        calls.append(body)
        assert cs.FINISH_GUIDANCE in prompt
        assert body['finish_connection_review']['uninspected_basis'][0]['source_ref']=='E1'
        return {'directive':'STOP_UNRESOLVED','reason':'현재 경로에서 확인 미완료','remaining_scope':'질문 대상 원문의 연결'}
    inv.invoke=invoke
    with pytest.raises(ap.ProgressHandoff):su.gate(inv,data,{},data,value,decision,{'type':'object'},lambda v:decision,'key')
    assert len(calls)==1 and st['calls']==2
    assert not any(k=='SUPERVISOR_FINISH_HANDOFF' for k,v in inv.s.repo.events)
    with pytest.raises(ap.ProgressHandoff):su.gate(inv,data,{},data,value,decision,{'type':'object'},lambda v:decision,'key')
    assert len(calls)==1

def test_reviewed_basis_keeps_existing_zero_call_finish():
    inv,data,value,decision,_=finish_fixture()
    data['connection_review']={'source_inspections':[{'source_ref':'E1','inspected_scope_ids':['scope']}]}
    assert su.gate(inv,data,{},data,value,decision,{'type':'object'},lambda v:decision,'key')==decision
    assert su.state_for(inv,data)['calls']==0

def test_recorded1341_wrong_finish_requires_scope_supervision_without_mutation():
    base=ROOT/'04_EXPERIMENTS/ADR/ADR-1341-page-cycle-charter-live/artifacts/public-live/charter-bounded/canonical'
    with gzip.open(base/'006.json.gz','rt') as f:data=json.load(f)['view']
    with gzip.open(base/'006-output.json.gz','rt') as f:value=json.load(f)
    before=deepcopy(data);result=cs.finish_review(data,value)
    assert not data['connection_review']['required_before_finish']
    assert result['supervision_required'] and result['uninspected_basis']
    refs={r['source_ref'] for r in result['uninspected_basis']}
    assert all(s['source_id']=='article:d7bc3cc9b3f778ea70b1ab2d' for s in data['sources'] if s['id'] in refs)
    assert data==before

def test_recorded1341_explanation_has_exact_repair_choices():
    base=ROOT/'04_EXPERIMENTS/ADR/ADR-1341-page-cycle-charter-live/artifacts/public-live/charter-bounded/canonical'
    with gzip.open(base/'008.json.gz','rt') as f:feedback=json.load(f)['view']['repair_feedback']
    value=feedback['rejected_assessment'];before=deepcopy(value)
    result=[r for r in final.repair_choices(value,feedback['validation']) if r['cause']=='CLAIM_WITHOUT_MATCHING_ADOPTION']
    assert len(result)==2 and all(r['claim_id']=='C3' and not r['adopted_evidence_refs'] for r in result)
    assert all(r['related_judgments'] and r['claim_evidence_refs'] for r in result)
    assert all('C3' not in j['claim_refs'] for r in result for j in r['related_judgments'])
    assert value==before

def explanation_value():
    ctx,opts,value=scope_fixture()
    value['claims'].append({'claim_id':'C3','issue_refs':['Q1'],'evidence_refs':['S2']})
    value['read_judgment_review']['scope_reviews'][0]['groups'][1]['claim_refs'].append('C3')
    return ctx,opts,value

def test_explanation_link_repair_requires_model_adoption_and_keeps_validator():
    ctx,opts,value=explanation_value();before=deepcopy(value)
    with pytest.raises(oc.OutputContractError) as error:final.validate_review(value,ctx,opts)
    rows=final.repair_choices(value,error.value)
    assert any(r['cause']=='CLAIM_WITHOUT_MATCHING_ADOPTION' and r['claim_id']=='C3' for r in rows)
    assert value==before
    # Explicit fixture model correction; the product must never insert it.
    value['read_judgment_review']['judgments'][0]['claim_refs'].append('C3')
    next(n for n in value['read_judgment_review']['needs'] if n['id']=='GNa')['claim_refs'].append('C3')
    final.validate_review(value,ctx,opts)
    value['read_judgment_review']['judgments'][0]['basis_refs']=[]
    with pytest.raises(ProposalError):final.validate_review(value,ctx,opts)

@pytest.mark.parametrize('kind',['prior_judgments','prior_conflicts'])
def test_incomplete_public_text_preserves_receipt_without_unvalidated_conclusion(kind):
    conclusion='별도 확인 없이 일반 규정이 항상 적용된다.'
    receipt={'status':'INCOMPLETE','review':None,'prior_needs':[],kind:[{'id':'J1','text':conclusion,'reason':conclusion}]}
    value={'read_judgment_review':deepcopy(receipt),'limitation_items':[],'disposition':'ANSWER'}
    assert final.limitations(value)
    assert value['read_judgment_review']==receipt
    assert conclusion not in ' '.join(value['limitations']) and 'J1' in ' '.join(value['limitations'])
    assert value['disposition']=='LIMITED_ANSWER'

def test_validated_unresolved_review_still_reports_actual_limit():
    value={'read_judgment_review':{'status':'REVIEWED','review':{'needs':[], 'conflicts':[],
        'judgments':[{'id':'J1','disposition':'UNRESOLVED','reason':'적용 대상의 원문 확인이 남았다.'}]}},'limitation_items':[]}
    final.limitations(value)
    assert '적용 대상의 원문 확인이 남았다.' in value['limitations'][0]
