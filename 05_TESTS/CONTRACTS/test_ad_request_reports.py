"""Synthetic transport and SQL tests; no GENOS network or model inference."""
import asyncio
import copy
import csv
import json
import sqlite3
from types import SimpleNamespace
import pytest

from semantic_runtime import ad_gateway, ad_model, ad_mode, request_report, request_summary
from semantic_runtime.ad_language import SCHEMA
from semantic_runtime.ad_request_report import bound_request, journal
from semantic_runtime.genos import endpoint
from semantic_runtime.legal_agent.errors import TransportError, ProposalError
from semantic_runtime.legal_agent.model_contract import genos_wire_schema, structured_content, structured_request


@pytest.fixture
def serving(tmp_path, monkeypatch):
    import service
    runtime=tmp_path/'runtime'; shared=tmp_path/'reports'
    monkeypatch.setenv('TEAM_ID','financial_team')
    monkeypatch.setenv('GENOS_RUNTIME_DIR',str(runtime))
    monkeypatch.setenv('GENOS_SHARED_LOG_DIR',str(shared))
    monkeypatch.setenv('AD_WORKER_ENABLED','0')
    monkeypatch.delenv('GENOS_STATE_DIR',raising=False)
    monkeypatch.setattr(service,'_ad_control',lambda:ad_gateway)
    target=endpoint('https://synthetic.invalid/v1',token='synthetic-secret-key')
    monkeypatch.setenv('GENOS_LLM_KEY','synthetic-secret-key')
    monkeypatch.setattr(ad_model,'from_env',lambda _: (target,'synthetic'))
    calls=[]
    class Transport:
        def __init__(self,*args):pass
        def send_once(self,body,ticket):
            calls.append(copy.deepcopy(body))
            # The actual wire request must be durable before the HTTP send.
            saved=journal(runtime,ticket['attempt_id'].rsplit(':ad:',1)[0],bound_request({
                'ad_session_id':'chat','ad_channel':'genos'}))
            assert saved['calls'][-1]['input']['request']==body
            if 'force_http_error' in body['messages'][-1]['content']:
                raise TransportError('upstream HTTP error',response={'status_code':400,
                    'body_json':{'error':{'code':'unsupported_parameter','param':'response_format',
                        'message':'unsupported grammar; synthetic-secret-key'}},
                    'body_text':None,'response_bytes':123,'body_sha256':'mock-response'})
            if 'duplicate' in body['messages'][-1]['content']:
                value={'action':'features','args':{'names':['shortcut','shortcut'],'enabled':True}}
            else:value={'action':'list','args':{'kind':'shortcut','query':''}}
            return {'status_code':200,'body_json':{'model':'synthetic','choices':[
                {'finish_reason':'stop','message':{'content':json.dumps(value)}}]},
                'body_sha256':'mock','response_bytes':120}
    monkeypatch.setattr(ad_model,'GenosTransport',Transport)
    def ask(question,ident,**extra):
        result=asyncio.run(service.service({}, {'API_TYPE':'AD_PROBE','question':question,
            'ad_session_id':'chat','ad_channel':'genos','request_id':ident,**extra}))
        request_report._FINALIZER_QUEUE.join()
        return result
    return runtime,shared,calls,ask


def reports(shared):
    return [json.loads(p.read_text()) for p in shared.rglob('*.json')]


def test_handled_ad_calls_are_reported_under_bound_team_with_full_wire_and_error(serving):
    runtime,shared,calls,ask=serving
    assert ask('[AD모드 시작]','enter')['body']['ad_mode'] is True
    assert ask('숏컷 보여줘','list',team_id='risk_team')['body']['answer_status']=='administration'
    failed=ask('force_http_error','fail')
    assert failed['status']==200 and failed['body']['answer_status']=='error'
    assert '400' in failed['body']['text'] and 'unsupported_parameter' in failed['body']['text']
    saved={r['request_id']:r for r in reports(shared)}
    assert set(saved)=={'enter','list','fail'}
    assert all(r['component']=='ad_mode' and r['team_id']=='financial_team' for r in saved.values())
    assert saved['enter']['journal']['calls']==[]
    success=saved['list']['journal']['calls'][0]
    assert success['input']['request']==calls[0]
    assert success['receipt']['http_status']==200
    fail=saved['fail']['journal']['calls'][0]
    assert fail['input']['request']==calls[1]
    assert fail['model_output']['status_code']==400
    assert fail['model_output']['body_json']['error']['param']=='response_format'
    assert saved['fail']['journal']['operation']['status']=='FAILED'
    assert saved['fail']['journal']['changes']==[]
    paths=list(shared.rglob('*.json'))
    assert all(p.parent.parts[-2:]==('financial_team','ad_mode') for p in paths)
    for p in shared.rglob('*'):
        if p.suffix in ('.json','.txt','.log','.row'):
            assert 'synthetic-secret-key' not in p.read_text()
    with next(shared.rglob('질문답변.csv')).open(encoding='utf-8-sig') as f:
        rows={r['요청 ID']:r for r in csv.DictReader(f)}
    assert rows['fail']['처리 상태']=='실패' and rows['list']['처리 상태']=='답변 완료'
    assert any('AD MODEL RESPONSE' in p.read_text() and 'unsupported_parameter' in p.read_text()
               for p in shared.rglob('*.log'))
    assert any('HTTP 400' in p.read_text() for p in shared.rglob('*.txt'))
    before={p:p.read_bytes() for p in paths}
    request_summary.rebuild(shared,team='financial_team')
    assert all(p.read_bytes()==raw for p,raw in before.items())


def test_unhandled_probe_does_not_create_ad_report(serving):
    _,shared,calls,ask=serving
    assert ask('안녕','not-ad')['body']=={'ad_handled':False}
    assert calls==[] and reports(shared)==[]


def test_local_ad_validator_still_rejects_duplicate_values(serving):
    _,shared,_,ask=serving
    ask('[AD모드 시작]','enter')
    result=ask('duplicate','duplicates')
    assert result['body']['answer_status']=='error'
    record=next(r for r in reports(shared) if r['request_id']=='duplicates')
    assert record['journal']['changes']==[]
    assert 'uniqueItems' in json.dumps(SCHEMA)


def test_journal_export_scopes_same_request_id_to_chat_and_team(serving):
    runtime,_,_,ask=serving
    ask('[AD모드 시작]','same')
    request=bound_request({'ad_session_id':'different','ad_channel':'genos'})
    assert journal(runtime,'same',request)['status']=='NOT_FOUND'
    request['ad_report_binding'].update(chat='chat',workspace='risk_team')
    assert journal(runtime,'same',request)['status']=='NOT_FOUND'


def test_nested_ad_request_never_inherits_outer_conversation_identity(monkeypatch):
    monkeypatch.setenv('TEAM_ID','financial_team')
    value=bound_request({'ad_session_id':'foreign-chat','ad_channel':'foreign-channel',
                         'json':{'question':'[AD모드 시작]','request_id':'same'}})
    assert value['ad_report_binding']=={'workspace':'financial_team','channel':'genos-chat','chat':''}


def test_reporting_failure_keeps_success_response(serving,monkeypatch):
    _,shared,_,ask=serving
    shared.write_text('blocked')
    assert ask('[AD모드 시작]','enter')['body']['ad_mode'] is True
    assert ask('숏컷','list')['body']['answer_status']=='administration'


@pytest.mark.parametrize('body',[None, ['item'], 'plain response'])
def test_report_finalizer_preserves_non_object_response(tmp_path,body):
    result={'status':200,'body':body}
    with request_report.DeferredReport(tmp_path/'reports',tmp_path/'runtime',request_id='r',
            api_type='PING',request={},events=[]) as report:
        report.complete(result)
    request_report._FINALIZER_QUEUE.join()
    saved=reports(tmp_path/'reports')
    assert len(saved)==1 and saved[0]['result']==result


def test_schema_adapter_preserves_property_names_and_validation_schema():
    schema={'type':'object','properties':{'uniqueItems':{'type':'array','uniqueItems':True,
        'items':{'type':'string'}}},'const':{'uniqueItems':True}}
    before=copy.deepcopy(schema);wire=genos_wire_schema(schema)
    assert schema==before and wire['const']==schema['const']
    assert 'uniqueItems' in wire['properties']
    assert 'uniqueItems' not in wire['properties']['uniqueItems']


def test_legal_and_ad_share_wire_contract_and_omit_unsupported_keyword(monkeypatch):
    from test_genos_wire_schema import _gateway
    original=copy.deepcopy(SCHEMA)
    legal=_gateway(schema=SCHEMA).request('investigate',{},'ad_command_v1')
    ad=structured_request(model='synthetic',max_tokens=6400,messages=legal['messages'],
                          schema_name='ad_command_v1',schema=SCHEMA)
    assert legal==ad and SCHEMA==original
    # A synthetic grammar compiler reproduces the pre-fix request rejection.
    def accepts(schema):return 'uniqueItems' not in json.dumps(schema)
    assert not accepts(original) and accepts(ad['response_format']['json_schema']['schema'])


@pytest.mark.parametrize('finish',['stop',None,'length','content_filter'])
def test_shared_response_completion_rules(finish):
    body={'choices':[{'finish_reason':finish,'message':{'content':'{"action":"help","args":{}}'}}]}
    if finish in ('length','content_filter'):
        with pytest.raises(ProposalError):structured_content(body)
    else:assert json.loads(structured_content(body))['action']=='help'


@pytest.mark.parametrize('component',['../escape','ad-mode','LEGAL_AGENT'])
def test_report_path_rejects_arbitrary_components(tmp_path,component):
    with pytest.raises(ValueError):request_summary.report_directory(tmp_path,'risk_team',component=component)
