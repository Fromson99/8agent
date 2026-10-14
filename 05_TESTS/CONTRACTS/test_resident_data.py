"""Whole-dataset cache contracts, including arbitrary queries and readonly mirrors."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import threading
import pytest
from semantic_runtime import resident_data as rd
from test_unit_fulltext_adaptive_read import tree  # noqa: F401


@pytest.fixture
def data(tmp_path):
    path=tmp_path/'source.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE VIRTUAL TABLE text USING fts5(body)')
        db.executemany('INSERT INTO text(body) VALUES(?)', [('alpha beta',),('gamma delta',),('epsilon',)])
    return path,hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize('mode',['memory','local'])
def test_all_queries_share_whole_dataset_after_first_connection_closes(data,tmp_path,mode,monkeypatch):
    path,pin=data; monkeypatch.setattr(rd,'available_memory',lambda: 8*1024**3)
    pool=rd.ResidentPool(mode=mode,max_memory_bytes=1024**2,directory=tmp_path/'cache')
    try:
        with closing(pool.connect(path,expected=pin)) as first:
            assert first.execute("SELECT body FROM text WHERE text MATCH 'alpha'").fetchall()==[('alpha beta',)]
        def must_not_reload(*args,**kwargs): pytest.fail('whole dataset reloaded for another query')
        monkeypatch.setattr(pool,'_build',must_not_reload)
        with closing(pool.connect(path,expected=pin)) as second:
            assert second.execute("SELECT body FROM text WHERE text MATCH 'gamma'").fetchall()==[('gamma delta',)]
            assert second.execute("SELECT body FROM text WHERE text MATCH 'epsilon'").fetchall()==[('epsilon',)]
            assert second.execute('SELECT count(*) FROM text').fetchone()[0]==3
            assert second.execute('PRAGMA database_list').fetchone()[2]!=str(path)
            with pytest.raises(sqlite3.DatabaseError): second.execute('PRAGMA query_only=OFF')
            with pytest.raises(sqlite3.DatabaseError): second.execute("INSERT INTO text VALUES('bad')")
        assert hashlib.sha256(path.read_bytes()).hexdigest()==pin
        assert len(pool.entries)==1
    finally: pool.close()
    assert pool.memory_bytes==0 and pool.local_bytes==0
    assert not list((tmp_path/'cache').glob('8-agent-resident-*'))


def test_hash_mismatch_and_source_change_are_never_served(data,tmp_path,monkeypatch):
    path,pin=data; pool=rd.ResidentPool(mode='local',directory=tmp_path/'cache')
    try:
        with pytest.raises(ValueError,match='hash mismatch'):pool.connect(path,expected='0'*64)
        assert not pool.entries and not pool.pending
        with closing(pool.connect(path,expected=pin)): pass
        with path.open('ab') as file:file.write(b'changed')
        with pytest.raises(ValueError,match='hash mismatch'):pool.connect(path,expected=pin)
        assert len(pool.entries)==1
    finally:pool.close()


def test_concurrent_first_load_is_single_flight(data,tmp_path):
    path,pin=data;pool=rd.ResidentPool(mode='local',directory=tmp_path/'cache')
    original=pool._build;started=threading.Event();release=threading.Event();calls=[]
    def build(*args):
        calls.append(1);started.set();assert release.wait(5);return original(*args)
    pool._build=build
    def read():
        with closing(pool.connect(path,expected=pin)) as db:return db.execute('SELECT count(*) FROM text').fetchone()[0]
    try:
        with ThreadPoolExecutor(max_workers=3) as threads:
            futures=[threads.submit(read) for _ in range(3)]
            assert started.wait(5);release.set()
            assert [f.result(5) for f in futures]==[3,3,3]
        assert len(calls)==1
    finally:pool.close()


def test_memory_limit_does_not_truncate_dataset_and_auto_retains_local(data,tmp_path,monkeypatch):
    path,pin=data;monkeypatch.setattr(rd,'available_memory',lambda:8*1024**3)
    strict=rd.ResidentPool(mode='memory',max_memory_bytes=1)
    with pytest.raises(MemoryError,match='whole dataset'):strict.connect(path,expected=pin)
    assert not strict.entries and strict.memory_bytes==0 and not strict.pending
    auto=rd.ResidentPool(mode='auto',max_memory_bytes=1,directory=tmp_path/'cache')
    try:
        with closing(auto.connect(path,expected=pin)) as db:assert db.execute('SELECT count(*) FROM text').fetchone()[0]==3
        assert next(iter(auto.entries.values()))['storage']=='local'
        assert auto.local_bytes==path.stat().st_size
    finally:auto.close()


def test_failed_load_does_not_leave_local_copy(data,tmp_path,monkeypatch):
    path,pin=data;pool=rd.ResidentPool(mode='local',directory=tmp_path/'cache')
    class Deadline(Exception):pass
    checks=[0]
    def remaining():
        checks[0]+=1
        if checks[0]>1:raise Deadline()
    try:
        with pytest.raises(Deadline):pool.connect(path,expected=pin,remaining=remaining)
        assert not pool.entries and not pool.pending
        assert not list(pool.local_root.glob('*.sqlite'))
    finally:pool.close()


def test_runtime_connections_use_shared_resident_pool_for_source_navigation_and_fts(tree,monkeypatch,tmp_path):
    from semantic_runtime.storage import Store
    from semantic_runtime.term_index import TermIndex
    from semantic_runtime.navigation_agent import glossary_assets
    gen,idx=tree;pool=rd.ResidentPool(mode='local',directory=tmp_path/'cache')
    monkeypatch.setattr(rd,'POOL',pool)
    try:
        with closing(Store(gen)) as store:
            nav=TermIndex(gen/'navigation',store);tools=nav.tools(['d']);glossary=glossary_assets(gen,{})
            try:
                with closing(idx.connect()) as db:
                    assert idx.law_groups_page(db,['승인'])['total']==1
                    assert idx.law_groups_page(db,['원문'])['total']==1
                for db in [store.db,tools.db,*glossary.dbs.values()]:
                    assert '/8-agent-resident-' in db.execute('PRAGMA database_list').fetchone()[2]
                assert len(pool.entries)==3+len(glossary.dbs)
            finally:tools.db.close();glossary.close()
    finally:pool.close()
