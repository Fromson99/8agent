from copy import deepcopy
from types import SimpleNamespace
from pathlib import Path
import gzip,json,pytest
from jsonschema import Draft202012Validator
from semantic_runtime.legal_agent import investigation_supervisor as supervisor, output_contract as output, ontology_assessment
from semantic_runtime.legal_agent.errors import ContractError, InvestigationPending, TransportError

ROOT=Path(__file__).resolve().parents[3]
def saved(name='charter-explicit',number=3):
    base=next((ROOT/'04_EXPERIMENTS/ADR').glob('ADR-1383-*/artifacts'))/'usage-live'/(name+'-ontology-on')/'canonical'
    def read(p):
        with gzip.open(p,'rt') as stream:return json.load(stream)
    v=read(base/f'{number:03}.json.gz')['view']
    p=read(base/f'{number:03}-output.json.gz')
    return v,p

class Repo:
    def __init__(self):self.states={};self.events=[]
    def output_decision_state(self,key):return deepcopy(self.states.get(key))
    def output_decision_event(self,row):self.states[row['decision_key']]=deepcopy(row)
    def event(self,kind,row):self.events.append((kind,deepcopy(row)))

def host(decision):
    repo=Repo();calls=[]
    profile={'candidate_navigation':{'supervisor_mode':'enforce'}}
    def invoke(prompt,body,schema,phase):
        calls.append(deepcopy(body))
        assert phase=='memory-ontology-supervisor'
        if isinstance(decision,Exception):raise decision
        return deepcopy(decision)
    ex=SimpleNamespace(s=SimpleNamespace(work=repo,sources=SimpleNamespace(profile=profile)),invoke=invoke)
    return ex,repo,calls

def run(ex,v,p):
    return supervisor.review_ontology_assessment(ex,v['current_request'],v,p,v['evidence_options'],{'binding':'same-current-source'})

def test_recorded_explicit_empty_usage_reaches_reviewer_without_fabricated_adoption():
    v,p=saved();ex,repo,calls=host({'decision':'PASS'});before=deepcopy(p)
    receipt=run(ex,v,p)
    assert len(calls)==1 and calls[0]['ontology_usage']==[]
    assert calls[0]['current_request']==v['current_request']
    assert calls[0]['issue_assessments']==p['issue_assessments']
    assert calls[0]['catalogs'][0]['paths'][0]['id']=='calculation-basis'
    assert calls[0]['evidence_options']==v['evidence_options']
    assert p==before and receipt['decision']=={'decision':'PASS'}
    assert run(ex,v,p)['reused'] and len(calls)==1

def test_recorded_claim_path_mismatch_keeps_all_missing_originals_in_feedback():
    v,p=saved('charter-on',8);schema={'properties':{'ontology_usage':{}}}
    with pytest.raises(output.OutputContractError) as exc:
        ontology_assessment.usage_core(p,schema,v)
    problem=exc.value.issues[0]
    assert problem['code']=='ONTOLOGY_PATH_EVIDENCE' and problem['path']=='/ontology_usage/0'
    assert len(problem['expected_constraint']['required_evidence_refs'])==2
    assert len(problem['expected_constraint']['claim_evidence_refs'])==1

def test_review_reply_has_one_field_on_pass_and_bounded_issue_on_repair():
    s=supervisor.ontology_review_schema(['C1']);v=Draft202012Validator(s)
    assert v.is_valid({'decision':'PASS'})
    assert not v.is_valid({'decision':'PASS','claims':[]})
    assert not v.is_valid({'decision':'REPAIR','issues':[]})
    assert not v.is_valid({'decision':'REPAIR','issues':[{'claim_id':'foreign','code':'REASON_CONFLICT','reason':'wrong claim'}]})
    assert len(json.dumps(s))<1200

def test_repair_is_preserved_and_owned_by_existing_assessment_not_reviewer():
    v,p=saved();ex,repo,calls=host({'decision':'REPAIR','issues':[{'claim_id':'C1','code':'USE_NOT_RECORDED','reason':'경로를 사용했다고 설명하면서 사용 목록이 비어 있습니다.'}]})
    for _ in range(2):
        with pytest.raises(output.OutputContractError) as error:run(ex,v,p)
        assert error.value.issues[0]['code']=='ONTOLOGY_USE_NOT_RECORDED'
        assert error.value.issues[0]['related_paths']==['/ontology_usage','/issue_assessments']
    assert len(calls)==1 and p['ontology_usage']==[]

@pytest.mark.parametrize('kind',['off','no_catalog','no_claims'])
def test_no_review_call_when_disabled_or_no_reusable_input(kind):
    v,p=saved();ex,repo,calls=host({'decision':'PASS'})
    if kind=='off':ex.s.sources.profile['candidate_navigation']['supervisor_mode']='off'
    if kind=='no_catalog':v['ontology_bundles']=[]
    if kind=='no_claims':p['claims']=[]
    assert run(ex,v,p) is None and not calls and not repo.states

def test_schema_invalid_reviewer_stops_without_primary_rewrite_or_nested_retry():
    v,p=saved();ex,repo,calls=host({'decision':'PASS','fabricated_evidence':['none']})
    with pytest.raises(InvestigationPending):run(ex,v,p)
    with pytest.raises(output.OutputContractError):run(ex,v,p)
    assert len(calls)==1

def test_unknown_reviewer_reservation_cannot_replay_after_restart():
    v,p=saved();ex,repo,calls=host(TransportError('synthetic timeout',unknown=True))
    with pytest.raises(TransportError):run(ex,v,p)
    with pytest.raises(ContractError,match='unknown'):run(ex,v,p)
    assert len(calls)==1

def test_changed_original_reference_is_not_offered_to_review():
    v,p=saved();v['evidence_options']=[]
    ex,repo,calls=host({'decision':'PASS'})
    with pytest.raises(ContractError,match='original references'):run(ex,v,p)
    assert not calls

def test_current_case_binding_and_changed_proposal_never_reuse_wrong_pass():
    v,p=saved();ex,repo,calls=host({'decision':'PASS'});run(ex,v,p)
    p['issue_assessments'][0]['reason']='별도 판단'
    run(ex,v,p)
    assert len(calls)==2 and len(repo.states)==2


def test_gateway_correction_owner_is_explicit_for_review_stage():
    assert output.owner_for('memory-ontology-supervisor')=='ontology-assessment-review'


def test_review_input_preserves_actual_user_fact_sources():
    v,p=saved();facts=[{'id':'F1','text':'사용자가 제공한 사건 전제'}]
    body=supervisor.ontology_review_input(v['current_request'],v,p,v['evidence_options'],facts)
    assert body['user_fact_sources']==facts and body['user_fact_sources'] is not facts
