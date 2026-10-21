"""Synthetic filename visibility, existing SQLite, navigation and API contracts."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3

import pytest

from lawrag.pipeline.search_selection import plan, activate, rollback, encode
from semantic_runtime.contracts import sha, write
from semantic_runtime.search_selection import selection_path, Selection
from semantic_runtime.storage import Store


def metadata_generation(tmp_path, rows):
    generation = tmp_path/'generation'; generation.mkdir()
    with closing(sqlite3.connect(generation/'store.sqlite')) as db:
        db.executescript('CREATE TABLE document(document_id TEXT,name TEXT,source_artifact_sha256 TEXT,json TEXT);'
                        'CREATE TABLE source_unit(document_id TEXT,unit_id TEXT);'
                        'CREATE TABLE source_block(document_id TEXT,block_id TEXT,text TEXT);')
        for did, path, extra in rows:
            meta = {'source_category': 'internal', 'relative_path': path, **extra}
            db.execute('INSERT INTO document VALUES (?,?,?,?)',
                       (did,path,did*64,json.dumps({'document_metadata': meta})))
            db.execute('INSERT INTO source_block VALUES (?,?,?)', (did, '1', 'synthetic '+did))
        db.commit()
    write(generation/'manifest.json', {'schema_version': 'term-source-generation-v1',
        'generation_id': generation.name, 'store_sha256': sha(generation/'store.sqlite'),
        'scope': {'document_version_ids': [r[0] for r in rows]}})
    return generation


def test_apply_idempotent_invalidation_and_rollback_preserve_sqlite(tmp_path):
    g = metadata_generation(tmp_path, [('a','internal/규정(20190710).docx',{}),
                                      ('b','internal/규정(20220331).docx',{})])
    before = sha(g/'store.sqlite'); manifest = sha(g/'manifest.json')
    old = Store(g, verify=False)
    p = plan(g); assert [r['document_id'] for r in p['excluded']] == ['a']
    result = activate(p)
    assert activate(p)['state'] == 'ALREADY_APPLIED'
    with pytest.raises(ValueError, match='restart'): old.check_unchanged()
    old.close()
    with closing(Store(g)) as s:
        assert s.db.execute('SELECT document_id FROM document').fetchall()[0][0] == 'b'
        assert s.db.execute('SELECT document_id FROM source_block').fetchall()[0][0] == 'b'
        with pytest.raises(KeyError): s.source('a','1')
        with pytest.raises(sqlite3.DatabaseError): s.db.execute('DELETE FROM main.document')
        with pytest.raises(sqlite3.DatabaseError): s.db.execute('PRAGMA query_only=OFF')
    assert sha(g/'store.sqlite') == before and sha(g/'manifest.json') == manifest
    rollback(result['receipt']); rollback(result['receipt'])
    with closing(Store(g, verify=False)) as s:
        assert s.db.execute('SELECT count(*) FROM document').fetchone()[0] == 2


@pytest.mark.parametrize('other,expected', [
    (('c','internal/다른폴더/규정(20250101).docx',{}), ['a']),
    (('c','external/규정(20250101).docx',{'source_category':'external'}), ['a']),
    (('c','internal/규정.docx',{}), []),
    (('c','internal/규정(20220230).docx',{}), []),
    (('c','internal/규정(220331).docx',{}), []),
    (('c','internal/규정(20220331)(2).docx',{}), []),
])
def test_metadata_ambiguities_are_preserved(tmp_path, other, expected):
    g = metadata_generation(tmp_path, [('a','internal/규정(20190710).docx',{}),
                                      ('b','internal/규정(20220331).docx',{}), other])
    assert [r['document_id'] for r in plan(g)['excluded']] == expected


def test_shared_alias_current_elsewhere_is_not_deleted(tmp_path):
    g = metadata_generation(tmp_path, [
        ('a','internal/규정(20190710).docx',{'aliases':[{'source_category':'internal','relative_path':'internal/다른폴더/규정(20190710).docx'}]}),
        ('b','internal/규정(20220331).docx',{})])
    p = plan(g)
    assert not p['excluded']
    assert p['warnings'][0]['reason'] == 'shared_document_still_current_or_ambiguous'


def test_changed_plan_binding_and_rollback_are_rejected(tmp_path):
    g = metadata_generation(tmp_path, [('a','internal/규정(20190710).docx',{}),
                                      ('b','internal/규정(20220331).docx',{})])
    p = plan(g)
    p['excluded'][0]['source_artifact_sha256'] = 'bad'
    with pytest.raises(ValueError, match='plan changed'): activate(p)
    p = plan(g); result = activate(p)
    value = json.loads(selection_path(g).read_text()); value['store_sha256']='bad'
    selection_path(g).write_bytes(encode(value))
    with pytest.raises(ValueError, match='binding'): Store(g, verify=False)
    with pytest.raises(ValueError, match='rollback refused'): rollback(result['receipt'])


def test_navigation_views_hide_old_sources_definitions_and_reference_candidates(tmp_path):
    g = metadata_generation(tmp_path, [('a','internal/규정(20190710).docx',{}),
                                      ('b','internal/규정(20220331).docx',{})])
    activate(plan(g)); s = Selection(g, json.loads((g/'manifest.json').read_text()))
    db = sqlite3.connect(':memory:')
    db.executescript('''
        CREATE TABLE source(id TEXT,document_id TEXT,json TEXT);
        INSERT INTO source VALUES ('old','a','{}'),('new','b','{}');
        CREATE TABLE definition(id TEXT,document_id TEXT,json TEXT);
        INSERT INTO definition VALUES ('d1','a','{}'),('d2','b','{}');
        CREATE TABLE reference(id TEXT,document_id TEXT,json TEXT);
        INSERT INTO reference VALUES ('oldref','a','{}'),('touch','b','{}'),('candidate','b','{}'),('keep','b','{}');
        CREATE TABLE reference_end(reference_id TEXT,source_id TEXT);
        INSERT INTO reference_end VALUES ('oldref','old'),('touch','old'),('touch','new'),('candidate','new'),('keep','new');
        CREATE TABLE reference_candidate(reference_id TEXT,source_id TEXT);
        INSERT INTO reference_candidate VALUES ('candidate','old');
    ''')
    s.bind(db, navigation=True)
    assert db.execute('SELECT id FROM source').fetchall() == [('new',)]
    assert db.execute('SELECT id FROM definition').fetchall() == [('d2',)]
    assert db.execute('SELECT id FROM reference').fetchall() == [('keep',)]
    db.close()


@pytest.mark.parametrize('mode', ['legacy', 'compact-v2'])
def test_existing_database_search_and_actual_api(tmp_path, monkeypatch, term_glossary, mode):
    from test_latest_internal_versions import docx
    from lawrag.pipeline import genos_corpus, genos_stages, document_release
    from lawrag.pipeline.term_generation import build_generation
    from semantic_runtime.term_index import TermIndex
    from fastapi.testclient import TestClient
    from test_legal_agent_v5 import app_for
    monkeypatch.setenv('STRUCTURE_RECIPE_VLM','off')
    raw = tmp_path/'RAW'
    old = docx(raw/'internal/모의규정(20190710).docx', '영업일은 은행이 영업하는 날을 말한다. 폐기예시옛본문')
    new = docx(raw/'internal/모의규정(20220331).docx', '영업일은 은행이 영업하는 날을 말한다. 최신예시본문')
    inventory, _ = genos_corpus.collect(raw, only_internal=True, skip_invalid=True, emit=lambda _: None)
    stores = []
    for row in inventory['files']:
        folder, _ = genos_stages.structure(row, inventory, tmp_path, {'synthetic':'no-model'},30,lambda _:None)
        stores.append(folder/'source.sqlite')
    # Existing generations include both versions; updating them must not rebuild.
    merged = document_release.merge_sources(stores, tmp_path/'merged')
    settings = {'storage_profile':'compact-v2','fulltext_granularity':'unit','audit_profile':'factorized-v1'} if mode=='compact-v2' else {}
    build_generation(merged, term_glossary, tmp_path/'built', serving=True, **settings)
    g = tmp_path/'built/generation'; before = {p:sha(p) for p in g.rglob('*') if p.is_file()}
    oldid, newid = sha(old)[:16], sha(new)[:16]
    with closing(Store(g)) as store:
        assert store.db.execute('SELECT count(*) FROM document').fetchone()[0] == 2
    value = plan(g)
    assert [r['document_id'] for r in value['excluded']] == [oldid]
    receipt = activate(value)
    with closing(Store(g)) as store:
        index = TermIndex(g/'navigation', store)
        with pytest.raises(ValueError, match='excluded'): index.tools([oldid,newid])
        tools = index.tools([newid])
        try:
            found = tools.search(['fixture:day'],[newid])
            assert found and all(tools.sources[x['id']]['document_id']==newid for x in found)
            assert all(v['document_id']==newid for v in tools.sources.values())
            from semantic_runtime.fulltext import open_index
            ft = open_index(g/'fulltext', index.manifest)
            with closing(ft.connect()) as db:
                ranked = ft.rank(db, ['은행'], allowed=set(tools.sources))
                assert ranked and all(tools.sources[sid]['document_id']==newid for sid in ranked)
        finally: tools.db.close()
    def verify_api(app):
      with TestClient(app) as client:
        listed=client.get('/v1/rag/documents')
        assert listed.status_code==200 and {d['id'] for d in listed.json()['documents']}=={newid}
        found=client.get('/v1/rag/search',params={'q':'모의규정(20190710) 모의규정(20220331) 제1조'})
        assert found.status_code==200 and oldid not in found.text and newid in found.text
        assert client.get('/v1/rag/search',params={'q':'영업일','doc_id':oldid}).status_code==422
        assert client.get('/v1/rag/document/read',params={'doc_id':oldid}).status_code==404
        assert client.get('/v1/rag/document/read',params={'doc_id':newid}).status_code==200
        assert oldid not in client.get('/v1/rag/scopes').text
        assert client.get('/health').json()['search_selection']['excluded_documents']==1
    verify_api(app_for(tmp_path/'api', g))
    from semantic_runtime.app import create_app
    from test_bounded_source_main import settings
    from test_unified_legal_agent import ScriptedTransport
    from test_legal_agent_double_harness import ROOT
    verify_api(create_app(tmp_path/'api-v6',g,contracts_root=ROOT,provider=object(),
        implementation='legal-agent-unified-v6',legal_agent_profile=settings(),
        legal_agent_transport=ScriptedTransport(),runtime_root=tmp_path/'api-v6/runtime'))
    assert before=={p:sha(p) for p in g.rglob('*') if p.is_file()}
    rollback(receipt['receipt'])
    with closing(Store(g)) as store:
        assert store.db.execute('SELECT count(*) FROM document').fetchone()[0]==2
