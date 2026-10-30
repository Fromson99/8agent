"""Failure contracts on real parser/journal/stage boundaries; no model service."""
from contextlib import contextmanager
from copy import deepcopy
import json
import sqlite3
import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import output_contract as oc
from semantic_runtime.legal_agent.model_contract import structured_value
from semantic_runtime.legal_agent.errors import ContractError, ProposalError, StaleProposal
from test_ad_language import records, output


class Journal:
    def __init__(self, path):
        self.db=sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS event(seq INTEGER PRIMARY KEY,kind,payload_json,payload_hash)')
        self.binding={'principal':'test-owner','generation':'test-generation'}
    @contextmanager
    def transaction(self):
        with self.db:yield
    def event(self,kind,value):
        self.db.execute('INSERT INTO event(kind,payload_json,payload_hash) VALUES(?,?,?)',
            (kind,json.dumps(value,ensure_ascii=False),digest(value)))


@pytest.mark.parametrize('raw,path',[
    ('{"a":1,"a":2}','/a'),('{"a":{"x":1,"x":1}}','/a/x'),
    ('{"rows":[{"a/b":1,"a/b":2}]}','/rows/0/a~1b'),
    ('{"a":NaN}','/a'),('{"a":[Infinity]}','/a/0'),
    ('{"a":1e10000}','/a')])
def test_strict_json_rejects_before_overwrite(raw,path):
    with pytest.raises(oc.OutputContractError) as caught:oc.strict_json(raw)
    assert caught.value.category=='OUTPUT_JSON_INVALID'
    assert caught.value.issues[0]['path']==path


def test_json_preserves_legal_numbers_unicode_and_text():
    value={'원문':'제1조 ① 1.5% B1', 'number':1000000000000000000001,'items':[None,True,1.5]}
    assert oc.strict_json(json.dumps(value,ensure_ascii=False))==value


@pytest.mark.parametrize('raw',['{','{"a":1} tail','```json\n{}\n```'])
def test_incomplete_json_is_not_reconstructed(raw):
    with pytest.raises(oc.OutputContractError):oc.strict_json(raw)


@pytest.mark.parametrize('reason,can_repair',[('length',True),('content_filter',False),('refusal',False)])
def test_completed_http_is_separate_from_usable_output(reason,can_repair):
    body={'choices':[{'finish_reason':reason,'message':{'content':'{}'}}]}
    with pytest.raises(oc.OutputContractError) as caught:structured_value(body)
    assert oc.repairable(caught.value) is can_repair


def test_independent_conflicts_are_reported_without_merging():
    row={'branch_id':'B1','status':'ADOPT','reason':'근거 확인'}
    value={'reason':' ','branch_decisions':[row,{**row,'status':'EXCLUDE','reason':'  '}]}
    before=deepcopy(value);issues=oc.decision_issues(value)
    assert {i['code'] for i in issues}=={'CONFLICTING_BRANCH_DECISIONS','BLANK_DECISION_REASON'}
    assert {i['path'] for i in issues}=={'/branch_decisions/1','/branch_decisions/1/reason','/reason'}
    assert value==before


def test_runtime_and_implementation_errors_are_never_model_repairs():
    for exc in [ContractError('hash mismatch'),StaleProposal('late'),KeyError('bug'),TypeError('bug')]:
        assert oc.repairable(exc) is False


SCHEMA={'type':'object','required':['ok'],'properties':{'ok':{'const':True}},'additionalProperties':False}


@pytest.mark.parametrize('second_valid',[True,False])
def test_one_owner_uses_one_correction_and_same_context(tmp_path,second_valid):
    repo=Journal(tmp_path/'state.sqlite');calls=[];data={'sources':['original'],'question':'synthetic'}
    def invoke(payload,attempt):
        calls.append(payload)
        assert payload['sources']==data['sources']
        if attempt:
            assert payload['repair_contract']['validation']['issues']
            assert payload['rejected_decision']=={'ok':False}
        return {'ok':bool(attempt and second_valid)}
    def run():return oc.bounded_decision(repo,'test',data,SCHEMA,invoke,lambda v:oc.validate_shape(v,SCHEMA))
    if second_valid:
        assert run()=={'ok':True};assert run()=={'ok':True}
    else:
        with pytest.raises(ProposalError):run()
        with pytest.raises(ProposalError):run()
    assert len(calls)==2
    assert repo.db.execute('SELECT count(*) FROM event WHERE kind=?',(oc.DecisionJournal.EVENT,)).fetchone()[0]==4


def test_unknown_reserved_call_cannot_be_replayed_after_restart(tmp_path):
    path=tmp_path/'state.sqlite';repo=Journal(path)
    oc.DecisionJournal(repo,'test',{'request':'same'},SCHEMA).reserve(0);repo.db.close()
    again=Journal(path)
    with pytest.raises(ContractError,match='unknown'):
        oc.bounded_decision(again,'test',{'request':'same'},SCHEMA,
            lambda *_:pytest.fail('unknown call must not be resent'),lambda v:oc.validate_shape(v,SCHEMA))


def test_accepted_result_resumes_without_call_and_is_revalidated(tmp_path):
    path=tmp_path/'state.sqlite';repo=Journal(path);j=oc.DecisionJournal(repo,'test',{'request':'same'},SCHEMA)
    j.reserve(0);j.accept(0,{'ok':True});repo.db.close();again=Journal(path);checked=[]
    assert oc.bounded_decision(again,'test',{'request':'same'},SCHEMA,
        lambda *_:pytest.fail('accepted call is reusable'),lambda v:checked.append(v))=={'ok':True}
    assert checked==[{'ok':True}]


def test_journal_tamper_is_not_repaired(tmp_path):
    repo=Journal(tmp_path/'state.sqlite');j=oc.DecisionJournal(repo,'test',{},SCHEMA)
    j.reserve(0);j.accept(0,{'ok':True})
    with repo.transaction():repo.db.execute("UPDATE event SET payload_hash='wrong' WHERE seq=2")
    with pytest.raises(ContractError,match='hash'):j.state()


def test_no_repair_after_stream_started(tmp_path):
    repo=Journal(tmp_path/'state.sqlite');calls=[]
    with pytest.raises(ProposalError):oc.bounded_decision(repo,'compose',{},SCHEMA,
        lambda *_:calls.append(1) or {'ok':False},lambda v:oc.validate_shape(v,SCHEMA),can_repair=lambda:False)
    assert calls==[1]
    repo.db.close();repo=Journal(tmp_path/'state.sqlite')
    with pytest.raises(ProposalError):oc.bounded_decision(repo,'compose',{},SCHEMA,
        lambda *_:pytest.fail('resume must retain the stream failure stop'),
        lambda v:oc.validate_shape(v,SCHEMA),can_repair=lambda:True)


def test_ad_schema_repair_is_before_sql_and_in_total_budget(records):
    path,ask,_=records;calls=[]
    def model(ctx,*_):
        calls.append(ctx)
        if len(calls)==1:return {**output('list',kind='shortcut',query=''),'plan':{'action':'list'}}
        assert ctx['schema_repair']['max_corrections']==1
        assert sqlite3.connect(path).execute('SELECT count(*) FROM ad_change').fetchone()[0]==0
        return output('list',kind='shortcut',query='')
    result=ask('숏컷 목록',model,request='repair-once')
    assert result['answer_status']=='administration',result
    assert result['model_call_count']==2
    assert ask('숏컷 목록',model,request='repair-once')==result
    assert len(calls)==2


def test_ad_second_failure_preserves_failed_operation_without_write(records):
    path,ask,_=records;calls=[]
    def model(*_):calls.append(1);return {**output('list',kind='shortcut',query=''),'plan':{}}
    result=ask('숏컷 목록',model,request='twice-bad')
    assert result['answer_status']=='error'
    assert ask('숏컷 목록',model,request='twice-bad')==result
    assert len(calls)==2
    assert sqlite3.connect(path).execute('SELECT count(*) FROM ad_change').fetchone()[0]==0


def test_ad_model_binding_failure_never_repairs(records):
    _,ask,_=records;calls=[]
    def model(*_):
        calls.append(1);v=output('list',kind='shortcut',query='')
        v['receipt'].update(decode_error='wrong model',output_contract={'category':'STATE_OR_BINDING_INVALID','repairable':False})
        return v
    assert ask('숏컷 목록',model)['answer_status']=='error'
    assert len(calls)==1

