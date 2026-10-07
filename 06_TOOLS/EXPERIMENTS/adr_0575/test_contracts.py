"""Ordinary engineering contracts, not semantic or latency certification."""
from datetime import datetime,timezone
import fcntl
import json
from pathlib import Path
import sqlite3
import sys

import pytest
from fastapi.testclient import TestClient
from harness import candidate,fixture,app,synthetic_transport,phases,R

@pytest.fixture(scope="module")
def modules():
    with candidate(snapshot=True): yield

def sample():
    from lawrag.core.action_memory import data_key
    b={'generation_id':'g','store_sha256':'a'*64}
    a={'source_id':'A','document_id':'d','unit_id':'1','heading':'적용규정','origin_hash':'b'*64,'text':'원칙과 예외를 확인한다.','reason':'적용 원칙 확인'}
    c={'source_id':'C','document_id':'d','unit_id':'2','heading':'실적표','origin_hash':'b'*64,'text':'인수 실적은100건이다.','reason':''}
    return {'id':'episode1','question':'적용 규정을 확인해 주세요.','purpose_reason':'규정 적용 확인','binding':b,'data_key':data_key(b),'selected':[a],'originals':[a,c]}

def assignment(e): return {'episode_id':e['id'],'concept_id':'','label':'적용규정 확인','definition':'행위에 적용되는 원칙과 예외 원문 확인','source_ids':['A'],'reason':'기존 선택 이유에 따른 적용 규정 확인'}

def populated(tmp_path):
    from lawrag.core.action_memory import Memory
    m=Memory(tmp_path/'memory.sqlite');e=sample();m.ingest(e);m.adopt([assignment(e)])
    return m,e,m.catalogue()[0]['id']

def test_memory_concepts_are_source_bound_and_unknown_keeps_access(modules,tmp_path):
    m,e,c=populated(tmp_path)
    assert m.compile(c,e['binding'],['A','C'],'discover')['allowed_node_ids']==['A','C']
    assert m.compile(c,e['binding'],['A','C'],'read')['guide_node_ids']==['A']
    assert m.compile(c,{'generation_id':'new','store_sha256':'c'*64},['A','C'],'read')['guide_node_ids']==[]
    assert m.catalogue(e['binding'],['other'])==[]
    with pytest.raises(ValueError): m.adopt([{**assignment(e),'source_ids':['C']}])
    m.close()

def test_reviewed_exclusion_is_generic_and_not_nonselection(modules,tmp_path):
    m,e,c=populated(tmp_path)
    with pytest.raises(ValueError): m.record_exclusion(e['id'],c,'C',reason='미선택',review={})
    m.record_exclusion(e['id'],c,'C',reason='규정 확인에는 이 순수 실적표 불필요',review={'verdict':'VALIDATED','reviewer':'synthetic-independent-source-review','quote':'인수 실적은100건이다.','origin_hash':'b'*64})
    for op in ['discover','list','traverse','read','definition','occurrences']:
        assert m.compile(c,e['binding'],['A','C'],op)['allowed_node_ids']==['A']
    with pytest.raises(ValueError): m.record_exclusion(e['id'],c,'A',reason='충돌',review={'verdict':'VALIDATED','reviewer':'fixture','quote':'원칙','origin_hash':'b'*64})
    e['negative_feedback']=[{'signal':'WRONG_ANSWER'}];m.ingest(e)
    assert m.compile(c,e['binding'],['A','C'],'read')['allowed_node_ids']==['A','C'];m.close()

def test_tampered_proof_restores_access(modules,tmp_path):
    m,e,c=populated(tmp_path)
    m.record_exclusion(e['id'],c,'C',reason='불필요',review={'verdict':'VALIDATED','reviewer':'fixture','quote':'실적','origin_hash':'b'*64})
    m.db.execute("UPDATE observation SET proof_hash=? WHERE predicate='EXCLUDES'",('f'*64,));m.db.commit()
    assert m.compile(c,e['binding'],['A','C'],'read')['allowed_node_ids']==['A','C'];m.close()

@pytest.mark.parametrize('at,inside',[('2026-09-29T14:59:59+00:00',False),('2026-09-29T15:00:00+00:00',True),('2026-09-29T20:59:59+00:00',True),('2026-09-29T21:00:00+00:00',False)])
def test_kst_window_boundaries(modules,at,inside):
    from lawrag.pipeline.action_memory import window
    assert window(datetime.fromisoformat(at))['inside'] is inside

def test_outside_window_does_not_collect_or_call_model(modules,tmp_path):
    from lawrag.pipeline.action_memory import build
    class NoModel:
        def eligible(self,e): raise AssertionError('model outside window')
    r=build(R,runtime=tmp_path,model=NoModel(),at=datetime.fromisoformat('2026-09-29T21:00:00+00:00'))
    assert r['state']=='OUTSIDE_WINDOW'
    assert not (tmp_path/'action-memory/memory.sqlite').exists()

def test_single_worker_lock(modules,tmp_path):
    from lawrag.pipeline.action_memory import build
    d=tmp_path/'action-memory';d.mkdir()
    with (d/'build.lock').open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert build(R,runtime=tmp_path,manual=True)['state']=='ALREADY_RUNNING'

def test_full_api_journal_build_and_next_request_reuses_concept(modules,tmp_path):
    from lawrag.core.action_memory import episode_from_journal,Memory
    from lawrag.pipeline.action_memory import build
    gen=fixture(tmp_path/'fixture');t=synthetic_transport();a=app(tmp_path,gen,t,enabled=True)
    with TestClient(a) as client:
        response=client.post('/v1/rag/ask',json={'question':'모의승인규정의 승인 원칙과 위임 예외를 설명해 주세요.','document_ids':['d']})
        assert response.status_code==200,response.text
        result=response.json();assert len(result['assembly']['term_agent']['source_bundle']['sources'])==2
        assert phases(t)==['source-query-plan','source-triage','compose']
        journals=list((tmp_path/'runtime/legal-agent/runs').glob('*/*/journal.sqlite'))
        e=episode_from_journal(journals[0]);assert len(e['selected'])==2
        class Model:
            calls=0
            def eligible(self,e): return True
            def generate(self,episodes,concepts,remaining,output):
                self.calls+=1
                with (tmp_path/'model-calls.txt').open('a') as receipt:receipt.write('call\n')
                return {'assignments':[{'episode_id':e['id'],'concept_id':'','label':'승인규정 적용 확인','definition':'승인 원칙과 위임 예외 확인','source_ids':[s['source_id'] for s in e['selected']],'reason':'원문 선택 이유 재사용'} for e in episodes],'exclusion_candidates':[]}
        model=Model();r=build(R,runtime=tmp_path/'runtime',manual=True,model=model)
        assert r['counts']['built_episodes']==1 and r['concepts']==1 and r['relations']['GUIDES_TO']==2
        r2=build(R,runtime=tmp_path/'runtime',manual=True,model=model)
        assert r2['counts']['new_episodes']==0 and r2['counts']['unchanged_journals']==1 and (tmp_path/'model-calls.txt').read_text().splitlines()==['call']
        before=len(t.calls)
        response=client.post('/v1/rag/ask',json={'question':'적법한 위임의 승인 예외를 확인해 주세요.','document_ids':['d']})
        assert response.status_code==200,response.text
        v=json.loads(t.calls[before]['messages'][1]['content'])['view']
        assert v['investigation_concepts'][0]['label']=='승인규정 적용 확인'
        assert len(t.calls)-before==3
        assert client.get('/v1/rag/action-memory/status').json()['concepts']==1
        feedback=client.post('/v1/rag/feedback',json={'run_id':result['run_id'],'signal':'WRONG_ANSWER','reason':'합성 부정 피드백 검증'})
        assert feedback.status_code==200,feedback.text
        assert client.get('/v1/rag/action-memory/status').json()['episodes']['NEGATIVE']==1

def test_provider_failure_is_durable_and_resumes_without_duplicate_episodes(modules,tmp_path):
    from lawrag.pipeline.action_memory import build
    gen=fixture(tmp_path/'fixture');t=synthetic_transport();a=app(tmp_path,gen,t,enabled=True)
    with TestClient(a) as client:
        assert client.post('/v1/rag/ask',json={'question':'모의승인규정의 승인 원칙은?','document_ids':['d']}).status_code==200
    class Failure:
        def eligible(self,e): return True
        def generate(self,*args): raise TimeoutError('fixture provider failure')
    r=build(R,runtime=tmp_path/'runtime',manual=True,model=Failure())
    assert r['state']=='FAILED' and r['episodes']['FAILED']==1
    assert 'MODEL_FAILED' in (tmp_path/'runtime/action-memory/build.jsonl').read_text()

def test_sql_exclusion_happens_before_rows_are_fetched(modules,tmp_path):
    from semantic_runtime.fulltext import FulltextIndex
    gen=fixture(tmp_path/'fixture');t=synthetic_transport();a=app(tmp_path,gen,t,enabled=True);p=a.state.pipeline
    try:
        request={'question':'승인','document_ids':['d'],'use_llm':True}
        with p.term_agent.open_session(request,query=p.plan('승인',['d']),runtime=tmp_path/'runtime') as s:
            ids=list(s.sources.matcher.sources)
            denied=next(i for i in ids if s.sources.matcher.sources[i]['document_id']=='d')
            db=s.sources.matcher.fulltext_db;sql=[];db.set_trace_callback(sql.append)
            out=s.sources.matcher.fulltext.rank(db,['승인'],excluded_source_ids=[denied])
            assert denied not in out
            assert any('source_id NOT IN (SELECT value FROM json_each(' in q for q in sql)
    finally: p.store.close()
