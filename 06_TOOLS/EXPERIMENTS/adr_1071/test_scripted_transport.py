"""Small pure contracts: no corpus, service, model or network."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

TOOLS = Path(__file__).parent
sys.path.insert(0, str(TOOLS))
from common import canonical_digest
from replay_transport import (EXPECTED_PHASES, RecordedTransport, ReplayBoundary,
                              validate_exchange)
from reconstruction_audit import compare_frame, frame_hashes


def fixture(ordinal=1):
    schema = {'type':'object', 'properties':{'choice':{'const':'READ'},
              'target':{'enum':['T-original']}}, 'required':['choice','target'],
              'additionalProperties':False}
    user = {'view':{'view_id':'V'+'a'*32, 'source_stage':EXPECTED_PHASES[ordinal-1],
                    'sources':[{'source_id':'S-original', 'text':'검증된 원문'}],
                    'tool_options':[{'choice':'READ','target':'T-original'}]},
            'step_state':{'budget_at_decision_start':{'seconds_remaining':179,
                          'model_remaining':41-ordinal,'tool_remaining':1024}}}
    request = {'model':'qwen/qwen3.8-27b', 'messages':[{'role':'system','content':'fixed'},
                 {'role':'user','content':json.dumps(user,ensure_ascii=False)}],
               'response_format':{'type':'json_schema','json_schema':{
                   'name':'BoundedSourceDecision','strict':True,'schema':schema}}}
    response = {'model':'qwen/qwen3.8-27b', 'provider':'Parasail', 'choices':[
        {'finish_reason':'stop','message':{'content':'{"choice":"READ","target":"T-original"}'}}]}
    envelope = {'status_code':200,'acceptance':'ACCEPTED','body_json':response,
                'stream_complete':True,'stream_receipt':{'complete':True}}
    return request,response,envelope


def replace_user(request, change):
    result = deepcopy(request)
    user = json.loads(result['messages'][1]['content'])
    change(user)
    result['messages'][1]['content'] = json.dumps(user,ensure_ascii=False)
    return result


def test_exact_response_and_metadata_difference_do_not_rewrite():
    request,response,envelope = fixture()
    original = deepcopy(envelope)
    actual = replace_user(request, lambda u:(u['view'].update(view_id='V'+'b'*32),
        u['step_state']['budget_at_decision_start'].update(seconds_remaining=177)))
    check = validate_exchange(request,actual,envelope,response,1)
    assert check['schema_exact'] and check['protected_user_payload_exact']
    assert not check['whole_request_exact'] and check['equivalence_comparable']
    assert envelope == original and not check['response_rewritten']


def test_source_difference_is_recorded_and_not_claimed_comparable():
    request,response,envelope = fixture()
    actual = replace_user(request,lambda u:u['view']['sources'][0].update(text='다른 원문'))
    check = validate_exchange(request,actual,envelope,response,1)
    assert check['response_valid_for_current_wire_schema']
    assert not check['protected_user_payload_exact'] and not check['projection_exact']
    assert not check['equivalence_comparable']


def test_nonrandom_view_alias_is_not_exempt():
    request,response,envelope = fixture()
    actual = replace_user(request,lambda u:u['view'].update(view_id='V1'))
    check = validate_exchange(request,actual,envelope,response,1)
    assert not check['protected_user_payload_exact']


@pytest.mark.parametrize('mutation,code',[
    ('schema','WIRE_SCHEMA_MISMATCH'), ('phase','PHASE_ORDER_MISMATCH'),
    ('target','RECORDED_RESPONSE_CURRENT_SCHEMA_INVALID'),
    ('incomplete','RECONSTRUCTION_INTEGRITY_FAILURE')])
def test_invalid_delivery_fails_before_response(mutation,code):
    request,response,envelope = fixture()
    actual = deepcopy(request)
    if mutation == 'schema':
        actual['response_format']['json_schema']['schema']['properties']['target']['enum']=['T-other']
    elif mutation == 'phase':
        actual = replace_user(request,lambda u:u['view'].update(source_stage='unknown'))
    elif mutation == 'target':
        response['choices'][0]['message']['content']='{"choice":"READ","target":"T-other"}'
    else:
        envelope['stream_complete']=False
    with pytest.raises(ReplayBoundary) as caught:
        validate_exchange(request,actual,envelope,response,1)
    assert caught.value.code == code


def test_frame_difference_remains_false_without_substitution():
    expected={'data':{'sources':[{'text':'원문'}]},'actions':{'T':{'action':'READ'}},'location':{'page':1}}
    actual=deepcopy(expected);actual['location']['page']=2
    before=deepcopy(actual)
    check=compare_frame(frame_hashes(expected),actual)
    assert not check['comparable'] and check['fields_exact']['data']
    assert actual == before


def test_all_eleven_literals_and_extra_call_guard(tmp_path,monkeypatch):
    import replay_transport as module
    monkeypatch.setattr(module,'ROOT',tmp_path)
    def write(name,value):
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value,ensure_ascii=False))
        return {'path':name,'sha256':module.sha(path)}
    rows=[];fixtures=[]
    for ordinal in range(1,12):
        request,response,envelope=fixture(ordinal);fixtures.append((request,response,envelope))
        rows.append({'call':ordinal,'request':write(f'{ordinal}/request.json',request),
                     'response':write(f'{ordinal}/response.json',response),
                     'response_receipt':write(f'{ordinal}/receipt.json',envelope)})
    outer=write('outer.json',{'API_TYPE':'RAG_ASK','json':{'question':'질문'}})
    inventory=write('inventory.json',{'schema_version':'exact-service-replay-inputs-v1',
        'cells':[{'case_id':'case','arm':'A0','source_completed':True,'calls':rows,'outer_request':outer}]})
    write('candidate/00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',{'key_env':'DUMMY','provider_routing':{}})
    frozen={'offline_only':True,'prefix_only':False,'scripted_reconstruction':True,
        'external_model_calls_allowed':0,'code_root':'candidate','replay_contract':{
            'inventory_path':inventory['path'],'inventory_sha256':inventory['sha256'],
            'expected_response_count':11,'expected_navigation_views':8,'schema_match':'exact','response_rewrite':False}}
    replay=RecordedTransport(frozen,{'case_id':'case','arm':'A0'},'B1')
    replay.out=tmp_path/'out';replay.out.mkdir();replay.audit=SimpleNamespace(views=0)
    for ordinal,(request,response,envelope) in enumerate(fixtures,1):
        replay.audit.views=min(8,ordinal-1)
        returned=replay.reply(request)
        assert returned == envelope and returned is not envelope
    receipt=replay.receipt()
    assert receipt['recorded_responses_used']==11 and receipt['external_model_calls']==0
    assert receipt['all_recorded_responses_consumed'] and not receipt['full_wire_replay_verified']
    with pytest.raises(ReplayBoundary):replay.reply(fixtures[-1][0])


def test_network_guard_blocks_inet_without_contact():
    import socket
    from replay_transport import offline_network
    with offline_network():
        with pytest.raises(ReplayBoundary) as caught:socket.getaddrinfo('example.invalid',443)
        assert caught.value.code=='RECONSTRUCTION_NETWORK_FORBIDDEN'
