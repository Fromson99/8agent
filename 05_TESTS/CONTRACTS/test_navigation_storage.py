"""Serving/build-audit separation preserves retrieval and fails closed on drift."""
from collections import Counter
from contextlib import closing
import json
import os
import shutil
import sqlite3

import pytest

from semantic_runtime.contracts import sha
from semantic_runtime import navigation_storage as storage
from semantic_runtime.storage import Store
from semantic_runtime.term_index import TermIndex
from lawrag.pipeline.term_generation import build_generation
from lawrag.pipeline.term_serving_bundle import verify_assets


def original_source(path):
    with sqlite3.connect(path) as db:
        db.executescript('''
        CREATE TABLE document(document_id TEXT PRIMARY KEY,name TEXT,source_artifact_sha256 TEXT,json TEXT);
        CREATE TABLE source_unit(document_id TEXT,unit_id TEXT,parent_id TEXT,json TEXT);
        CREATE TABLE source_block(document_id TEXT,block_id TEXT,unit_id TEXT,text TEXT,source_artifact_sha256 TEXT,json TEXT);
        INSERT INTO document VALUES ('doc','가상법','fixture-hash','{}');
        ''')
        unit={'family':'kr_article','surface':'제1조','title':'영업일','span':[0,1]}
        db.execute('INSERT INTO source_unit VALUES (?,?,?,?)',('doc','u',None,json.dumps(unit)))
        db.execute('INSERT INTO source_block VALUES (?,?,?,?,?,?)',
                   ('doc','0','u','영업일 영업일 Business Day 자금지원','fixture-hash','{}'))
    return path


def make_monolithic(tmp_path, term_glossary):
    built=tmp_path/'parent'
    build_generation(original_source(tmp_path/'input.sqlite'),term_glossary,built,serving=True)
    nav=built/'generation/navigation'
    shutil.copyfile(built/'audit/navigation/navigation.sqlite',nav/'navigation.sqlite')
    m=json.loads((nav/'manifest.json').read_text());m.pop('storage')
    m['index_sha256']=sha(nav/'navigation.sqlite')
    (nav/'manifest.json').write_text(json.dumps(m))
    g=built/'generation';gm=json.loads((g/'manifest.json').read_text())
    gm['navigation']['manifest_sha256']=sha(nav/'manifest.json')
    ft=g/'fulltext/manifest.json';fm=json.loads(ft.read_text())
    fm['navigation_index_sha256']=m['index_sha256'];ft.write_text(json.dumps(fm))
    gm['fulltext'].update(manifest_sha256=sha(ft),navigation_index_sha256=m['index_sha256'])
    (g/'manifest.json').write_text(json.dumps(gm))
    verify_assets(g)
    return g


def test_pipeline_emits_audit_and_resume_rejects_missing_evidence(tmp_path, term_glossary):
    source=original_source(tmp_path/'source.sqlite');built=tmp_path/'built'
    result=build_generation(source,term_glossary,built,serving=True)
    nav=built/'generation/navigation'
    audit=built/'audit/navigation/navigation.sqlite'
    with closing(sqlite3.connect(nav/'navigation.sqlite')) as db:
        assert not storage._tables(db).intersection(storage.AUDIT_TABLES)
        assert db.execute('SELECT count(*) FROM occurrence').fetchone()[0]>0
    with closing(sqlite3.connect(audit)) as db:
        assert set(storage.AUDIT_TABLES)<=storage._tables(db)
        assert db.execute('SELECT count(*) FROM occurrence_evidence').fetchone()[0]>0
    assert build_generation(source,term_glossary,built,serving=True)==result
    with audit.open('ab') as stream:stream.write(b'drift')
    with pytest.raises(ValueError,match='audit snapshot'):
        build_generation(source,term_glossary,built,serving=True)


def test_migration_preserves_all_runtime_rows_and_fulltext(tmp_path, term_glossary):
    parent=make_monolithic(tmp_path,term_glossary);before=sha(parent/'manifest.json')
    result=storage.compact_generation(parent,tmp_path/'compact')
    new=tmp_path/'compact/generation'
    assert storage.compact_generation(parent,tmp_path/'compact')==result
    assert before==sha(parent/'manifest.json')
    assert sha(parent/'fulltext/fulltext.sqlite')==sha(new/'fulltext/fulltext.sqlite')
    assert sha(parent/'store.sqlite')==sha(new/'store.sqlite')
    assert sha(parent/'navigation/navigation.sqlite')==sha(tmp_path/'compact/audit/navigation/navigation.sqlite')
    with closing(sqlite3.connect(parent/'navigation/navigation.sqlite')) as old, closing(sqlite3.connect(new/'navigation/navigation.sqlite')) as compact:
        for table in storage._tables(compact):
            assert Counter(old.execute(f'SELECT * FROM "{table}"'))==Counter(compact.execute(f'SELECT * FROM "{table}"'))
    for generation in (parent,new):
        with closing(Store(generation)) as store:
            tools=TermIndex(generation/'navigation',store).tools(['doc'])
            try:
                assert tools.search(['fixture:day'],['doc'])
                assert tools.search_labels(['Business Day'],['doc'])
                with pytest.raises(ValueError,match='scope'):
                    tools.search(['fixture:day'],['private'])
            finally:tools.db.close()


def test_serving_does_not_require_build_audit(tmp_path, term_glossary):
    parent=make_monolithic(tmp_path,term_glossary)
    storage.compact_generation(parent,tmp_path/'compact')
    shutil.move(tmp_path/'compact/audit',tmp_path/'offline-audit')
    assert verify_assets(tmp_path/'compact/generation')['verified']
    with pytest.raises(OSError):storage.verify_build(tmp_path/'compact')


def test_refuses_shared_navigation_or_output_inside_parent(tmp_path, term_glossary):
    parent=make_monolithic(tmp_path,term_glossary)
    with pytest.raises(ValueError,match='separate'):
        storage.compact_generation(parent,parent/'derived')
    linked=tmp_path/'serving/navigation.sqlite';linked.parent.mkdir()
    os.link(parent/'navigation/navigation.sqlite',linked)
    before=sha(linked)
    with pytest.raises(ValueError,match='hardlinked'):
        storage.separate_navigation(linked,tmp_path/'audit')
    assert sha(linked)==before


def test_derivation_resume_rejects_compact_db_tampering(tmp_path, term_glossary):
    parent=make_monolithic(tmp_path,term_glossary)
    storage.compact_generation(parent,tmp_path/'compact')
    with (tmp_path/'compact/generation/navigation/navigation.sqlite').open('ab') as stream:
        stream.write(b'drift')
    with pytest.raises(ValueError,match='navigation database'):
        storage.compact_generation(parent,tmp_path/'compact')


def test_explicit_legacy_fulltext_binding_preserves_payload_and_parent(tmp_path, term_glossary):
    from lawrag.pipeline.document_release import rebind_fulltext, verify_fulltext_binding
    parent = make_monolithic(tmp_path, term_glossary)
    manifest = json.loads((parent / 'manifest.json').read_text())
    binding = manifest.pop('fulltext')
    (parent / 'manifest.json').write_text(json.dumps(manifest))
    storage.compact_generation(parent, tmp_path / 'compact')
    original = sha(tmp_path / 'compact/generation/fulltext/manifest.json')
    result = rebind_fulltext(tmp_path / 'compact', binding, tmp_path / 'bound')
    value, index = verify_fulltext_binding(tmp_path / 'bound', result['fulltext_binding'])
    assert value['navigation_index_sha256'] == index['index_sha256']
    assert sha(tmp_path / 'compact/generation/fulltext/manifest.json') == original
    assert sha(tmp_path / 'bound/generation/fulltext/fulltext.sqlite') == sha(parent / 'fulltext/fulltext.sqlite')
    assert rebind_fulltext(tmp_path / 'compact', binding, tmp_path / 'bound') == result
    assert storage.verify_build(tmp_path / 'bound') == result
    with (tmp_path / 'bound/generation/fulltext/manifest.json').open('a') as stream:
        stream.write(' ')
    with pytest.raises(ValueError, match='Legacy fulltext manifest changed'):
        rebind_fulltext(tmp_path / 'compact', binding, tmp_path / 'bound')
