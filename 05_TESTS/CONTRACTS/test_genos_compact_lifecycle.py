"""Physical storage, completed-stage reuse and request journal contracts."""
from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import pytest
from semantic_runtime.contracts import sha
from semantic_runtime.storage import Store
from semantic_runtime.term_index import TermIndex
from semantic_runtime.fulltext import open_index
from lawrag.pipeline.term_generation import build_generation
from lawrag.pipeline.term_serving_bundle import verify_assets
from test_navigation_storage import original_source


@pytest.mark.parametrize('granularity',['article','unit'])
def test_compact_lifecycle_preserves_logical_source_navigation_and_search(tmp_path, term_glossary, granularity):
    source=original_source(tmp_path/'input.sqlite')
    before=sha(source)
    build_generation(source,term_glossary,tmp_path/'legacy',serving=True,fulltext_granularity=granularity)
    result=build_generation(source,term_glossary,tmp_path/'compact',serving=True,storage_profile='compact-v1',fulltext_granularity=granularity)
    old=tmp_path/'legacy/generation';new=tmp_path/'compact/generation'
    assert result['llm_calls']==0 and not result['activated']
    assert not (tmp_path/'compact/links/source.sqlite').exists()
    assert sha(source)==before
    with closing(Store(old)) as a, closing(Store(new)) as b:
        assert a.source('doc','0')==b.source('doc','0')
        assert a.section('doc','u')==b.section('doc','u')
        assert b.sources('doc',['0','0'])==[b.source('doc','0')]*2
        with pytest.raises(KeyError):b.sources('doc',['missing'])
        with closing(sqlite3.connect(old/'navigation/navigation.sqlite')) as x, closing(sqlite3.connect(new/'navigation/navigation.sqlite')) as y:
            for (table,) in x.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
                assert Counter(x.execute('SELECT * FROM '+table))==Counter(y.execute('SELECT * FROM '+table)),table
        index=TermIndex(new/'navigation',b)
        tools=index.tools(['doc'])
        try:assert tools.search(['fixture:day'],['doc'])
        finally:tools.db.close()
        ft=open_index(new/'fulltext',index.manifest)
        old_ft=open_index(old/'fulltext',TermIndex(old/'navigation',a).manifest)
        with closing(ft.connect()) as db, closing(old_ft.connect()) as old_db:
            for terms in (['영업'], ['은행'], ['자금'], ['Business']):
                assert ft.rank(db,terms)==old_ft.rank(old_db,terms)
    assert verify_assets(new)['verified']
    assert build_generation(source,term_glossary,tmp_path/'compact',serving=True,storage_profile='compact-v1',fulltext_granularity=granularity)==result


def test_compact_resume_preserves_completed_navigation(tmp_path,term_glossary,monkeypatch):
    from lawrag.pipeline import generation_build_steps as steps
    source=original_source(tmp_path/'input.sqlite');out=tmp_path/'compact'
    original=steps.fulltext.build
    def interrupt(*a,**k):raise RuntimeError('interrupted fulltext')
    monkeypatch.setattr(steps.fulltext,'build',interrupt)
    with pytest.raises(RuntimeError,match='interrupted'):
        build_generation(source,term_glossary,out,serving=True,storage_profile='compact-v1')
    partial=tmp_path/'.compact.building'
    digest=sha(partial/'generation/navigation/navigation.sqlite')
    monkeypatch.setattr(steps.fulltext,'build',original)
    def forbidden(*a,**k):raise AssertionError('completed navigation must not be rebuilt')
    monkeypatch.setattr(steps.term_index,'compile_index',forbidden)
    result=build_generation(source,term_glossary,out,serving=True,storage_profile='compact-v1')
    assert sha(out/'generation/navigation/navigation.sqlite')==digest
    assert all(s['reused'] for s in result['stages'] if s['stage']!='fulltext')
    assert not result['stages'][-1]['reused']


def test_source_projection_preserves_json_and_metadata(tmp_path):
    from semantic_runtime import storage,compact_storage
    source=original_source(tmp_path/'input.sqlite')
    with sqlite3.connect(source) as db:
        db.execute('UPDATE document SET json=?',(json.dumps({'nodes':[{'id':'u'}],'blocks':[{'text':'large'}],'ladder':{'a':1},'document_metadata':{'acl':'team'}}),))
        db.execute('UPDATE source_block SET json=?',(json.dumps({'text':'영업일 영업일 Business Day 자금지원','special':['x']}),))
    manifest=storage.publish(None,source,tmp_path/'generation')
    value=compact_storage.source(tmp_path/'generation',tmp_path/'audit',manifest)
    (tmp_path/'generation/manifest.json').write_text(json.dumps(value))
    with closing(Store(tmp_path/'generation')) as store, closing(sqlite3.connect(source)) as raw:
        assert json.loads(store.source('doc','0')['json'])==json.loads(raw.execute('SELECT json FROM source_block').fetchone()[0])
        assert json.loads(store.db.execute('SELECT json FROM document').fetchone()[0])=={'ladder':{'a':1},'document_metadata':{'acl':'team'}}
    compact_storage.verify_source_audit(tmp_path/'audit',value['source_storage'],value['store_sha256'])


def test_navigation_journal_batches_without_holding_read_lock(tmp_path):
    from semantic_runtime.legal_agent.repository import WorkRepository
    repo=WorkRepository.__new__(WorkRepository)
    repo.db=sqlite3.connect(tmp_path/'journal.sqlite',isolation_level=None);repo.db.row_factory=sqlite3.Row
    repo.db.executescript('CREATE TABLE navigation_handle(handle PRIMARY KEY,kind,identity_json,binding_hash);CREATE TABLE navigation_cursor(cursor PRIMARY KEY,operation_hash,position_json,binding_hash);')
    statements=[];repo.db.set_trace_callback(statements.append)
    try:
        with repo.navigation_batch():
            for i in range(80):
                ident=repo.navigation_handle('U',json.dumps({'unit_id':str(i)}),'binding')
                assert ident=='U'+str(i+1)
                assert repo.navigation_row('navigation_handle',ident)['binding_hash']=='binding'
            assert not repo.db.in_transaction
            assert repo.db.execute('SELECT count(*) FROM navigation_handle').fetchone()[0]==0
            assert repo.navigation_handle('U',json.dumps({'unit_id':'0'}),'binding')=='U1'
        assert sum(s=='COMMIT' for s in statements)==1
        assert repo.db.execute('SELECT count(*) FROM navigation_handle').fetchone()[0]==80
        with pytest.raises(RuntimeError):
            with repo.navigation_batch():
                repo.navigation_handle('U','{"unit_id":"cancelled"}','binding')
                raise RuntimeError('interrupted')
        assert repo.db.execute('SELECT count(*) FROM navigation_handle').fetchone()[0]==80
    finally:repo.close()


def test_compact_glossary_runtime_requires_prebuilt_cache(tmp_path,term_glossary):
    from lawrag.pipeline import glossary_serving,glossary_knowledge
    from semantic_runtime.full_glossary import Glossary
    bundle=tmp_path/'projected';dictionary=term_glossary/'dictionary.sqlite'
    glossary_serving.project(glossary_knowledge.selected_for(term_glossary),dictionary,bundle)
    with pytest.raises(ValueError,match='offline'):
        Glossary(bundle,dictionary,tmp_path/'missing-cache',manifest_sha256=sha(bundle/'manifest.json'))
