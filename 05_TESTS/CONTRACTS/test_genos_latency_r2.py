"""Synthetic correctness/queue failure contracts; no model or performance experiment."""
from contextlib import closing
from copy import deepcopy
import io
import logging
import os
import threading
from types import SimpleNamespace

import pytest
from semantic_runtime.storage import Store
from semantic_runtime import team_scope, observability as obs
from semantic_runtime.multi_entry_navigation import freeze, validate_structure
from semantic_runtime.legal_agent_adapter import ServingLegalAgent
from semantic_runtime.legal_agent.errors import AdmissionRejected, ContractError
from semantic_runtime.legal_agent.exploration_tools import ExplorationTools
from test_genos_team_selection import team_generation, app_for


def test_catalogue_shared_across_connections_without_repeated_document_sql(team_generation):
    team_scope._CACHE.clear()
    with closing(Store(team_generation)) as first, closing(Store(team_generation)) as second:
        sql=[];first.db.set_trace_callback(sql.append);second.db.set_trace_callback(sql.append)
        a=team_scope.prepared_catalogue(first)
        assert team_scope.prepared_catalogue(second) is a
        assert team_scope.select_documents(first,'risk_team')==['duplicate','risk']
        assert team_scope.select_documents(second,'financial_team')==['duplicate','finance']
        assert len([q for q in sql if 'FROM document' in q])==1
        with pytest.raises(TypeError):a['teams']['risk']=frozenset()
        assert first.db is not second.db


@pytest.mark.parametrize('file',['store.sqlite','manifest.json'])
def test_changed_source_cannot_use_ready_catalogue(team_generation,file,monkeypatch):
    # ADR-1504: the file-system proof of the local store runs at most once a second (as the Oracle store,
    # MAIN190); a changed file is refused within that second.
    from semantic_runtime import oracle_dp_io
    clock=[1000.0];monkeypatch.setattr(oracle_dp_io.time,'monotonic',lambda:clock[0])
    with closing(Store(team_generation)) as store:
        team_scope.prepared_catalogue(store)
        path=team_generation/file;s=path.stat()
        os.utime(path,ns=(s.st_atime_ns,s.st_mtime_ns+1000000))
        clock[0]+=1.0
        with pytest.raises(ValueError,match='changed'):team_scope.prepared_catalogue(store)


def test_team_run_plans_once_and_releases_admission_after_invalid_scope(tmp_path,team_generation,monkeypatch):
    p=app_for(tmp_path,team_generation).state.pipeline
    plan=p.plan;calls=[]
    def counted(*args,**kwargs):calls.append(1);return plan(*args,**kwargs)
    monkeypatch.setattr(p,'plan',counted)
    result=p.run('전체 문서 목록',use_llm=False,team_id='risk_team',execution_context={'runtime':tmp_path/'runtime'})
    assert result['answer'] and calls==[1]
    with pytest.raises(ValueError):p.run('목록',documents=['finance'],team_id='risk_team')
    p.term_agent.admission=threading.BoundedSemaphore(1)
    with p.term_agent.admit() as lease:
        with p.term_agent.admit(lease):pass
        # Saturation rejects before any planning or metadata SQL.
        with pytest.raises(AdmissionRejected):p.run('목록')


def test_admission_nested_lease_and_cancel_release_once():
    a=ServingLegalAgent.__new__(ServingLegalAgent);a.admission=threading.BoundedSemaphore(1)
    with pytest.raises(KeyboardInterrupt):
        with a.admit() as lease:
            with a.admit(lease):pass
            with pytest.raises(AdmissionRejected):
                with a.admit():pass
            raise KeyboardInterrupt()
    with a.admit():pass
    with pytest.raises(ContractError):
        with a.admit(lease):pass


def synthetic_matcher(units):
    units=freeze(units)
    prepared={'units':units,'unit_index':{'d':tuple(units)},'source_index':{},
              'validated':frozenset(),'lock':threading.Lock()}
    return SimpleNamespace(units=units,prepared_structure=prepared)


def test_successful_structure_is_reused_and_normal_mutation_fails():
    m=synthetic_matcher({('d','1'):{'parent':None,'span':[0,2]},('d','2'):{'parent':'1','span':[1,2]}})
    assert validate_structure(m,['d'])==2
    assert validate_structure(m,['d'])==0
    with pytest.raises(TypeError):m.units[('d','1')]['span'][0]=5
    mutable=deepcopy(m.units);mutable[('d','2')]['parent']='missing';m.units=mutable
    with pytest.raises(ContractError,match='parent'):validate_structure(m,['d'])


@pytest.mark.parametrize('bad',[
    {('d','1'):{'parent':'missing','span':[0,2]}},
    {('d','1'):{'parent':'2','span':[0,2]},('d','2'):{'parent':'1','span':[1,2]}},
    {('d','1'):{'parent':None,'span':[2,1]}},
    {('d','1'):{'parent':None,'span':None}},
])
def test_failed_structure_never_marks_ready(bad):
    m=synthetic_matcher(bad)
    for _ in range(2):
        with pytest.raises(ContractError):validate_structure(m,['d'])
        assert not m.prepared_structure['validated']


def test_indexed_sources_preserve_interleaved_order_and_team_scope():
    t=ExplorationTools.__new__(ExplorationTools)
    t.matcher=SimpleNamespace(prepared_structure={'source_index':{
        'a':((0,'s1'),(2,'s3')),'b':((1,'s2'),),'other':((3,'hidden'),)}})
    t.docs_bounds=lambda target:(['b','a'],None)
    assert t.sources_in('R')==['s1','s2','s3']
    t.docs_bounds=lambda target:(['a'],None)
    assert t.sources_in('R')==['s1','s3']


def test_log_blocked_writer_queue_is_bounded_and_final_event_reserved():
    entered,release=threading.Event(),threading.Event();seen=[]
    class Blocked(logging.Handler):
        def emit(self,record):
            entered.set();assert release.wait(5);seen.append(record.getMessage())
    writer=obs.AsyncHandler(Blocked(),max_records=128,max_bytes=65536)
    def event(name,level=logging.INFO):
        r=logging.LogRecord('genos.test',level,__file__,1,name,(),None);r.fields={'request_id':'fixture'}
        writer.handle(r)
    try:
        event('first');assert entered.wait(2)
        for _ in range(500):event('ordinary')
        event('request.returning')
        assert len(writer.queue)<=128 and writer.bytes<=65536 and writer.dropped>0
        release.set();assert writer.drain(2)
        assert seen[0]=='first' and seen[-1]=='request.returning' and 'logging.queue.loss' in seen
    finally:release.set();writer.close();writer.worker.join(2)


def test_failed_diagnostic_write_does_not_raise_to_caller():
    class Broken(logging.Handler):
        def emit(self,record):raise OSError('synthetic storage failure')
    writer=obs.AsyncHandler(Broken())
    record=logging.LogRecord('genos.test',logging.ERROR,__file__,1,'failed',(),None)
    writer.handle(record);assert writer.drain(2);assert writer.write_errors==1
    writer.close();writer.worker.join(2)
