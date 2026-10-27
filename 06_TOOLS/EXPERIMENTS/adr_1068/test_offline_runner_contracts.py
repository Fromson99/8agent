"""Pure boundary/receipt tests: no service, corpus, model or performance run."""
import asyncio
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import socket
import sys
from types import SimpleNamespace

import pytest


@pytest.fixture
def modules(monkeypatch):
    root=Path(__file__).parent;monkeypatch.syspath_prepend(str(root));result={}
    for name in ('common','replay_transport','profile_capture','run_case'):
        spec=importlib.util.spec_from_file_location(name,root/(name+'.py'))
        module=importlib.util.module_from_spec(spec);monkeypatch.setitem(sys.modules,name,module)
        spec.loader.exec_module(module);result[name]=module
    return result


def boundary(modules):
    check={'actual_sha256':'a'*64,'expected_sha256':'b'*64,'exact_match':False}
    replay=SimpleNamespace(calls=0,visits=1,matches=[check])
    error=modules['replay_transport'].ReplayBoundary('REPLAY_PREFIX_DIAGNOSTIC',**check,matched_responses=0)
    return replay,error


def test_direct_prefix_is_a_diagnostic_only(modules):
    replay,error=boundary(modules)
    result=modules['run_case'].expected_prefix_boundary(error,replay)
    assert result['boundary_leaf_count']==1 and result['cancelled_leaf_count']==0
    assert result['external_model_calls']==0 and result['recorded_responses_used']==0
    assert result['full_service_replay_verified'] is False


def test_nested_group_with_only_prefix_and_cancellation_is_expected(modules):
    replay,error=boundary(modules)
    group=BaseExceptionGroup('outer',[asyncio.CancelledError(),
        BaseExceptionGroup('inner',[error,asyncio.CancelledError()])])
    result=modules['run_case'].expected_prefix_boundary(group,replay)
    assert result['grouped'] is True and result['boundary_leaf_count']==1
    assert result['cancelled_leaf_count']==2


@pytest.mark.parametrize('other',[ValueError('unexpected'),MemoryError(),KeyboardInterrupt()])
def test_mixed_unexpected_leaf_is_never_a_success(modules,other):
    replay,error=boundary(modules)
    group=BaseExceptionGroup('outer',[error,BaseExceptionGroup('mixed',[other])])
    assert modules['run_case'].expected_prefix_boundary(group,replay) is None


def test_cancellation_or_other_boundary_alone_is_fatal(modules):
    replay,error=boundary(modules);classify=modules['run_case'].expected_prefix_boundary
    assert classify(BaseExceptionGroup('cancel',[asyncio.CancelledError()]),replay) is None
    error.code='REPLAY_NETWORK_FORBIDDEN'
    assert classify(error,replay) is None


def test_unproven_or_consumed_boundary_is_fatal(modules):
    replay,error=boundary(modules);classify=modules['run_case'].expected_prefix_boundary
    replay.calls=1;assert classify(error,replay) is None
    replay.calls=0;error.details['actual_sha256']='c'*64
    assert classify(error,replay) is None


def test_first_request_always_stops_without_reading_response(tmp_path,modules,monkeypatch):
    m=modules['replay_transport'];monkeypatch.setattr(m,'ROOT',tmp_path)
    request={'model':'synthetic','messages':[{'role':'user','content':'fixed'}],'flag':True}
    original=tmp_path/'request.json';original.write_text(json.dumps(request))
    transport=object.__new__(m.RecordedTransport)
    transport.calls=transport.visits=0;transport.matches=[];transport.out=tmp_path
    transport.source={'calls':[{'call':1,'request':{'path':'request.json','sha256':m.sha(original)},
        'response':{'path':'absent.json','sha256':'z'*64}}]}
    with pytest.raises(m.ReplayBoundary) as caught:transport.reply(request)
    assert caught.value.code=='REPLAY_PREFIX_DIAGNOSTIC' and caught.value.details['exact_match'] is True
    assert transport.calls==0
    other=deepcopy(request);other['flag']=1
    transport.visits=0;transport.matches=[];transport.out=tmp_path/'different';transport.out.mkdir()
    with pytest.raises(m.ReplayBoundary) as caught:transport.reply(other)
    assert caught.value.details['exact_match'] is False
    assert caught.value.details['top_level_field_equality']['flag'] is False
    assert transport.calls==0


def test_network_and_dns_are_blocked_and_restored(modules):
    m=modules['replay_transport'];resolver=socket.getaddrinfo;connect=socket.socket.connect
    with m.offline_network():
        with pytest.raises(m.ReplayBoundary):socket.getaddrinfo('example.invalid',443)
        with socket.socket() as sock:
            with pytest.raises(m.ReplayBoundary):sock.connect(('127.0.0.1',1))
    assert socket.getaddrinfo is resolver and socket.socket.connect is connect


def test_prepare_event_preserves_only_named_numeric_phases(modules):
    fields={'elapsed_ms':100,'thread_cpu_ms':90,'question':'discard', 'prepare_status':'READY',
        'phases':{'session.resources':{'wall_ms':80,'cpu_ms':75,'source':'discard'},
                  'arbitrary-source-name':{'wall_ms':1}}}
    result=modules['profile_capture'].prepare_fields(fields)
    assert result=={'elapsed_ms':100,'thread_cpu_ms':90,'prepare_status':'READY',
        'phases':{'session.resources':{'wall_ms':80,'cpu_ms':75}}}


def test_live_entry_is_rejected_before_reservation(modules):
    m=modules['run_case']
    with pytest.raises(m.IntegrityFailure,match='offline transport is mandatory'):
        m.run({'ordinal':1,'case_id':'fsc-hard-005','arm':'A0'},({},None,{},None,None,None))
