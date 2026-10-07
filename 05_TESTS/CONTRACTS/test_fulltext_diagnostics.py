"""Synthetic telemetry and search-contract checks; no performance/model experiment."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import threading
from types import SimpleNamespace

import pytest
from semantic_runtime import fulltext, observability as obs
from semantic_runtime.term_index import SourceMap
from semantic_runtime.legal_agent.workflow_relations_tools import RelationsTools


@pytest.fixture
def events(monkeypatch):
    records=[]
    def record(logger,name,**fields):records.append({'event':name,**fields})
    monkeypatch.setattr(obs,'event',record)
    return records


def index():
    value=fulltext.FulltextIndex.__new__(fulltext.FulltextIndex)
    value.manifest={'counts':{'source':3},'tokenizer':{'name':'synthetic'},
                    'ranking':{'bm25_weights':{'heading':10.0,'body':1.0}}}
    return value


def database():
    db=sqlite3.connect(':memory:')
    db.execute('CREATE VIRTUAL TABLE source_fts USING fts5(source_id UNINDEXED,heading,body)')
    db.executemany('INSERT INTO source_fts VALUES(?,?,?)',[
        ('s2','alpha','beta'),('s1','alpha','beta'),('hidden','beta','alpha')])
    return db


def test_rank_keeps_scope_order_limit_and_bounded_content_free_diagnostics(events):
    with closing(database()) as db:
        expected=[row[0] for row in db.execute(
            'SELECT source_id FROM source_fts WHERE source_fts MATCH ? '
            'ORDER BY bm25(source_fts,0,10.0,1.0),source_id',('"alpha"',))]
        ranked=index()
        assert ranked.rank(db,['alpha'],{'s1','s2'})==[s for s in expected if s!='hidden']
        timings=[e for e in events if e['event']=='fulltext.sql.timings'][-1]
        assert timings['fetched_count']==3 and timings['selected_count']==2
        assert timings['scope_rejected_count']==1 and timings['sql_status']=='completed'
        assert timings['active_searches_at_finish']==0
        assert timings['active_searches_peak']==1
        assert len(timings['slowest_batches'])<=5
        assert all(timings[key]>=0 for key in ('sql_fetch_cpu_ms','thread_cpu_ms','thread_non_cpu_ms'))
        assert ranked.rank(db,['alpha'],{'s1','s2'},1)==[s for s in expected if s!='hidden'][:1]
        assert 'alpha' not in json.dumps(events)  # no query or source terms in telemetry


def test_deadline_interrupt_propagates_and_does_not_leak_active_search(events):
    with closing(database()) as db:
        db.set_progress_handler(lambda:1,1)
        with pytest.raises(sqlite3.OperationalError,match='interrupted'):
            index().rank(db,['alpha'])
        failed=[e for e in events if e['event']=='fulltext.sql.timings'][-1]
        assert failed['sql_status']=='failed' and failed['error_type']=='OperationalError'
        assert failed['active_searches_at_finish']==0
        db.set_progress_handler(None,0)
        assert len(index().rank(db,['alpha']))==3
        assert [e for e in events if e['event']=='fulltext.sql.started'][-1]['active_searches_at_start']==1


def test_search_overlap_is_counted_per_process_and_released(events):
    entered=threading.Barrier(2)
    class Cursor:
        def fetchone(self):entered.wait(5);return ('s1',0.0)
        def fetchmany(self,size):return []
        def close(self):pass
    class DB:
        def execute(self,sql,args):return Cursor()
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures=[workers.submit(index().rank,DB(),['alpha']) for _ in range(2)]
        assert [f.result(timeout=10) for f in futures]==[['s1'],['s1']]
    timings=[e for e in events if e['event']=='fulltext.sql.timings']
    assert len({e['search_id'] for e in timings})==2
    assert all(e['active_searches_peak']==2 and e['concurrency_scope']=='process' for e in timings)
    assert not fulltext._ACTIVE_SEARCHES


def test_unavailable_proc_counters_are_absent_and_search_still_runs(events,monkeypatch):
    read=Path.read_text
    def unavailable(path,*args,**kwargs):
        if str(path).startswith('/proc/thread-self/'):raise PermissionError('synthetic unavailable')
        return read(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',unavailable)
    with closing(database()) as db:assert len(index().rank(db,['alpha']))==3
    timings=[e for e in events if e['event']=='fulltext.sql.timings'][-1]
    assert 'scheduler_wait_ms' not in timings and 'thread_read_bytes_delta' not in timings
    assert timings['sql_status']=='completed'


def test_connection_facts_getters_leave_settings_and_database_unchanged():
    with closing(database()) as db:
        before=db.total_changes
        db.execute('PRAGMA cache_size=-1234')
        facts=fulltext._connection_facts(db,index().manifest)
        assert facts['cache_size']==-1234 and facts['indexed_source_count']==3
        assert facts['uses_temp_sort'] is False
        assert db.total_changes==before
        assert db.execute('PRAGMA cache_size').fetchone()[0]==-1234
        assert len(index().rank(db,['alpha']))==3


def sources(db):
    db.execute('CREATE TABLE source(id TEXT PRIMARY KEY,json TEXT)')
    for sid in ('s1','s2'):
        value={'document_id':'d','unit_id':sid,'text':'synthetic private body','blocks':[]}
        db.execute('INSERT INTO source VALUES(?,?)',(sid,json.dumps(value)))
    return SourceMap(db)


def test_source_measurement_counts_reads_and_cache_without_changing_values():
    with closing(database()) as db:
        mapping=sources(db)
        with mapping.measure_loads() as stats:
            first=mapping['s1']
            assert mapping['s1'] is first
            assert mapping['s2']['unit_id']=='s2'
        assert stats['source_lookup_count']==3 and stats['source_sql_count']==2
        assert stats['source_cache_hits']==1 and stats['source_json_chars']>0
        assert stats['source_sql_execute_ms']>=0 and stats['source_json_decode_ms']>=0
        assert 'synthetic private body' not in json.dumps(stats)
        assert mapping._load_metrics is None
        with mapping.measure_loads() as warm:
            assert mapping['s1'] is first
        assert warm['source_sql_count']==0 and warm['source_cache_hits']==1


@pytest.mark.parametrize('bad',[None,'malformed json'])
def test_source_errors_stay_errors_and_measurement_is_released(bad):
    with closing(database()) as db:
        mapping=sources(db)
        if bad is not None:db.execute('INSERT INTO source VALUES(?,?)',('bad',bad))
        with pytest.raises((KeyError,json.JSONDecodeError)):
            with mapping.measure_loads() as stats:mapping['bad']
        assert stats['source_load_errors']==1 and mapping._load_metrics is None
        assert 'bad' not in mapping.cache and mapping['s1']['document_id']=='d'


def test_fulltext_location_diagnostics_keep_exact_total_scope_and_page(events,monkeypatch):
    monkeypatch.setattr(fulltext,'question_terms',lambda text:['alpha'])
    with closing(database()) as db:
        mapping=sources(db)
        tool=RelationsTools.__new__(RelationsTools)
        tool.context=SimpleNamespace(deadline=float('inf'))
        tool.matcher=SimpleNamespace(fulltext=index(),fulltext_db=db,
            sources={sid:{'document_id':'d','unit_id':sid} for sid in ('s1','s2')})
        tool.tools=SimpleNamespace(sources=mapping)
        tool.docs_bounds=lambda target:(['d'],None)
        tool.sources_in=lambda target:['s1','s2']
        tool.handle=lambda kind,value:'route'
        tool.page=lambda values,offset:(values[offset:offset+1],'next' if offset+1<len(values) else None)
        tool.node_card=lambda did,uid,source_id,route:{'id':source_id,'document_id':did}
        args={'mode':'fulltext','target':'R','query':'synthetic private question'}
        items,nxt,evidence,extra=tool.search(args,0)
        assert items==[{'id':'s1','document_id':'d'}] and nxt=='next' and evidence==[]
        assert extra['search_receipt']['total']==2 and extra['search_receipt']['total_status']=='exact'
        diagnostic=next(e for e in events if e['event']=='fulltext.location.timings')
        assert diagnostic['source_sql_count']==0 and diagnostic['location_count']==2
        assert diagnostic['source_lookup_count']==0 and not mapping.cache
        assert diagnostic['mapping_status']=='completed'
        assert not any(word in json.dumps(events) for word in ('synthetic private body','synthetic private question'))
        second=tool.search(args,1)
        assert second[0]==[{'id':'s2','document_id':'d'}] and second[1] is None
        assert [e for e in events if e['event']=='fulltext.location.timings'][-1]['source_sql_count']==0
