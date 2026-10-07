"""Bounded model-owned repair, actual reader execution and persistent rejection audit."""
import copy
import json
from pathlib import Path
import pytest
from jsonschema import validate, ValidationError
from test_law_grouped_navigation import prepared, reader, decide
from test_unit_fulltext_adaptive_read import tree, session
from semantic_runtime.legal_agent import law_navigation as ln
from semantic_runtime.legal_agent.errors import ProposalError, ContractError

ROOT = Path('/home/jin/8-AGENT')


def conflict(data):
    candidate = data['articles'][0]
    value = decide(data, 'READ_PARENT', candidate['read_parent_action'], candidate)
    value['branch_decisions'] = [{'branch_id':candidate['id'], 'status':'DEFER',
        'reason':'전체 원문을 읽고 확인 필요', 'issue_refs':['Q1'], 'basis_refs':[data['basis'][0]['id']]}]
    return value


def test_actual_previous_conflict_schema_requires_changed_decision():
    audit=json.loads((ROOT/'04_EXPERIMENTS/ADR/ADR-0662-law-navigation-clean-search-probe/artifacts/search-boundary-audit.json').read_text())
    data=json.loads((ROOT/'04_EXPERIMENTS/ADR/ADR-0662-law-navigation-clean-search-probe/artifacts/first-law-navigation-input.json').read_text())
    rejected=audit['first_model_decision'];gid=rejected['branch_decisions'][0]['branch_id']
    handle=rejected['targets'][0]
    actions={r['id']:{**r,'identity':{'branch_id':gid} if r['id']==handle else {}} for r in data['actions']}
    schema,instructions=ln.repair_contract(data,actions,{r['id'] for r in data['branches']},rejected,ProposalError(audit['navigation_error']))
    with pytest.raises(ValidationError): validate(rejected,schema)
    corrected=copy.deepcopy(rejected);corrected['branch_decisions']=corrected['branch_decisions'][1:]
    validate(corrected,schema)
    deferred=copy.deepcopy(rejected);deferred.update(next_action='PENDING',targets=[])
    validate(deferred,schema)
    assert instructions['max_attempts']==1 and instructions['conflicts'][0]['branch_id']==gid
    assert rejected==audit['first_model_decision']


def test_repair_then_execute_reads_only_corrected_decision(session):
    native,_=session;s=native.sources;record=prepared(s);calls=[];events=[]
    original=s.repo.event
    def log(kind,payload,**kwargs):events.append((kind,copy.deepcopy(payload)));return original(kind,payload,**kwargs)
    s.repo.event=log
    def invoke(system,data,schema,phase,timeout):
        calls.append(phase)
        if len(calls)==1:return conflict(data)
        if phase.endswith('-repair'):
            assert not s.law_navigation_state['selected']
            assert data['repair_contract']['conflicts']
        return reader(system,data,schema,phase,timeout)
    result=ln.select('승인 예외',record,invoke,session=s,remaining_seconds=30)
    assert result['status']=='complete'
    assert sum(p.endswith('-repair') for p in calls)==1
    assert len(result['rejected_decisions'])==1
    assert any(k=='LAW_DECISION_REPAIRED' for k,_ in events)
    assert any(k=='UNIT_READ_CHOICE' for k,_ in events)


def test_second_invalid_is_saved_and_resume_cannot_retry_again(session):
    native,_=session;s=native.sources;record=prepared(s);calls=[]
    def invoke(system,data,schema,phase,timeout):calls.append(phase);return conflict(data)
    with pytest.raises(ValidationError):ln.select('승인 예외',record,invoke,session=s,remaining_seconds=30)
    saved=copy.deepcopy(s.law_navigation_state)
    assert len(calls)==2 and len(saved['rejected_decisions'])==2
    assert saved['rejected_decisions'][1]['phase'].endswith('-repair')
    assert not saved['selected'] and saved['decision_retry']['attempt']==1
    with pytest.raises(ProposalError,match='already attempted'):
        ln.select('승인 예외',record,invoke,session=s,remaining_seconds=30,checkpoint=saved)
    assert len(calls)==2


def test_invoke_proposal_error_is_repaired_once(session):
    native,_=session;s=native.sources;record=prepared(s);calls=[]
    def invoke(system,data,schema,phase,timeout):
        calls.append(phase)
        if len(calls)==1:raise ProposalError('invalid model object')
        if phase.endswith('-repair'):assert data['rejected_decision'] is None
        return reader(system,data,schema,phase,timeout)
    result=ln.select('승인 예외',record,invoke,session=s,remaining_seconds=30)
    assert result['status']=='complete' and sum(p.endswith('-repair') for p in calls)==1


def test_transport_contract_error_does_not_retry(session):
    native,_=session;s=native.sources;record=prepared(s);calls=[]
    def invoke(*args):calls.append(args[3]);raise ContractError('provider binding mismatch')
    with pytest.raises(ContractError,match='provider binding'):
        ln.select('승인 예외',record,invoke,session=s,remaining_seconds=30)
    assert len(calls)==1 and not s.law_navigation_state['selected']


@pytest.mark.parametrize('rejected',[None,{'next_action':'READ_PARENT','targets':[{}],'branch_decisions':None}])
def test_missing_or_malformed_decision_still_has_generic_repair_schema(rejected):
    data={'laws':[],'basis':[],'branches':[],'presentation_id':'P1'}
    schema,instructions=ln.repair_contract(data,{},set(),rejected,ProposalError('malformed'))
    assert schema['type']=='object' and not instructions['conflicts']
