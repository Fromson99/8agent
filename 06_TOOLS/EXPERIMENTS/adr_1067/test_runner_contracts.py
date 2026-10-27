"""Small synthetic runner contracts; no service, corpus, credential or model."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import socket
import sqlite3
import sys

import pytest


@pytest.fixture
def modules(monkeypatch):
    root=Path(__file__).parent
    monkeypatch.syspath_prepend(str(root))
    loaded={}
    for name in ('common','delivery_spans','wire_audit','collect_metrics','physical_transport','gate','replay_transport','profile_capture'):
        spec=importlib.util.spec_from_file_location(name,root/(name+'.py'))
        module=importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules,name,module)
        spec.loader.exec_module(module)
        loaded[name]=module
    return loaded


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False))
    return path


def replay_fixture(tmp_path,modules,monkeypatch):
    m=modules['replay_transport'];monkeypatch.setattr(m,'ROOT',tmp_path)
    policy={'key_env':'SYNTHETIC_REPLAY_KEY','provider_routing':{'only':['parasail/fp8']}}
    write(tmp_path/'code/00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',policy)
    body={'provider':'Parasail','model':'qwen/qwen3.8-27b','choices':[{'finish_reason':'stop','message':{'content':'{}'}}]}
    payload={'model':'qwen/qwen3.8-27b','messages':[{'role':'user','content':'exact'}]}
    files={'outer':{'API_TYPE':'RAG_ASK','request_id':'old','json':{'question':'q'}},
           'request':payload,'response':body,
           'receipt':{'status_code':200,'stream_complete':True,'stream_receipt':{'complete':True},'body_json':body}}
    refs={}
    for key,value in files.items():
        path=write(tmp_path/(key+'.json'),value)
        refs[key]={'path':str(path.relative_to(tmp_path)),'sha256':m.sha(path)}
    inventory={'schema_version':'exact-service-replay-inputs-v1','cells':[
        {'case_id':'q','arm':'A0','outer_request':refs['outer'],'calls':[
            {'call':1,'request':refs['request'],'response_receipt':refs['receipt'],'response':refs['response']}]}]}
    path=write(tmp_path/'inventory.json',inventory)
    frozen={'code_root':'code','replay_contract':{'inventory_path':'inventory.json',
        'inventory_sha256':m.sha(path),'allow_prefix_diagnostic':True}}
    replay=m.RecordedTransport(frozen,{'case_id':'q','arm':'A0'},'B0')
    replay.out=tmp_path
    return m,replay,payload,body


def test_replay_exact_only_and_no_external_calls(tmp_path,modules,monkeypatch):
    m,replay,payload,body=replay_fixture(tmp_path,modules,monkeypatch)
    envelope=replay.reply(payload)
    assert envelope['body_json']==body
    assert replay.receipt()['external_model_calls']==0
    assert replay.receipt()['recorded_responses_used']==1
    assert replay.receipt()['request_identity_normalization'] is False
    with pytest.raises(m.ReplayBoundary) as caught:replay.reply(payload)
    assert caught.value.code=='REPLAY_RECORDS_EXHAUSTED'


def test_replay_different_request_is_prefix_not_response(tmp_path,modules,monkeypatch):
    m,replay,payload,_=replay_fixture(tmp_path,modules,monkeypatch)
    changed=deepcopy(payload);changed['messages'][0]['content']='different'
    with pytest.raises(m.ReplayBoundary) as caught:replay.reply(changed)
    assert caught.value.code=='REPLAY_PREFIX_DIAGNOSTIC'
    assert replay.calls==0
    assert replay.matches[0]['exact_match'] is False


def test_replay_changed_recorded_bytes_fail_closed(tmp_path,modules,monkeypatch):
    m,replay,payload,_=replay_fixture(tmp_path,modules,monkeypatch)
    write(tmp_path/'receipt.json',{'status_code':200})
    with pytest.raises(m.ReplayBoundary) as caught:replay.reply(payload)
    assert caught.value.code=='REPLAY_INTEGRITY_FAILURE'
    assert replay.calls==0


def test_offline_socket_blocked_before_connect(modules):
    m=modules['replay_transport']
    with m.offline_network(),socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
        with pytest.raises(m.ReplayBoundary) as caught:sock.connect(('127.0.0.1',1))
    assert caught.value.code=='REPLAY_NETWORK_FORBIDDEN'


def test_lifetime_capture_is_numeric_and_does_not_wait_for_finalizer(modules):
    import logging
    capture=modules['profile_capture']
    logger=logging.getLogger('genos')
    record=logging.LogRecord('genos',logging.INFO,__file__,0,'timing.service.returning',(),None)
    record.fields={'duration_ms':12.5,'returning_ns':100,'finalizer_included':False,
                   'request_id':'synthetic','question':'not captured'}
    with capture.capture() as records:
        logger.handle(record)
    assert len(records)==1 and 'question' not in records[0]['fields']
    result=capture.receipt(records,freeze_hash='a'*64,code_root='synthetic',replay=True,
                           service_seconds=.0125,shared_report_enabled=True)
    assert result['report_finalizer']['status']=='NOT_MEASURED'
    assert result['report_finalizer']['finalizer_wait_added'] is False


def test_native_evidence_id_replaces_missing_parent_coordinates(tmp_path,modules):
    spans=modules['delivery_spans'];wire=modules['wire_audit']
    record={'evidence_id':'e','document_id':'d','source_id':'s','source_artifact_hash':'a'*64,
        'generation_id':'g','created_seq':1,'text_hash':spans.text_hash('abc'),
        'spans':[{'ordinal':0,'block_id':'b','start_cp':5,'end_cp':8,'text':'abc','span_hash':spans.text_hash('abc')}]}
    checks=[{'evidence_id':'e','exact_original_match':True,'span_count':1}]
    acquired=[{'evidence_id':'e','document_id':'d','source_id':'s','block_id':'b','start_cp':5,'end_cp':8,
        'text_sha256':spans.text_hash('abc'),'source_artifact_sha256':'a'*64}]
    index=spans.evidence_index([record],checks,acquired,{'d'},'g')
    view={'exact_evidence':[{'evidence':'e','text':'abc','spans':[{
        'block_id':'b','start_cp':5,'end_cp':8,'text':'abc'}]}]}
    with pytest.raises(wire.WireAuditError):wire.explicit_spans(view)
    result=spans.audit_view(view,view,index,{'d'})
    assert result['status']=='VERIFIED'
    assert result['occurrences'][0]['document_id']=='d'
    assert result['occurrences'][0]['evidence_id']=='e'
    changed=deepcopy(view);changed['exact_evidence'][0]['evidence']='unknown'
    with pytest.raises(spans.AuditError):spans.audit_view(changed,view,index,{'d'})


def test_gate_native_span_inventory_is_exact(tmp_path,modules):
    gate=modules['gate'];digest=modules['common'].canonical_digest
    view={'view_id':'v','exact_evidence':[{'evidence':'e','text':'abc','spans':[{
        'block_id':'b','start_cp':5,'end_cp':8,'text':'abc'}]}]}
    request={'messages':[{'role':'user','content':json.dumps({'view':view})}]}
    request_path=write(tmp_path/'model/call-001-service/request.json',request)
    write(tmp_path/'result.json',{'model_calls':1})
    (tmp_path/'physical-calls.jsonl').write_text(json.dumps({'event':'START','call':1})+'\n'+
        json.dumps({'event':'END','call':1,'acceptance':'ACCEPTED'})+'\n')
    journal=tmp_path/'journal.sqlite';db=sqlite3.connect(journal)
    db.executescript('CREATE TABLE model_view(view_id TEXT,body_json TEXT,body_hash TEXT);'
        'CREATE TABLE model_attempt(attempt_id TEXT,view_id TEXT,status TEXT,request_json TEXT,request_hash TEXT);')
    db.execute('INSERT INTO model_view VALUES(?,?,?)',('v',json.dumps(view),digest(view)))
    db.execute('INSERT INTO model_attempt VALUES(?,?,?,?,?)',('a','v','SUCCEEDED',json.dumps(request),digest(request)))
    db.commit();db.close()
    span={'document_id':'d','source_id':'s','source_ref':None,'evidence_id':'e','block_id':'b',
        'start_cp':5,'end_cp':8,'text':'abc'}
    size=len(json.dumps(request,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False))
    call={'request_path':str(request_path.relative_to(tmp_path)),'request_sha256':gate.sha(request_path),
        'canonical_request_sha256':digest(request),'request_chars':size,'status':'VERIFIED_EXACT_RECONSTRUCTION',
        'missing_text_spans':0,'input_budget_receipts':[{'contract':'execution-review-input-modes-v1',
            'input_mode':'REVIEW','request_sha256':digest(request),'measured_chars':size,
            'mode_limit_chars':48000,'outer_limit_chars':100000,'configured_limit_chars':48000,
            'enforcement_enabled':False,'max_context_chars':0,'status':'WITHIN_BUDGET'}],
        'successful_native_attempts':[{'journal':'journal.sqlite','attempt_id':'a','view_id':'v'}],
        'originals':[{**{k:v for k,v in span.items() if k!='text'},'text_sha256':gate.text_hash('abc')}],
        'ontology_bundles':[],'current_source_hash':digest([])}
    native={('journal.sqlite','a','v'):{'attempt_status':'SUCCEEDED','native_request_sha256':digest(request),
        'status':'VERIFIED_EXACT_RECONSTRUCTION','missing_text_spans':0,'spans':[span]}}
    assert gate._input_calls({'calls':[call]},tmp_path,native_records=native)==[]
    missing=deepcopy(call);missing['originals']=[]
    assert 'GATE_SOURCE_SPAN_INVENTORY_CHANGED' in {e['code'] for e in gate._input_calls(
        {'calls':[missing]},tmp_path,native_records=native)}
    assert 'GATE_NATIVE_SOURCE_RECONSTRUCTION_UNKNOWN' in {e['code'] for e in gate._input_calls(
        {'calls':[call]},tmp_path,native_records={})}
