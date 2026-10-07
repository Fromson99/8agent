"""Read-only generation inspection, compact views, failures, and delivery."""
from contextlib import closing
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess

import pytest

from semantic_runtime.storage import publish
from semantic_runtime.compact_storage import source as compact_source
from semantic_runtime.reference_build import shared_reference_schema
from semantic_runtime.navigation_build import occurrence_schema
from semantic_runtime.contracts import digest, sha

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / '08_DEPLOYMENT/GENOS/diagnostics/data_audit_20261006_r2'
SCRIPT = PACKAGE / 'GENOS_DATA_AUDIT_20261006_R2.py'
spec = importlib.util.spec_from_file_location('genos_data_audit_r2', SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def write(path, value):
    # Test fixtures are deliberately mutated to exercise corruption detection.
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


def fixture(tmp_path, compact=True, glossary=False, term_glossary=None):
    base = tmp_path / 'built'
    base.mkdir()
    raw = tmp_path / 'source.sqlite'
    texts = {'d1': ['제1조(정의) 영업일', '① 가상법 제2조를 준용한다.'],
             'd2': ['제2조(대상) 영업일', '① 은행이 영업하는 날을 말한다.']}
    with sqlite3.connect(raw) as db:
        db.executescript('''
        CREATE TABLE document(document_id TEXT PRIMARY KEY,name TEXT,source_artifact_sha256 TEXT,json TEXT);
        CREATE TABLE source_unit(document_id TEXT,unit_id TEXT,parent_id TEXT,json TEXT);
        CREATE TABLE source_block(document_id TEXT,block_id TEXT,unit_id TEXT,text TEXT,source_artifact_sha256 TEXT,json TEXT);
        ''')
        for did, parts in texts.items():
            name = '모의법 ' + did + ' <script>alert(1)</script>'
            db.execute('INSERT INTO document VALUES(?,?,?,?)', (did, name, 'raw-hash', '{}'))
            for uid, parent, span, family, surface in [('a', None, [0, 2], 'kr_article', '제1조'), ('p', 'a', [1, 2], 'kr_paragraph', '①')]:
                value = dict(span=span, family=family, surface=surface)
                db.execute('INSERT INTO source_unit VALUES(?,?,?,?)', (did, uid, parent, json.dumps(value)))
            for i, text in enumerate(parts):
                db.execute('INSERT INTO source_block VALUES(?,?,?,?,?,?)', (did, str(i), 'a' if i == 0 else 'p', text, 'raw-hash', json.dumps({'text': text})))
    gen = base / 'generation'
    sm = publish(ROOT, raw, gen)
    if compact:
        sm = compact_source(gen, base / 'audit/source', sm)
    write(gen / 'manifest.json', sm)
    nav = gen / 'navigation'
    nav.mkdir()
    with sqlite3.connect(nav / 'navigation.sqlite') as db:
        db.executescript('''
        CREATE TABLE term(id TEXT PRIMARY KEY,json TEXT);
        CREATE TABLE edge(id TEXT PRIMARY KEY,json TEXT);
        CREATE TABLE source(id TEXT PRIMARY KEY,document_id TEXT,article TEXT,json TEXT);
        CREATE INDEX source_document ON source(document_id);
        CREATE TABLE occurrence(term_id TEXT,source_id TEXT,PRIMARY KEY(term_id,source_id));
        CREATE TABLE definition(id TEXT PRIMARY KEY,document_id TEXT,json TEXT);
        CREATE TABLE reference(id TEXT PRIMARY KEY,document_id TEXT,json TEXT);
        CREATE TABLE reference_end(source_id TEXT,reference_id TEXT,PRIMARY KEY(source_id,reference_id));
        CREATE TABLE reference_target(reference_id TEXT,ordinal INTEGER,source_id TEXT,unit_id TEXT,unit_path TEXT,block_ids TEXT,target_level TEXT);
        CREATE TABLE reference_candidate(reference_id TEXT,candidate_id TEXT,ordinal INTEGER,source_id TEXT,unit_id TEXT,unit_path TEXT,block_ids TEXT,target_level TEXT,basis TEXT,json TEXT);
        CREATE TABLE reference_candidate_end(source_id TEXT,reference_id TEXT,candidate_id TEXT);
        ''')
        if compact:
            shared_reference_schema(db)
            occurrence_schema(db)
        db.execute('INSERT INTO term VALUES(?,?)', ('t', json.dumps({'id': 't', 'label': '영업일'})))
        for did, parts in texts.items():
            source = {'id': 's' + did, 'document_id': did, 'unit_id': 'a', 'document_name': did,
                      'heading': '제1조', 'blocks': [{'block_id': str(i), 'text': t} for i, t in enumerate(parts)],
                      'text': '\n'.join(parts), 'text_sha256': audit.text_hash('\n'.join(parts))}
            db.execute('INSERT INTO source VALUES(?,?,?,?)', (source['id'], did, '제1조', json.dumps(source)))
            db.execute('INSERT INTO occurrence VALUES(?,?)', ('t', source['id']))
        text = texts['d1'][1]
        target = {'source_id': 'sd2', 'unit_id': 'p', 'unit_path': ['①'], 'block_ids': ['1'], 'target_level': 'provision'}
        ref = {'id': 'r', 'document_id': 'd1', 'source_id': 'sd1', 'block_id': '1', 'source_text': text,
               'source_text_sha256': audit.text_hash(text), 'mention_start': 6, 'mention_end': 9,
               'mention_text': text[6:9], 'mention_text_sha256': audit.text_hash(text[6:9]),
               'targets': [target], 'target_source_ids': ['sd2'], 'coverage_state': 'COMPLETE'}
        db.execute('INSERT INTO reference VALUES(?,?,?)', ('r', 'd1', json.dumps(ref)))
        db.executemany('INSERT INTO reference_end VALUES(?,?)', [('sd1', 'r'), ('sd2', 'r')])
        db.execute('INSERT INTO reference_target VALUES(?,?,?,?,?,?,?)', ('r', 0, 'sd2', 'p', '["①"]', '["1"]', 'provision'))
        definition = {'id': 'def', 'source_id': 'sd2', 'block_id': '1', 'source_text': texts['d2'][1],
                      'source_text_sha256': audit.text_hash(texts['d2'][1]), 'term_ids': ['t']}
        db.execute('INSERT INTO definition VALUES(?,?,?)', ('def', 'd2', json.dumps(definition)))
    nm = {'schema_version': 'term-navigation-index-v7' if compact else 'term-navigation-index-v4',
          'generation_id': sm['generation_id'], 'source_store_sha256': sm['store_sha256'],
          'source_manifest_sha256': digest(sm), 'index_sha256': sha(nav / 'navigation.sqlite'),
          'counts': dict(term=1, edge=0, source=2, occurrence=2, definition=1, reference=1)}
    write(nav / 'manifest.json', nm)
    sm['navigation'] = {'path': 'navigation', 'manifest_sha256': sha(nav / 'manifest.json')}
    ft = gen / 'fulltext'; ft.mkdir()
    with sqlite3.connect(ft / 'units.sqlite') as db:
        db.executescript('''CREATE TABLE unit(key TEXT PRIMARY KEY,source_id TEXT,document_id TEXT,json TEXT);
        CREATE VIRTUAL TABLE unit_fts USING fts5(key UNINDEXED,body);''')
        for did, parts in texts.items():
            for i, text in enumerate(parts):
                value = {'key': did + str(i), 'source_id': 's' + did, 'document_id': did,
                         'unit_id': 'a' if i == 0 else 'p', 'block_ids': [str(i)], 'text': text}
                db.execute('INSERT INTO unit VALUES(?,?,?,?)', (value['key'], value['source_id'], did, json.dumps(value)))
                db.execute('INSERT INTO unit_fts VALUES(?,?)', (value['key'], '영업일'))
    fm = {'schema_version': 'semantic-unit-fulltext-v1', 'generation_id': sm['generation_id'],
          'source_store_sha256': sm['store_sha256'], 'navigation_index_sha256': nm['index_sha256'],
          'index_sha256': sha(ft / 'units.sqlite'), 'counts': {'unit': 4}, 'scope': {'document_version_ids': ['d1', 'd2']}}
    write(ft / 'manifest.json', fm)
    sm['fulltext'] = {'path': 'fulltext', 'manifest_sha256': sha(ft / 'manifest.json'), 'navigation_index_sha256': nm['index_sha256']}
    if glossary:
        import shutil
        from lawrag.pipeline.glossary_serving import project
        g = gen / 'glossary'; g.mkdir()
        dictionary = g / 'dictionary.sqlite'
        shutil.copyfile(term_glossary / 'dictionary.sqlite', dictionary)
        project(term_glossary.parent / 'knowledge', dictionary, g / 'bundle')
        cache = g / 'cache'; cache.mkdir()
        with sqlite3.connect(cache / 'test.sqlite') as db:
            db.execute('CREATE TABLE label(text TEXT)')
            db.execute('INSERT INTO label VALUES(?)', ('영업일',))
        binding = {'manifest_sha256': sha(g / 'bundle/manifest.json'), 'dictionary_sha256': sha(dictionary), 'compiler_sha256': 'unverified'}
        write(cache / 'test.json', {'binding': binding, 'sha256': sha(cache / 'test.sqlite')})
        sm['glossary'] = {'schema_version': 'glossary-serving-v2', 'bundle': 'glossary/bundle', 'dictionary': 'glossary/dictionary.sqlite',
                          'cache': 'glossary/cache', 'manifest_sha256': binding['manifest_sha256'], 'cache_receipt': 'test.json', 'cache_receipt_sha256': sha(cache / 'test.json')}
    write(gen / 'manifest.json', sm)
    rebind(gen)
    return gen


def rebind(gen):
    sm = json.loads((gen / 'manifest.json').read_text())
    sm['store_sha256'] = sha(gen / 'store.sqlite')
    nm = json.loads((gen / 'navigation/manifest.json').read_text())
    nm['source_store_sha256'] = sm['store_sha256']
    nm['source_manifest_sha256'] = digest({k: v for k, v in sm.items() if k not in {'navigation', 'fulltext', 'fulltext_derivation'}})
    nm['index_sha256'] = sha(gen / 'navigation/navigation.sqlite')
    write(gen / 'navigation/manifest.json', nm)
    sm['navigation']['manifest_sha256'] = sha(gen / 'navigation/manifest.json')
    fm = json.loads((gen / 'fulltext/manifest.json').read_text())
    fm.update(source_store_sha256=sm['store_sha256'], navigation_index_sha256=nm['index_sha256'], index_sha256=sha(gen / 'fulltext/units.sqlite'))
    write(gen / 'fulltext/manifest.json', fm)
    sm['fulltext'].update(manifest_sha256=sha(gen / 'fulltext/manifest.json'), navigation_index_sha256=nm['index_sha256'])
    write(gen / 'manifest.json', sm)


def run(gen, out, *extra):
    code = audit.main(['--generation', str(gen), '--output', str(out), *map(str, extra)])
    return code, json.loads((out / 'summary.json').read_text())


def codes(out):
    return {json.loads(s)['code'] for s in (out / 'issues.jsonl').read_text().splitlines()}


@pytest.mark.parametrize('compact', [False, True])
def test_complete_readonly_counts_and_html(tmp_path, compact):
    gen = fixture(tmp_path, compact=compact)
    before = {str(p): (sha(p), p.stat().st_mtime_ns) for p in gen.parent.rglob('*') if p.is_file()}
    out = tmp_path / 'report'
    extra = ['--audit-root', gen.parent / 'audit'] if compact else []
    code, result = run(gen, out, *extra)
    assert code == 0, (result, (out / 'issues.jsonl').read_text())
    assert result['completed'] and not result['quality_certified']
    assert result['database_counts']['source']['document'] == 2
    assert result['database_counts']['navigation']['reference'] == 1
    assert result['database_counts']['fulltext']['unit'] == 4
    assert before == {str(p): (sha(p), p.stat().st_mtime_ns) for p in gen.parent.rglob('*') if p.is_file()}
    page = (out / 'documents' / audit.doc_file('d2')).read_text()
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in page
    assert '<script>alert(1)</script>' not in page
    assert 'incoming_references' in page
    assert 'ORIGINAL_SEMANTIC_REVIEW_REQUIRED' in codes(out)


def test_glossary_export_without_build_audit(tmp_path, term_glossary):
    gen = fixture(tmp_path, glossary=True, term_glossary=term_glossary)
    out = tmp_path / 'report'
    code, result = run(gen, out)
    assert code == 0, (result, (out / 'issues.jsonl').read_text())
    assert result['schemas']['glossary'] == 'glossary-serving-v2'
    text = (out / 'records.jsonl').read_text()
    assert 'dictionary:entry' in text and 'glossary:nodes.sqlite:node' in text
    assert list((out / 'catalogues').glob('*.html'))


def test_structure_cycle_provenance_empty_and_fts_damage(tmp_path):
    gen = fixture(tmp_path)
    with sqlite3.connect(gen / 'store.sqlite') as db:
        db.execute("UPDATE source_unit SET parent_id='p' WHERE document_id='d1' AND unit_id='a'")
        db.execute("UPDATE block_payload SET source_artifact_sha256='other' WHERE document_id='d1' AND block_id='0'")
    with sqlite3.connect(gen / 'fulltext/units.sqlite') as db:
        db.execute("DELETE FROM unit_fts WHERE key='d10'")
    rebind(gen)
    out = tmp_path / 'report'
    code, result = run(gen, out)
    assert code == 1 and result['completed']
    assert {'PARENT_CYCLE', 'BLOCK_PROVENANCE_MISMATCH', 'FTS_ROW_MISSING'} <= codes(out)


def test_compact_hidden_orphans_are_not_hidden(tmp_path):
    gen = fixture(tmp_path)
    with sqlite3.connect(gen / 'navigation/navigation.sqlite') as db:
        db.execute('INSERT INTO occurrence_keys VALUES(999,999)')
        db.execute('INSERT INTO reference_payload VALUES(?,?,?)', ('orphan', 'd1', json.dumps({'source_text_sha256': 'missing'})))
    rebind(gen)
    out = tmp_path / 'report'
    code, _ = run(gen, out)
    assert code == 1
    assert {'HIDDEN_OCCURRENCE_ORPHAN', 'HIDDEN_REFERENCE_ORPHAN'} <= codes(out)


def test_hash_drift_and_reverse_index_damage(tmp_path):
    gen = fixture(tmp_path)
    with sqlite3.connect(gen / 'navigation/navigation.sqlite') as db:
        db.execute("DELETE FROM reference_end WHERE source_id='sd2'")
    out = tmp_path / 'report'
    code, _ = run(gen, out)
    assert code == 1
    assert {'HASH_MISMATCH', 'REFERENCE_REVERSE_INDEX_DIFF'} <= codes(out)


def test_resume_preserves_report_on_identity_change(tmp_path):
    gen = fixture(tmp_path)
    out = tmp_path / 'report'
    run(gen, out)
    assert run(gen, out, '--resume')[0] == 0
    before = (out / 'summary.json').read_bytes(), (out / 'report.sqlite').read_bytes()
    with (gen / 'store.sqlite').open('ab') as f:
        f.write(b'changed')
    assert audit.main(['--generation', str(gen), '--output', str(out), '--resume']) == 2
    assert before == ((out / 'summary.json').read_bytes(), (out / 'report.sqlite').read_bytes())


def test_partial_missing_assets_and_no_overwrite(tmp_path):
    gen = fixture(tmp_path)
    (gen / 'navigation/navigation.sqlite').unlink()
    out = tmp_path / 'report'
    code, result = run(gen, out)
    assert code == 2 and not result['completed']
    assert (out / 'index.html').is_file()
    before = (out / 'summary.json').read_bytes()
    assert audit.main(['--generation', str(gen), '--output', str(out)]) == 2
    assert before == (out / 'summary.json').read_bytes()


def test_wal_no_new_sidecars_and_refuses_input_output(tmp_path):
    gen = fixture(tmp_path)
    out = tmp_path / 'report'
    assert audit.main(['--generation', str(gen), '--output', str(gen / 'report')]) == 2
    (gen / 'store.sqlite-wal').write_bytes(b'active')
    before = set(gen.rglob('*'))
    code, result = run(gen, out)
    assert code == 2 and not result['completed']
    assert before == set(gen.rglob('*'))


def test_explicit_current_no_local_fallback_and_input_coverage(tmp_path, monkeypatch):
    gen = fixture(tmp_path)
    root = tmp_path
    (root / 'generations').mkdir()
    write(root / 'generations/CURRENT.json', {'schema_version': 'genos-current-generation-v1', 'path': str(gen), 'manifest_sha256': sha(gen / 'manifest.json')})
    monkeypatch.delenv('GENOS_GENERATION', raising=False)
    monkeypatch.delenv('GENOS_DATA_ROOT', raising=False)
    out = tmp_path / 'report'
    selection = tmp_path / 'selection.json'
    write(selection, {'schema_version': 'structure-selection-v1', 'documents': {'d1': {}, 'd2': {}}, 'expected_document_ids': ['d1', 'd2', 'failed'], 'completed': False})
    status = tmp_path / 'status.json'
    write(status, {'documents': [{'document_id': 'failed', 'selection': 'INPUT_FAILED'}]})
    assert audit.main(['--data-root', str(root), '--output', str(out), '--selection', str(selection), '--status-report', str(status)]) == 0
    assert {'INPUT_NOT_STRUCTURED', 'INPUT_DOCUMENT_NOT_SERVED'} <= codes(out)
    write(root / 'generations/CURRENT.json', {'schema_version': 'genos-current-generation-v1', 'path': str(gen), 'manifest_sha256': 'wrong'})
    assert audit.main(['--data-root', str(root), '--output', str(tmp_path / 'no')]) == 2


def test_original_paths_hash_and_escape(tmp_path):
    gen = fixture(tmp_path)
    originals = tmp_path / 'originals'; originals.mkdir()
    raw = originals / 'sample.xml'; raw.write_text('<document>모의 원문</document>')
    metadata = {'document_metadata': {'representations': [{'path': '/old/site/sample.xml', 'relative_path': 'sample.xml', 'sha256': sha(raw)}]}}
    with sqlite3.connect(gen / 'store.sqlite') as db:
        db.execute('UPDATE document SET json=? WHERE document_id=?', (json.dumps(metadata), 'd1'))
    rebind(gen)
    out = tmp_path / 'report'
    assert run(gen, out, '--raw-root', originals)[0] == 0
    assert 'original_files' in (out / 'records.jsonl').read_text()
    assert not (originals / 'report').exists()


def test_actual_legacy_compiler_contract(tmp_path, term_glossary):
    gen = fixture(tmp_path, compact=False)
    from semantic_runtime.storage import Store
    from semantic_runtime.term_index import compile_index
    import shutil
    shutil.rmtree(gen / 'navigation')
    shutil.rmtree(gen / 'fulltext')
    sm = json.loads((gen / 'manifest.json').read_text())
    sm.pop('navigation'); sm.pop('fulltext'); write(gen / 'manifest.json', sm)
    with closing(Store(gen)) as store:
        compile_index(store, term_glossary.parent / 'knowledge/legal.sqlite', term_glossary / 'dictionary.sqlite', gen / 'navigation')
    sm['navigation'] = {'path': 'navigation', 'manifest_sha256': sha(gen / 'navigation/manifest.json')}
    write(gen / 'manifest.json', sm)
    out = tmp_path / 'report'
    code, result = run(gen, out)
    assert code == 0, (result, (out / 'issues.jsonl').read_text())
    assert result['stages']['global-checks'] == 'COMPLETE'


def add_navigation_audit(gen):
    root = gen.parent / 'audit/navigation'; root.mkdir()
    with sqlite3.connect(root / 'navigation.sqlite') as db:
        db.executescript('''
        CREATE TABLE link_catalogue(id TEXT PRIMARY KEY,kind TEXT,key TEXT,term_id TEXT,status TEXT,reason TEXT,json TEXT);
        CREATE TABLE link_occurrence(id TEXT PRIMARY KEY,key TEXT,document_id TEXT,block_id TEXT,unit_id TEXT,start INTEGER,end INTEGER,source_id TEXT,source_text_sha256 TEXT,source_artifact_sha256 TEXT,matched_text TEXT,status TEXT,reason TEXT);
        CREATE TABLE occurrence_evidence(occurrence_id TEXT,catalogue_id TEXT,term_id TEXT,source_id TEXT,status TEXT,reason TEXT);
        CREATE TABLE occurrence_origin(term_id TEXT,source_id TEXT,origin TEXT);
        ''')
        db.execute('INSERT INTO link_catalogue VALUES(?,?,?,?,?,?,?)', ('c', 'label', '영업일', 't', 'ACCEPTED', 'EXACT', '{}'))
        text = '제1조(정의) 영업일'
        a = text.index('영업일'); z = a + len('영업일')
        db.execute('INSERT INTO link_occurrence VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   ('o', '영업일', 'd1', '0', 'a', a, z, 'sd1', audit.text_hash(text), 'raw-hash', '영업일', 'ACCEPTED', 'EXACT'))
        db.execute('INSERT INTO link_occurrence VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   ('held', '영업일', 'd1', 'missing', None, 0, 999, None, None, None, '', 'HELD', 'SOURCE_BLOCK_MISSING'))
        db.execute('INSERT INTO occurrence_evidence VALUES(?,?,?,?,?,?)', ('o', 'c', 't', 'sd1', 'ACCEPTED', 'EXACT'))
        db.execute('INSERT INTO occurrence_origin VALUES(?,?,?)', ('t', 'sd1', 'VERIFIED_GLOSSARY_LINK'))
    nm = json.loads((gen / 'navigation/manifest.json').read_text())
    counts = dict(link_catalogue=1, link_occurrence=2, occurrence_evidence=1, occurrence_origin=1)
    am = {'schema_version': 'term-navigation-storage-v3', 'audit_file': 'navigation.sqlite', 'audit_sha256': sha(root / 'navigation.sqlite'),
          'serving_index_sha256': nm['index_sha256'], 'construction_tables': counts}
    write(root / 'manifest.json', am)
    nm['storage'] = {'schema_version': 'term-navigation-storage-v3', 'audit_manifest_sha256': sha(root / 'manifest.json')}
    write(gen / 'navigation/manifest.json', nm)
    rebind(gen)


def test_storage_v3_audit_held_is_warning_and_evidence_checked(tmp_path):
    gen = fixture(tmp_path)
    add_navigation_audit(gen)
    out = tmp_path / 'report'
    code, result = run(gen, out, '--audit-root', gen.parent / 'audit')
    assert code == 0, (result, (out / 'issues.jsonl').read_text())
    assert 'TERM_OCCURRENCE_HELD' in codes(out)
    assert result['audit_status_counts']['link_occurrence'] == {'ACCEPTED': 1, 'HELD': 1}
    assert 'audit:link_occurrence' in (out / 'documents' / audit.doc_file('d1')).read_text()
    root = gen.parent / 'audit/navigation'
    with sqlite3.connect(root / 'navigation.sqlite') as db:
        db.execute("UPDATE occurrence_evidence SET catalogue_id='missing'")
    am = json.loads((root / 'manifest.json').read_text())
    am['audit_sha256'] = sha(root / 'navigation.sqlite'); write(root / 'manifest.json', am)
    nm = json.loads((gen / 'navigation/manifest.json').read_text())
    nm['storage']['audit_manifest_sha256'] = sha(root / 'manifest.json')
    write(gen / 'navigation/manifest.json', nm); rebind(gen)
    damaged = tmp_path / 'damaged-report'
    assert run(gen, damaged, '--audit-root', gen.parent / 'audit')[0] == 1
    assert 'AUDIT_EVIDENCE_ORPHAN' in codes(damaged)


def test_python311_syntax_and_standalone_cli(tmp_path):
    import ast
    ast.parse(SCRIPT.read_text(), feature_version=(3, 11))
    result = subprocess.run([str(ROOT / '.venv/bin/python'), str(SCRIPT), '--help'], capture_output=True, text=True, cwd=tmp_path)
    assert result.returncode == 0 and '--audit-root' in result.stdout


def test_completed_status_database_exact_attempt(tmp_path):
    gen = fixture(tmp_path)
    ledger = tmp_path / 'status.sqlite'
    with sqlite3.connect(ledger) as db:
        db.executescript('''CREATE TABLE status_meta(version); INSERT INTO status_meta VALUES(1);
        CREATE TABLE attempts(id TEXT,stage TEXT,status TEXT);
        CREATE TABLE documents(attempt TEXT,id TEXT,ordinal INTEGER,data TEXT);''')
        db.executemany('INSERT INTO attempts VALUES(?,?,?)', [('first', 'structure', 'FAILED'), ('finished', 'structure', 'COMPLETED_WITH_FAILURES')])
        for i, did in enumerate(('d1', 'd2', 'failed')):
            value = {'document_id': did, 'selection': 'SELECTED', 'phases': {'structure': {'state': 'FAILED' if did == 'failed' else 'PASSED'}}}
            db.execute('INSERT INTO documents VALUES(?,?,?,?)', ('finished', did, i, json.dumps(value)))
    out = tmp_path / 'report'
    code, result = run(gen, out, '--status-db', ledger, '--status-attempt', 'finished')
    assert code == 0, result
    coverage = json.loads((out / 'input-coverage.json').read_text())
    assert coverage['status_database_report_counts']['structure'] == {'FAILED': 1, 'PASSED': 2}
    bad = tmp_path / 'ambiguous-report'
    assert run(gen, bad, '--status-db', ledger)[0] == 2
    assert 'available attempts' in (bad / 'issues.jsonl').read_text()


def test_selection_origin_preserves_parent_failure_counts(tmp_path):
    gen = fixture(tmp_path)
    root = tmp_path / 'selection'; root.mkdir()
    path = root / 'structure-selection.json'
    selected = {'d1': {}, 'd2': {}}
    write(root / 'parent-selection.json', {'documents': selected})
    write(root / 'parent-status.json', {'documents': [{'document_id': 'failed', 'selection': 'INPUT_FAILED', 'phases': {}}]})
    write(root / 'selection-origin.json', {'schema_version': 'structure-selection-origin-v1', 'selected_document_ids': ['d1', 'd2'],
                                          'parent_selection_sha256': sha(root / 'parent-selection.json'), 'parent_status_sha256': sha(root / 'parent-status.json'),
                                          'omitted_count': 1, 'coverage': 'PARTIAL', 'omitted_documents': ['failed']})
    write(path, {'schema_version': 'structure-selection-v1', 'documents': selected, 'expected_document_ids': ['d1', 'd2'],
                 'origin_sha256': sha(root / 'selection-origin.json')})
    out = tmp_path / 'report'
    assert run(gen, out, '--selection', path)[0] == 0
    assert 'INPUT_DOCUMENT_NOT_SERVED' in codes(out)
    assert json.loads((out / 'input-coverage.json').read_text())['origin']['omitted_count'] == 1


def test_delivery_txt_contains_exact_source_and_launches(tmp_path):
    wrapper = PACKAGE / 'GENOS_DATA_AUDIT_20261006_R2_RUN.txt'
    text = wrapper.read_text()
    embedded = text.split("<<'__GENOS_DATA_AUDIT_PY_R2__'\n", 1)[1].split('__GENOS_DATA_AUDIT_PY_R2__\n', 1)[0]
    assert embedded == SCRIPT.read_text()
    gen = fixture(tmp_path)
    before = {p: sha(p) for p in gen.parent.rglob('*') if p.is_file()}
    import os
    env = {**os.environ, 'GENOS_DATA_AUDIT_LOG_ROOT': str(tmp_path / 'launcher-logs')}
    out = tmp_path / 'report'
    for output, expected, extra in [(out, 0, ['--audit-root', str(gen.parent / 'audit')]),
                                     (out, 2, [])]:
        result = subprocess.run(['bash', str(wrapper), '--generation', str(gen), '--output', str(output), *extra],
                                env=env, cwd=tmp_path, capture_output=True, text=True, timeout=30)
        assert result.returncode == expected, result.stdout + result.stderr
        assert 'DATA_AUDIT_EXIT=' + str(expected) in result.stdout
    assert before == {p: sha(p) for p in gen.parent.rglob('*') if p.is_file()}
    runs = list((tmp_path / 'launcher-logs').glob('run-*'))
    assert sorted(json.loads((p / 'exit.json').read_text())['exit_code'] for p in runs) == [0, 2]
    assert all((p / 'run.log').stat().st_size for p in runs)


def snapshot(root):
    return {str(p): (sha(p), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file() and not p.is_symlink()}


def test_photo_r1_reproduction_r2_parent_alias_and_resume(tmp_path, capsys):
    gen = fixture(tmp_path)
    before = snapshot(gen.parent)
    workspace = tmp_path / 'workspace'; workspace.mkdir()
    home = tmp_path / 'home'; home.mkdir()
    dev = home / 'DEV'; dev.symlink_to(workspace, target_is_directory=True)
    transfer = tmp_path / 'transfer'; transfer.mkdir()
    (workspace / 'TRANSFER').symlink_to(transfer, target_is_directory=True)
    out = dev / 'TRANSFER/report'
    old_script = ROOT / '08_DEPLOYMENT/GENOS/diagnostics/data_audit_20261006_r1/GENOS_DATA_AUDIT_20261006_R1.py'
    spec = importlib.util.spec_from_file_location('audit_r1_reproduction', old_script)
    old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
    assert old.main(['--generation', str(gen), '--output', str(out), '--code-root', str(dev)]) == 2
    assert 'Report output symlinks are forbidden' in capsys.readouterr().err
    assert not out.exists() and snapshot(gen.parent) == before
    compiler = workspace / '02_BACKEND/semantic_runtime/full_glossary.py'
    compiler.parent.mkdir(parents=True); compiler.write_text('# mock compiler')
    assert audit.contained(dev.resolve(), '02_BACKEND/semantic_runtime/full_glossary.py') == compiler
    extra = ['--audit-root', gen.parent / 'audit', '--code-root', dev]
    code, result = run(gen, out, *extra)
    assert code == 0, result
    assert result['path_resolution']['output'] == {'requested': str(out), 'resolved': str(transfer / 'report')}
    assert result['path_resolution']['code_root']['resolved'] == str(workspace)
    assert 'paths-resolved' in capsys.readouterr().out
    assert str(transfer / 'report') in (out / 'run.log').read_text()
    assert run(gen, out, *extra, '--resume')[0] == 0
    assert snapshot(gen.parent) == before


def test_parent_alias_to_input_is_still_rejected(tmp_path, capsys):
    gen = fixture(tmp_path)
    before = snapshot(gen.parent)
    alias = tmp_path / 'alias'; alias.symlink_to(gen, target_is_directory=True)
    out = alias / 'report'
    assert audit.main(['--generation', str(gen), '--output', str(out)]) == 2
    assert 'separate from the generation' in capsys.readouterr().err
    assert not out.exists() and snapshot(gen.parent) == before


@pytest.mark.parametrize('dangling', [False, True])
def test_direct_output_link_rejected(tmp_path, dangling, capsys):
    gen = fixture(tmp_path)
    target = tmp_path / 'target'
    if not dangling:
        target.mkdir(); (target / 'untouched').write_text('preserve')
    link = tmp_path / 'report'; link.symlink_to(target, target_is_directory=True)
    before = snapshot(tmp_path)
    assert audit.main(['--generation', str(gen), '--output', str(link)]) == 2
    assert 'directory itself must not be a symlink' in capsys.readouterr().err
    assert snapshot(tmp_path) == before and target.exists() == (not dangling)


def test_dangling_parent_link_rejected(tmp_path, capsys):
    gen = fixture(tmp_path)
    target = tmp_path / 'absent'
    alias = tmp_path / 'DEV'; alias.symlink_to(target, target_is_directory=True)
    assert audit.main(['--generation', str(gen), '--output', str(alias / 'TRANSFER/report')]) == 2
    assert 'parent symlink has no directory target' in capsys.readouterr().err
    assert not target.exists()


@pytest.mark.parametrize('name', ['audit.lock', 'run.log', 'report.sqlite', 'documents', 'catalogues', 'summary.json.tmp', 'dangling'])
def test_resume_rejects_report_links_before_any_writes(tmp_path, name, capsys):
    import shutil
    gen = fixture(tmp_path)
    out = tmp_path / 'report'
    assert run(gen, out)[0] == 0
    p = out / name
    if p.is_dir():
        shutil.rmtree(p)
    elif p.exists():
        p.unlink()
    target = gen if name in ('documents', 'catalogues') else gen / 'store.sqlite'
    if name == 'dangling':
        target = tmp_path / 'missing'
    p.symlink_to(target, target_is_directory=name in ('documents', 'catalogues'))
    before = snapshot(tmp_path)
    assert audit.main(['--generation', str(gen), '--output', str(out), '--resume']) == 2
    assert 'Symlink inside report output is forbidden' in capsys.readouterr().err
    assert snapshot(tmp_path) == before


def test_resume_rejects_hardlinked_database(tmp_path, capsys):
    import os
    gen = fixture(tmp_path)
    out = tmp_path / 'report'
    assert run(gen, out)[0] == 0
    (out / 'report.sqlite').unlink()
    os.link(gen / 'store.sqlite', out / 'report.sqlite')
    before = snapshot(tmp_path)
    assert audit.main(['--generation', str(gen), '--output', str(out), '--resume']) == 2
    assert 'Hardlinked report file is forbidden' in capsys.readouterr().err
    assert snapshot(tmp_path) == before


def test_input_inside_report_and_artifact_escape_rejected(tmp_path, capsys):
    gen = fixture(tmp_path)
    out = tmp_path / 'report'
    inside = out / 'raw'; inside.mkdir(parents=True)
    before = snapshot(tmp_path)
    assert audit.main(['--generation', str(gen), '--output', str(out), '--raw-root', str(inside), '--resume']) == 2
    assert 'overlaps an input location' in capsys.readouterr().err
    assert snapshot(tmp_path) == before
    (gen / 'escape').symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        audit.contained(gen, 'escape/source.sqlite')
    (gen / 'db-alias').symlink_to(gen / 'store.sqlite')
    with pytest.raises(ValueError, match='Symlink in artifact path'):
        audit.contained(gen, 'db-alias')


def test_glossary_compiler_binding_through_checkout_alias(tmp_path, term_glossary):
    gen = fixture(tmp_path, glossary=True, term_glossary=term_glossary)
    checkout = tmp_path / 'workspace'; checkout.mkdir()
    compiler = checkout / '02_BACKEND/semantic_runtime/full_glossary.py'
    compiler.parent.mkdir(parents=True); compiler.write_text('# mock bound compiler')
    alias = tmp_path / 'DEV'; alias.symlink_to(checkout, target_is_directory=True)
    receipt = gen / 'glossary/cache/test.json'
    value = json.loads(receipt.read_text())
    value['binding']['compiler_sha256'] = sha(compiler)
    write(receipt, value)
    manifest = json.loads((gen / 'manifest.json').read_text())
    manifest['glossary']['cache_receipt_sha256'] = sha(receipt)
    write(gen / 'manifest.json', manifest); rebind(gen)
    before = snapshot(gen.parent)
    out = alias / 'TRANSFER/report'
    code, result = run(gen, out, '--code-root', alias)
    assert code == 0, (result, (out / 'issues.jsonl').read_text())
    assert 'GLOSSARY_COMPILER_MISMATCH' not in codes(out)
    assert result['path_resolution']['code_root']['resolved'] == str(checkout)
    assert snapshot(gen.parent) == before


def test_standalone_txt_photo_command_parent_alias(tmp_path):
    import os
    gen = fixture(tmp_path)
    before = snapshot(gen.parent)
    workspace = tmp_path / 'workspace'; workspace.mkdir()
    alias = tmp_path / 'DEV'; alias.symlink_to(workspace, target_is_directory=True)
    wrapper = PACKAGE / 'GENOS_DATA_AUDIT_20261006_R2_RUN.txt'
    out = alias / 'TRANSFER/data-audit-report-002'
    env = {**os.environ, 'GENOS_DATA_AUDIT_LOG_ROOT': str(alias / 'TRANSFER/launcher-logs')}
    result = subprocess.run(['bash', str(wrapper), '--generation', str(gen), '--output', str(out), '--code-root', str(alias)],
                            env=env, cwd=alias, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'DATA_AUDIT_EXIT=0' in result.stdout and 'paths-resolved' in result.stdout
    assert (out / 'index.html').is_file()
    logs = list((alias / 'TRANSFER/launcher-logs').glob('run-*'))
    assert len(logs) == 1 and json.loads((logs[0] / 'exit.json').read_text()) == {'exit_code': 0}
    assert snapshot(gen.parent) == before
