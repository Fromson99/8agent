"""Real local journals and deterministic proposals; no provider calls."""
from copy import deepcopy
import json
import sqlite3
from types import SimpleNamespace as NS

import pytest

from workflow.adapters.model import ModelAdapter
from workflow.contracts import WorkflowError, digest, encoded
from workflow.repository import Repository
from semantic_runtime.legal_agent.bounded_source_session import _Protocol
from semantic_runtime.legal_agent.context import RequestContext
from semantic_runtime.legal_agent.errors import (
    BudgetExhausted, ContractError, ProposalError, StaleProposal, TransportError,
)
from semantic_runtime.legal_agent.output_contract import strict_json, validate_shape
from semantic_runtime.legal_agent.repository import WorkRepository


SCHEMA={'type':'object','properties':{'value':{'type':'integer'}},
        'required':['value'],'additionalProperties':False}
DATA={'question':'모의 정수 관측','sources':[]}


def accepted(value):
    if value['value']<=0:raise ValueError('supplied observation must be positive')


class Interrupted(BaseException):pass


class Services:
    ProposalError=ProposalError
    def __init__(self, proposals, *, interrupt=False):
        self.proposals=list(proposals);self.interrupt=interrupt;self.calls=[]

    def recover_response(self, raw, schema):
        if raw['model']!='synthetic':raise ContractError('recovered model binding mismatch')
        value=strict_json(raw['content']);validate_shape(value,schema)
        return value

    def structured(self, work, context, stage, call_id, data, schema, system, validator):
        self.calls.append(deepcopy(data))
        value=self.proposals.pop(0)
        if isinstance(value,BaseException):raise value
        view=work.save_view('compose',{'workflow_call_id':call_id,**data},[])
        ident=work.reserve_attempt(view,{'model':'synthetic'},call_id,1,'compose')
        work.attempt_sent(ident)
        raw={'model':'synthetic','content':json.dumps(value)}
        work.finish_attempt(ident,'SUCCEEDED',raw,{'model':'synthetic','usage':{}})
        if self.interrupt:
            self.interrupt=False
            raise Interrupted()
        _Protocol(schema,validator).validate('Synthetic',value)
        return deepcopy(value)


class Harness:
    def __init__(self, tmp_path, services):
        self.path=tmp_path/'journal.sqlite'
        self.request={'workflow_id':'risk_team_compare_workflow','question':DATA['question']}
        self.binding={'generation_id':'synthetic','export_allowed':True}
        self.context=RequestContext.create({'id':'synthetic','question':DATA['question']},
            self.request,self.binding,600,'a'*32)
        self.profile={'max_model_attempts':2,'finalization_reserve':0,'max_tool_actions':1}
        self.services=services;self.open()

    def open(self):
        self.work=WorkRepository(self.path,self.context,self.profile)
        self.repo=Repository(self.work,self.request,self.binding)
        self.model=ModelAdapter(self.repo,self.services,self.context)

    def reopen(self):
        self.work.close();self.open()

    def decide(self, validator=accepted):
        return self.model.decide('SYNTHETIC',DATA,SCHEMA,'모의 관측만 확인한다.',validator)

    def calls(self):
        return [dict(row) for row in self.work.db.execute('SELECT * FROM workflow_call ORDER BY call_id')]

    def close(self):self.work.close()


@pytest.mark.parametrize('first',[{'value':0},{'value':'invalid shape'}])
def test_recovered_invalid_proposal_uses_only_the_remaining_correction(tmp_path,first):
    services=Services([first,{'value':2}],interrupt=True);h=Harness(tmp_path,services)
    try:
        with pytest.raises(Interrupted):h.decide()
        assert h.calls()[0]['status']=='PREPARED'
        h.reopen()
        assert h.decide()=={'value':2}
        calls=h.calls()
        assert [row['status'] for row in calls]==['FAILED','COMPLETE']
        assert json.loads(calls[0]['error_json'])['repairable'] is True
        assert len(services.calls)==2 and services.calls[1]['repair']['error']['repairable'] is True
        assert h.work.db.execute('SELECT COUNT(*) FROM model_attempt').fetchone()[0]==2
        assert h.work.budget()['model_reserved']==2
        h.reopen();assert h.decide()=={'value':2} and len(services.calls)==2
    finally:h.close()


def test_recovered_valid_proposal_needs_no_second_call(tmp_path):
    services=Services([{'value':3}],interrupt=True);h=Harness(tmp_path,services)
    try:
        with pytest.raises(Interrupted):h.decide()
        h.reopen();assert h.decide()=={'value':3}
        assert len(services.calls)==1 and h.work.budget()['model_reserved']==1
        h.reopen();assert h.decide()=={'value':3} and len(services.calls)==1
    finally:h.close()


def test_recovered_invalid_and_failed_correction_remain_exhausted_after_restart(tmp_path):
    services=Services([{'value':0},{'value':-1}],interrupt=True);h=Harness(tmp_path,services)
    try:
        with pytest.raises(Interrupted):h.decide()
        h.reopen()
        for _ in range(2):
            with pytest.raises(WorkflowError) as caught:h.decide()
            assert caught.value.code=='WORKFLOW_REPAIR_EXHAUSTED'
            h.reopen()
        assert len(services.calls)==2 and h.work.budget()['model_reserved']==2
        assert all(row['status']=='FAILED' for row in h.calls())
    finally:h.close()


def test_new_call_semantic_failure_and_recovered_failure_use_same_owner(tmp_path):
    services=Services([{'value':0},{'value':1}]);h=Harness(tmp_path,services)
    try:
        assert h.decide()=={'value':1}
        assert len(services.calls)==2
        assert [row['status'] for row in h.calls()]==['FAILED','COMPLETE']
        assert services.calls[1]['repair']['error']['repairable'] is True
    finally:h.close()


@pytest.mark.parametrize('error',[
    ContractError('source/hash/ACL mismatch'),StaleProposal('stale response'),
    BudgetExhausted('budget exhausted'),sqlite3.OperationalError('storage failure'),
    TransportError('unknown delivery',unknown=True),
])
def test_nonproposal_failures_never_get_semantic_repair(tmp_path,error):
    services=Services([error,{'value':1}]);h=Harness(tmp_path,services)
    try:
        with pytest.raises(type(error)):h.decide()
        assert len(services.calls)==1 and len(h.calls())==1
        h.reopen()
        with pytest.raises(WorkflowError) as caught:h.decide()
        assert caught.value.code=='WORKFLOW_MODEL_STOPPED' and len(services.calls)==1
    finally:h.close()


def test_workflow_state_error_wrapped_by_gateway_is_not_a_repairable_proposal(tmp_path):
    services=Services([{'value':1},{'value':2}]);h=Harness(tmp_path,services)
    def state_error(value):raise WorkflowError('WORKFLOW_STATE_INTEGRITY','stored hash changed',409)
    try:
        with pytest.raises((WorkflowError,ProposalError)):h.decide(state_error)
        assert len(services.calls)==1
        row=h.calls()[0]
        assert row['status']=='FAILED' and json.loads(row['error_json']).get('repairable') is not True
        assert any(cause['code']=='WORKFLOW_STATE_INTEGRITY' for cause in json.loads(row['error_json'])['causes'])
        h.reopen()
        with pytest.raises(WorkflowError):h.decide(state_error)
        assert len(services.calls)==1
    finally:h.close()


def test_recovered_model_binding_error_stops_without_repair(tmp_path):
    services=Services([{'value':1},{'value':2}],interrupt=True);h=Harness(tmp_path,services)
    try:
        with pytest.raises(Interrupted):h.decide()
        row=h.work.db.execute('SELECT attempt_id,response_json FROM model_attempt').fetchone()
        raw=json.loads(row['response_json']);raw['model']='foreign'
        h.work.db.execute('UPDATE model_attempt SET response_json=?,response_hash=? WHERE attempt_id=?',
            (json.dumps(raw),digest(raw),row['attempt_id']))
        h.reopen()
        with pytest.raises(ContractError):h.decide()
        assert len(services.calls)==1 and h.calls()[0]['status']=='FAILED'
    finally:h.close()


@pytest.mark.parametrize('tamper',['response','hash'])
def test_recovered_response_hash_mismatch_is_state_failure_without_new_call(tmp_path,tamper):
    services=Services([{'value':1},{'value':2}],interrupt=True);h=Harness(tmp_path,services)
    try:
        with pytest.raises(Interrupted):h.decide()
        row=h.work.db.execute('SELECT attempt_id,response_json,response_hash FROM model_attempt').fetchone()
        assert digest(json.loads(row['response_json']))==row['response_hash']
        if tamper=='response':
            raw=json.loads(row['response_json']);raw['content']=json.dumps({'value':9})
            h.work.db.execute('UPDATE model_attempt SET response_json=? WHERE attempt_id=?',
                (json.dumps(raw),row['attempt_id']))
        else:
            h.work.db.execute('UPDATE model_attempt SET response_hash=? WHERE attempt_id=?',
                ('0'*64,row['attempt_id']))
        h.reopen()
        with pytest.raises(WorkflowError) as caught:h.decide()
        assert caught.value.code=='WORKFLOW_MODEL_RESPONSE_INTEGRITY' and caught.value.http_status==409
        assert len(services.calls)==1 and h.calls()[0]['status']=='FAILED'
        h.reopen()
        with pytest.raises(WorkflowError):h.decide()
        assert len(services.calls)==1
    finally:h.close()


def test_completed_invalid_result_is_state_failure_not_new_model_work(tmp_path):
    services=Services([{'value':1},{'value':2}]);h=Harness(tmp_path,services)
    try:
        assert h.decide()=={'value':1}
        invalid={'value':0}
        h.work.db.execute('UPDATE workflow_call SET result_json=?,result_hash=?',
            (encoded(invalid),digest(invalid)))
        h.reopen()
        with pytest.raises(WorkflowError) as caught:h.decide()
        assert caught.value.code=='WORKFLOW_STORED_RESULT_INVALID'
        assert len(services.calls)==1 and h.calls()[0]['status']=='COMPLETE'
    finally:h.close()
