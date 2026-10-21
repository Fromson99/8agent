"""Deterministic real gateway/journal checks; no external client is created."""
from copy import deepcopy
from importlib import util
from pathlib import Path
import json
import os

import pytest

_path=Path(__file__).with_name('model_probe.py')
_spec=util.spec_from_file_location('adr0813_real_probe_helpers',_path)
h=util.module_from_spec(_spec);_spec.loader.exec_module(h)


class Sender:
    def __init__(self,modes):self.modes=list(modes);self.requests=[]
    def __call__(self,body,ticket):
        assert len(self.requests)<len(self.modes), 'unexpected extra physical call'
        mode=self.modes[len(self.requests)];self.requests.append(deepcopy(body))
        view=json.loads(body['messages'][1]['content'])['view']
        schema=body['response_format']['json_schema']['schema']
        row_schema=schema['properties']['rows']['items']
        citations=[{'citation_id':s['citation_options'][0]['citation_id']} for s in view['sources']]
        dimensions={name:{'citations':deepcopy(citations),'reason':'양측 모의 원문에서 확인한 조건',
            'status':'DIFFERENT' if name=='value' else 'MATCH'} for name in h.modules().contracts.DIMENSIONS}
        row={'item':'모의 수치 기준','citations':citations,'dimensions':dimensions,
             'difference':'내규와 외규의 최솟값이 다르다.','reason':'동일한 모의 대상에 서로 다른 최솟값을 적용한다.',
             'unresolved':[],'verdict':'CONFORMS' if mode=='invalid' else 'CONFLICT'}
        row={key:row[key] for key in row_schema['properties'] if key in row}
        value={'rows':[row],'answer':'모의 비교 결과','unresolved':[]}
        value={key:value[key] for key in schema['properties']}
        raw={'id':'stub-'+str(len(self.requests)),'model':body['model'],'provider':'Parasail',
             'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(value,ensure_ascii=False)}}],
             'usage':{'prompt_tokens':100,'completion_tokens':200,'total_tokens':300,
                      'completion_tokens_details':{'reasoning_tokens':0}}}
        if mode=='malformed':raw['choices'][0]['message']['content']='incomplete {'
        if mode=='length':raw['choices'][0]['finish_reason']='length'
        return {'status_code':200,'body_json':raw,'body_text':None,'body_sha256':h.digest(raw),'acceptance':'ACCEPTED'}


def fixture(tmp_path,modes):
    case=h.read(h.DESIGN/'model-cases.json')[0]
    code=Path(os.environ['WORKFLOW_TEST_CODE_ROOT'])
    profile=h.read(code/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
    policy=h.read(h.ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')
    sender=Sender(modes);transport=h.Transport(h.model_binding(policy),sender)
    stack=h.Stack(tmp_path,case,profile,transport,code_binding={'kind':'deterministic-unit-fixture','root':str(code)})
    return stack,sender


def assert_replay(stack,sender,result):
    calls=len(sender.requests);budget=stack.work.budget();deadline=stack.work.run()['deadline_at']
    stack.reopen()
    assert stack.run()==result and len(sender.requests)==calls
    assert stack.work.budget()==budget and stack.work.run()['deadline_at']==deadline


def test_first_valid_gateway_result_is_durable_and_duplicate_makes_no_send(tmp_path):
    stack,sender=fixture(tmp_path,['valid'])
    try:
        result=stack.run();report=stack.report()
        assert result['rows'][0]['verdict']=='CONFLICT'
        assert report['initial_valid'] is True and report['final_model_valid'] is True
        assert report['physical_calls']==report['budget']['model_reserved']==1
        assert report['attempts'][0]['provider_status']=='SUCCEEDED'
        assert_replay(stack,sender,result)
    finally:stack.close()


def test_one_semantic_correction_uses_same_originals_and_exact_failure(tmp_path):
    stack,sender=fixture(tmp_path,['invalid','valid'])
    try:
        result=stack.run();report=stack.report();a,b=report['attempts']
        assert result['rows'][0]['verdict']=='CONFLICT'
        assert report['initial_valid'] is False and report['final_model_valid'] is True
        assert report['physical_calls']==report['budget']['model_reserved']==2
        assert a['provider_status']==b['provider_status']=='SUCCEEDED'
        assert a['workflow_call_status']=='FAILED' and b['workflow_call_status']=='COMPLETE'
        assert a['source_binding']==b['source_binding'] and a['catalogue_hash']==b['catalogue_hash']
        assert 'conceal' in b['repair']['error']['message']
        assert a['validation_errors'] and not b['validation_errors']
        assert_replay(stack,sender,result)
    finally:stack.close()


def test_exhausted_correction_is_deferred_and_restart_cannot_reset_allowance(tmp_path):
    stack,sender=fixture(tmp_path,['invalid','invalid'])
    try:
        result=stack.run();report=stack.report()
        assert result['rows'][0]['verdict']=='DEFERRED'
        assert report['initial_valid'] is False and report['final_model_valid'] is False
        assert report['physical_calls']==report['budget']['model_reserved']==2
        assert all(a['provider_status']=='SUCCEEDED' and a['workflow_call_status']=='FAILED' for a in report['attempts'])
        assert_replay(stack,sender,result)
    finally:stack.close()


@pytest.mark.parametrize('mode',['malformed','length'])
def test_order_diagnostic_cannot_consume_the_gateway_validation_or_correction(mode,tmp_path):
    stack,sender=fixture(tmp_path,[mode,'valid'])
    try:
        result=stack.run();report=stack.report()
        assert result['rows'][0]['verdict']=='CONFLICT'
        assert report['physical_calls']==report['budget']['model_reserved']==2
        assert stack.transport.calls[0]['order_diagnostic_error']
        assert report['attempts'][0]['workflow_call_status']=='FAILED'
        assert report['attempts'][1]['workflow_call_status']=='COMPLETE'
        assert_replay(stack,sender,result)
    finally:stack.close()


class Crash(BaseException):pass


def test_completed_raw_response_recovers_without_a_new_physical_call(tmp_path):
    stack,sender=fixture(tmp_path,['valid'])
    try:
        finish=stack.repo.finish
        def crash(call_id,result):raise Crash('after validated gateway response, before workflow return')
        stack.repo.finish=crash
        with pytest.raises(Crash):stack.run()
        assert len(sender.requests)==1
        assert stack.work.db.execute('SELECT status FROM model_attempt').fetchone()[0]=='SUCCEEDED'
        assert stack.work.db.execute('SELECT status FROM workflow_call').fetchone()[0]=='PREPARED'
        stack.repo.finish=finish;stack.reopen()
        result=stack.run()
        assert result['rows'][0]['verdict']=='CONFLICT' and len(sender.requests)==1
        assert_replay(stack,sender,result)
    finally:stack.close()


def test_interrupted_invalid_response_uses_existing_remaining_correction_after_reopen(tmp_path):
    stack,sender=fixture(tmp_path,['invalid','valid'])
    try:
        def crash(call_id,error):raise Crash('after invalid raw response, before failure receipt')
        stack.repo.failure=crash
        with pytest.raises(Crash):stack.run()
        assert len(sender.requests)==1
        assert stack.work.db.execute('SELECT status FROM model_attempt').fetchone()[0]=='SUCCEEDED'
        assert stack.work.db.execute('SELECT status FROM workflow_call').fetchone()[0]=='PREPARED'
        stack.reopen();result=stack.run();report=stack.report()
        assert result['rows'][0]['verdict']=='CONFLICT' and len(sender.requests)==2
        assert report['attempts'][0]['workflow_call_status']=='FAILED'
        assert report['attempts'][1]['workflow_call_status']=='COMPLETE'
        assert report['budget']['model_reserved']==2
        assert_replay(stack,sender,result)
    finally:stack.close()
