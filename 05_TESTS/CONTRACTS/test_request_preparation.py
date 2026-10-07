"""Preparation durability/cache/isolation contracts; no latency experiment or model calls."""
import json
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest
from semantic_runtime import document_aliases, folder_navigation, navigation_agent, observability as obs
from semantic_runtime.contracts import sha
from semantic_runtime.request_report import capture_events
from semantic_runtime.legal_agent.context import RequestContext
from semantic_runtime.legal_agent.repository import WorkRepository
from semantic_runtime.legal_agent.tools_repository import ToolsRepository
from semantic_runtime.legal_agent.relations_repository import RelationsRepository
from semantic_runtime.legal_agent.tiers_repository import TiersRepository
from semantic_runtime.legal_agent.obligation_repository import ObligationRepository
from test_legal_agent_double_harness import PROFILE
from test_genos_team_selection import team_generation, app_for


def context():
    request={'question':'합성 준비 계약?', 'use_llm':False}
    query={'id':'query:fixture', 'question':request['question'], 'scope':{'document_version_ids':['d']}}
    return RequestContext.create(query,request,{'generation_id':'g','store_sha256':'a'*64},300)


@pytest.mark.parametrize('kind',[WorkRepository,ToolsRepository,RelationsRepository,TiersRepository,ObligationRepository])
def test_initial_schema_and_request_commit_together_without_changing_schema(tmp_path,monkeypatch,kind):
    traced=[];connect=sqlite3.connect
    def observed(*args,**kwargs):
        db=connect(*args,**kwargs)
        db.set_trace_callback(lambda sql:traced.append((sql,db.in_transaction)))
        return db
    monkeypatch.setattr(sqlite3,'connect',observed)
    path=tmp_path/'journal.sqlite';ctx=context()
    repo=kind(path,ctx,PROFILE)
    try:
        assert repo.db.execute('PRAGMA synchronous').fetchone()[0]==2
        assert repo.db.execute('PRAGMA journal_mode').fetchone()[0]=='delete'
        assert repo.db.execute('PRAGMA foreign_keys').fetchone()[0]==1
        assert repo.db.execute('PRAGMA user_version').fetchone()[0]==kind.VERSION
        assert [s.strip() for s,_ in traced if s.strip() in ('BEGIN IMMEDIATE;','COMMIT')]==['BEGIN IMMEDIATE;','COMMIT']
        writes=[(s,t) for s,t in traced if s.strip().upper().startswith(('CREATE ','INSERT ')) or (s.strip().upper().startswith('PRAGMA USER_VERSION') and '=' in s)]
        assert len(writes)>20 and all(t for _,t in writes)
        # Compare actual sqlite schemas against the unchanged versioned DDL.
        reference=connect(':memory:')
        reference.executescript(Path(__import__('semantic_runtime.legal_agent.repository',fromlist=['x']).__file__).with_name(kind.DDL).read_text())
        schema='SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'
        assert [tuple(r) for r in repo.db.execute(schema)]==reference.execute(schema).fetchall()
        reference.close()
        assert repo.run()['run_id']==ctx.run_id and repo.budget()['model_limit']==PROFILE['max_model_attempts']
    finally:repo.close()
    reopened=kind(path,ctx,PROFILE)
    assert reopened.run()['run_id']==ctx.run_id
    reopened.close()


def test_failed_request_binding_rolls_back_schema_and_version(tmp_path):
    path=tmp_path/'failed.sqlite'
    with pytest.raises(KeyError,match='max_model_attempts'):
        WorkRepository(path,context(),{})
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM sqlite_master').fetchone()[0]==0


@pytest.mark.parametrize('kind',['origin','alias'])
def test_projection_warm_reads_are_cached_isolated_and_still_verify_changes(tmp_path,monkeypatch,kind):
    navigation_agent._JSON_MEMO.clear()
    store=SimpleNamespace(manifest={'generation_id':'g','store_sha256':'a'*64})
    value={**store.manifest,'schema_version':'document-origin-projection-v1' if kind=='origin' else document_aliases.SCHEMA,
           'evidence':{},'documents':{'d':{'aliases':[{'surface':'모의법'}]}}}
    path=tmp_path/'projection.json';path.write_text(json.dumps(value))
    key='origin_projections' if kind=='origin' else 'alias_projections'
    config={key:[{'generation_id':'g','path':path.name,'sha256':sha(path)}]}
    load=folder_navigation.load_origin_projection if kind=='origin' else document_aliases.load
    reads=[];read=Path.read_bytes
    def observed(p):
        if p==path:reads.append(p)
        return read(p)
    monkeypatch.setattr(Path,'read_bytes',observed)
    first=load(tmp_path,config,store)
    if kind=='origin':first['evidence']['injected']={'bad':True}
    else:first['d']=('injected',)
    second=load(tmp_path,config,store)
    assert len(reads)==1
    assert ('injected' not in second['evidence']) if kind=='origin' else second['d']==('모의법',)
    stale=SimpleNamespace(manifest={**store.manifest,'store_sha256':'b'*64})
    with pytest.raises(ValueError,match='stale'):load(tmp_path,config,stale)
    path.write_text(json.dumps({**value,'mutation':True}))
    with pytest.raises(ValueError,match='hash mismatch'):load(tmp_path,config,store)


def test_two_ready_sessions_report_preparation_and_keep_journals_separate(tmp_path,team_generation,monkeypatch):
    records=[]
    monkeypatch.setattr(obs,'event',lambda logger,name,**fields:records.append({'event':name,**fields}))
    p=app_for(tmp_path,team_generation).state.pipeline
    request={'question':'모의 승인?', 'use_llm':False}
    ids=[];paths=[]
    try:
        for _ in range(2):
            query=p.plan(request['question'],team_id='risk_team')
            with p.term_agent.open_session(request,query=query,runtime=tmp_path/'runtime') as s:
                ids.append(s.context.run_id);paths.append(s.work.path)
                assert s.work.binding['pipeline_sha256']==sha(p.contracts.root/'00_SYSTEM/PIPELINE.json')
    finally:p.store.close()
    assert ids[0]!=ids[1] and paths[0]!=paths[1]
    summaries=[r for r in records if r['event']=='session.prepare.timings']
    assert len(summaries)==2
    for r in summaries:
        assert r['prepare_status']=='READY' and r['process_id']==os.getpid()
        assert set(r['phases'])=={'session.store','session.resources','session.context','session.journal','session.sources','session.gateway'}
        assert all(v['wall_ms']>=0 and v['cpu_ms']>=0 for v in r['phases'].values())
        assert request['question'] not in json.dumps(r,ensure_ascii=False)


def test_preparation_failure_has_one_failure_summary(tmp_path,team_generation,monkeypatch):
    records=[]
    monkeypatch.setattr(obs,'event',lambda logger,name,**fields:records.append({'event':name,**fields}))
    p=app_for(tmp_path,team_generation).state.pipeline
    try:
        p.term_agent.transport=None
        with pytest.raises(Exception,match='explicit deployment model profile'):
            with p.term_agent.open_session({'question':'모의?', 'use_llm':True},query=p.plan('모의?'),runtime=tmp_path):pass
    finally:p.store.close()
    summaries=[r for r in records if r['event']=='session.prepare.timings']
    assert len(summaries)==1 and summaries[0]['prepare_status']=='FAILED'


def test_safe_completed_report_capture_preserves_stage_metrics(tmp_path,team_generation):
    p=app_for(tmp_path,team_generation).state.pipeline
    request={'question':'PRIVATE_PREPARATION_FIXTURE','use_llm':False}
    try:
        with capture_events('preparation-contract') as events, obs.context(request_id='preparation-contract'):
            with p.term_agent.open_session(request,query=p.plan(request['question']),runtime=tmp_path/'runtime'):pass
    finally:p.store.close()
    rows=[e for e in events if e['event']=='session.prepare.timings']
    assert len(rows)==1 and rows[0]['prepare_status']=='READY'
    assert 'session.journal' in rows[0]['phases']
    assert 'PRIVATE_PREPARATION_FIXTURE' not in json.dumps(rows)
