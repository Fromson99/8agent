"""Location/read contracts using synthetic data; no latency or model experiment."""
from contextlib import closing
import json
from types import SimpleNamespace

import pytest

from semantic_runtime import fulltext, observability as obs
from semantic_runtime.legal_agent.errors import DeadlineExceeded
from semantic_runtime.legal_agent.workflow_relations_tools import RelationsTools
from semantic_runtime.term_index import SourceMap
from test_fulltext_diagnostics import database, index
from test_legal_agent_double_harness import generation
from test_legal_agent_v5 import session, PROFILE
from test_tool_exploration_v3 import tool as action


@pytest.fixture
def events(monkeypatch):
    records=[]
    monkeypatch.setattr(obs,'event',lambda logger,name,**fields:records.append({'event':name,**fields}))
    return records


def tools(db,monkeypatch,*,bounds=None,blocks=None):
    monkeypatch.setattr(fulltext,'question_terms',lambda text:text.split())
    db.execute('CREATE TABLE source(id TEXT PRIMARY KEY,json TEXT)')
    metadata={}
    for sid in ('s1','s2'):
        value={'document_id':'d','unit_id':sid,
               'blocks':(blocks or {}).get(sid,[{'block_id':'1','text':'alpha private body'}])}
        db.execute('INSERT INTO source VALUES(?,?)',(sid,json.dumps(value)))
        metadata[sid]={'document_id':'d','unit_id':sid}
    mapping=SourceMap(db)
    tool=RelationsTools.__new__(RelationsTools)
    tool.context=SimpleNamespace(deadline=float('inf'))
    tool.matcher=SimpleNamespace(fulltext=index(),fulltext_db=db,sources=metadata)
    tool.tools=SimpleNamespace(sources=mapping)
    tool.docs_bounds=lambda target:(['d'],bounds)
    tool.sources_in=lambda target:['s1','s2']
    tool.handle=lambda kind,value:'route'
    tool.resolve=lambda target:{'document_id':'d','unit_id':'bounded'}
    tool.page=lambda values,offset:(values[offset:offset+1],offset+1 if offset+1<len(values) else None)
    tool.node_card=lambda did,uid,source_id,route:{'document_id':did,'unit_id':uid,'source_id':source_id}
    return tool,mapping


ARGS={'mode':'fulltext','target':'R','query':'alpha'}


@pytest.mark.parametrize('unit_id',[None,'shared-unit'])
def test_metadata_keeps_rank_order_distinct_sources_and_cursor(events,monkeypatch,unit_id):
    with closing(database()) as db:
        tool,mapping=tools(db,monkeypatch)
        for value in tool.matcher.sources.values():value['unit_id']=unit_id
        tool.matcher.fulltext.rank=lambda *args:['s2','s1','s2']
        first=tool.search(ARGS,0)
        second=tool.search(ARGS,first[1])
        assert first[0]==[{'document_id':'d','unit_id':unit_id,'source_id':'s2'}]
        assert second[0]==[{'document_id':'d','unit_id':unit_id,'source_id':'s1'}]
        assert first[1]==1 and second[1] is None
        assert first[3]['search_receipt']['total']==second[3]['search_receipt']['total']==2
        assert first[3]['search_receipt']['total_status']=='exact'
        assert not mapping.cache
        assert all(row['source_sql_count']==0 for row in events if row['event']=='fulltext.location.timings')


def test_scope_excludes_hidden_source_before_metadata_lookup(events,monkeypatch):
    with closing(database()) as db:
        tool,mapping=tools(db,monkeypatch)
        first=tool.search(ARGS,0)
        assert first[0][0]['source_id']=='s1' and first[3]['search_receipt']['total']==2
        timing=next(row for row in events if row['event']=='fulltext.sql.timings')
        assert timing['fetched_count']==3 and timing['scope_rejected_count']==1
        assert 'hidden' not in tool.matcher.sources and not mapping.cache


def test_only_returned_page_reads_body_and_next_page_still_checks_body(events,monkeypatch):
    with closing(database()) as db:
        tool,mapping=tools(db,monkeypatch)
        db.execute('UPDATE source SET json=? WHERE id=?',('malformed body','s2'))
        def card(did,uid,source_id,route):
            return {'source_id':source_id,'text':mapping[source_id]['blocks'][0]['text']}
        tool.node_card=card
        first=tool.search(ARGS,0)
        assert first[0]==[{'source_id':'s1','text':'alpha private body'}]
        assert set(mapping.cache)=={'s1'} and first[3]['search_receipt']['total']==2
        timing=next(row for row in events if row['event']=='fulltext.location.timings')
        assert timing['source_sql_count']==timing['source_lookup_count']==0
        with pytest.raises(json.JSONDecodeError):tool.search(ARGS,first[1])
        assert set(mapping.cache)=={'s1'} and mapping._load_metrics is None
        assert 'private body' not in json.dumps(events)


@pytest.mark.parametrize('inside_text,expected_total',[('alpha',1),('beta',0)])
def test_bounded_search_checks_inside_text_and_excludes_outside_match(events,monkeypatch,inside_text,expected_total):
    blocks={'s1':[{'block_id':'0','text':'alpha'},{'block_id':'1','text':'beta'}],
            's2':[{'block_id':'1','text':inside_text},{'block_id':'2','text':'alpha'}]}
    with closing(database()) as db:
        tool,mapping=tools(db,monkeypatch,bounds=(1,2),blocks=blocks)
        tool.matcher.sources={}  # bounded lookup must use actual body blocks
        result=tool.search(ARGS,0)
        assert result[3]['search_receipt']['bounds']==(1,2)
        assert result[3]['search_receipt']['total']==expected_total and result[1] is None
        if expected_total:
            assert result[0]==[{'document_id':'d','unit_id':'bounded','source_id':None}]
        else:assert result[0]==[]
        timing=next(row for row in events if row['event']=='fulltext.location.timings')
        assert timing['source_sql_count']==2 and timing['bounds_enabled'] is True
        assert set(mapping.cache)=={'s1','s2'}


def test_bounded_matches_collapse_to_the_same_unit(events,monkeypatch):
    with closing(database()) as db:
        tool,mapping=tools(db,monkeypatch,bounds=(1,2))
        result=tool.search(ARGS,0)
        assert result[3]['search_receipt']['total']==1
        assert result[0]==[{'document_id':'d','unit_id':'bounded','source_id':None}]
        assert set(mapping.cache)=={'s1','s2'}


def test_missing_metadata_fails_without_silently_dropping_a_result(events,monkeypatch):
    with closing(database()) as db:
        tool,mapping=tools(db,monkeypatch)
        del tool.matcher.sources['s2']
        with pytest.raises(KeyError,match='s2'):tool.search(ARGS,0)
        timing=next(row for row in events if row['event']=='fulltext.location.timings')
        assert timing['mapping_status']=='failed' and timing['source_sql_count']==0
        assert mapping._load_metrics is None and not mapping.cache


def test_request_deadline_still_stops_metadata_mapping(events,monkeypatch):
    with closing(database()) as db:
        tool,mapping=tools(db,monkeypatch)
        def rank(*args):
            tool.context.deadline=0
            return ['s1','s2']
        tool.matcher.fulltext.rank=rank
        with pytest.raises(DeadlineExceeded,match='fulltext location mapping'):tool.search(ARGS,0)
        timing=next(row for row in events if row['event']=='fulltext.location.timings')
        assert timing['mapping_status']=='failed'
        assert mapping._load_metrics is None and not mapping.cache


def test_deadline_is_checked_during_a_long_metadata_iteration(events,monkeypatch):
    with closing(database()) as db:
        tool,mapping=tools(db,monkeypatch)
        tool.matcher.fulltext.rank=lambda *args:['s1','s2']*150
        class Metadata(dict):
            reads=0
            def __getitem__(self,key):
                self.reads+=1
                if self.reads==256:tool.context.deadline=0
                return super().__getitem__(key)
        tool.matcher.sources=Metadata(tool.matcher.sources)
        with pytest.raises(DeadlineExceeded):tool.search(ARGS,0)
        assert tool.matcher.sources.reads==256
        assert mapping._load_metrics is None and not mapping.cache


def test_empty_search_has_exact_zero_total_without_body_reads(events,monkeypatch):
    with closing(database()) as db:
        tool,mapping=tools(db,monkeypatch)
        tool.matcher.fulltext.rank=lambda *args:[]
        result=tool.search(ARGS,0)
        assert result[0]==[] and result[1] is None
        assert result[3]['search_receipt']['total']==0
        assert result[3]['search_receipt']['total_status']=='exact'
        assert mapping._load_metrics is None and not mapping.cache


def test_bounded_body_errors_remain_failures(events,monkeypatch):
    with closing(database()) as db:
        tool,mapping=tools(db,monkeypatch,bounds=(1,2))
        db.execute('UPDATE source SET json=? WHERE id=?',('malformed body','s1'))
        with pytest.raises(json.JSONDecodeError):tool.search(ARGS,0)
        timing=next(row for row in events if row['event']=='fulltext.location.timings')
        assert timing['mapping_status']=='failed' and timing['source_load_errors']==1
        assert mapping._load_metrics is None and not mapping.cache


def test_v5_pages_materialize_only_the_returned_bodies(tmp_path,generation,monkeypatch,events):
    with session(tmp_path,generation,profile={**PROFILE,'page_size':1}) as s:
        ids=[sid for sid,source in s.sources.matcher.sources.items() if source['document_id'] in s.sources.scope]
        monkeypatch.setattr(s.sources.matcher.fulltext,'rank',lambda *args:ids*1000)
        mapping=s.sources.tools.sources
        mapping.cache.clear()
        args={'target':s.sources.root,'mode':'fulltext','query':'승인','cursor':None}
        first=s.sources.execute(action('search',**args),'first')
        assert len(first['items'])==1 and first['search_receipt']['total']==len(ids)
        assert first['next_cursor'] and len(mapping.cache)==1
        second=s.sources.execute(action('search',**{**args,'cursor':first['next_cursor']}),'second')
        assert second['items'][0]['target']!=first['items'][0]['target']
        assert second['search_receipt']['total']==len(ids) and len(mapping.cache)==2
        assert all(row['source_sql_count']==0 for row in events if row['event']=='fulltext.location.timings')
        # A search preview is still not citation evidence. READ checks the body.
        selected=first['items'][0]
        assert selected['citation_eligible'] is False
        read_action=action('read',**selected['read_action']['args'])
        result=s.sources.execute(read_action,'read-first')
        assert result['evidence_ids']
        for ident in result['evidence_ids']:s.sources.source.verify(s.work.evidence(ident))


def test_compacted_navigation_uses_metadata_for_fulltext_and_preserves_read(tmp_path,term_glossary,monkeypatch,events):
    import sqlite3
    from semantic_runtime.app import create_app
    from semantic_runtime.navigation_storage import compact_generation
    import test_navigation_storage as storage_tests
    from test_legal_agent_double_harness import ROOT

    original_source=storage_tests.original_source
    def evidence_source(path):
        original_source(path)
        # The storage fixture uses a short placeholder; READ requires a SHA-256.
        with sqlite3.connect(path) as db:
            for table in ('document','source_block'):
                db.execute(f'UPDATE {table} SET source_artifact_sha256=?',('a'*64,))
        return path
    monkeypatch.setattr(storage_tests,'original_source',evidence_source)
    parent=storage_tests.make_monolithic(tmp_path,term_glossary)
    compact_generation(parent,tmp_path/'compact')
    compact=tmp_path/'compact/generation'
    app=create_app(tmp_path/'app',compact,contracts_root=ROOT,provider=object(),
                   implementation='legal-agent-tools-v5',
                   legal_agent_profile={**PROFILE,'model_binding':None})
    pipeline=app.state.pipeline
    try:
        question='영업일'
        with pipeline.term_agent.open_session(
            {'question':question,'document_ids':['doc'],'use_llm':False},
            query=pipeline.plan(question,['doc']),runtime=tmp_path/'runtime') as s:
            response=s.sources.execute(action('search',target=s.sources.root,mode='fulltext',
                                              query=question,cursor=None),'compact-search')
            assert response['items'] and response['search_receipt']['total']>0
            metrics=[row for row in events if row['event']=='fulltext.location.timings']
            assert len(metrics)==1 and metrics[0]['mapping_status']=='completed'
            assert metrics[0]['source_sql_count']==metrics[0]['source_lookup_count']==0
            selected=response['items'][0]
            assert selected['preview_spans'] and selected['citation_eligible'] is False
            read=s.sources.execute(action('read',**selected['read_action']['args']),'compact-read')
            assert read['evidence_ids']
            for ident in read['evidence_ids']:s.sources.source.verify(s.work.evidence(ident))
    finally:
        pipeline.store.close()
