"""Physical audit reduction must preserve every logical record and serving row."""
from contextlib import closing
import json
import sqlite3
import pytest
from lawrag.pipeline.term_generation import build_generation
from semantic_runtime import factorized_audit as audit
from semantic_runtime.navigation_storage import archive_audit, verify_build
from semantic_runtime.contracts import sha
from test_reference_build_compact_v2 import corpus, compare_builds


def test_generated_audit_omits_candidate_product_and_preserves_all_rows(tmp_path, term_glossary):
    # Many valid concepts share one surface, causing a real candidate fan-out.
    report = json.loads((term_glossary / 'report.json').read_text())
    knowledge = term_glossary.parent / 'knowledge'
    with sqlite3.connect(knowledge / 'lookup.sqlite') as db:
        db.executemany('INSERT INTO surface VALUES (?,?,?,?,?)',
            [('자금지원', 'fibo', 'loan-' + str(i), '자금지원', 'TRANSLATION') for i in range(80)])
    manifest = json.loads((knowledge / 'manifest.json').read_text())
    for row in manifest['files']:
        row.update(sha256=sha(knowledge / row['path']), bytes=(knowledge / row['path']).stat().st_size)
    (knowledge / 'manifest.json').write_text(json.dumps(manifest))
    report['knowledge_binding']['manifest_sha256'] = sha(knowledge / 'manifest.json')
    (term_glossary / 'report.json').write_text(json.dumps(report))
    source = corpus(tmp_path / 'source.sqlite', 20); original = sha(source)
    results = {}
    for profile, name in [('materialized', 'old'), ('factorized-v1', 'new')]:
        results[name] = build_generation(source, term_glossary, tmp_path / name, serving=True,
            storage_profile='compact-v2', fulltext_granularity='unit', audit_profile=profile)
    compare_builds(tmp_path / 'old', tmp_path / 'new')
    assert results['old']['counts'] == results['new']['counts']
    assert sha(source) == original
    old = tmp_path / 'old/audit/navigation/navigation.sqlite'
    new = tmp_path / 'new/audit/navigation/navigation.sqlite'
    assert new.stat().st_size < old.stat().st_size / 2
    with closing(sqlite3.connect(new)) as db:
        kinds = dict(db.execute("SELECT name,type FROM sqlite_master"))
        assert kinds['occurrence_evidence'] == kinds['occurrence_origin'] == 'view'
        assert db.execute('SELECT count(*) FROM occurrence_evidence').fetchone()[0] > 3000
    verify_build(tmp_path / 'new')
    archive_audit(new.parent)
    verify_build(tmp_path / 'new')
    assert build_generation(source, term_glossary, tmp_path / 'new', serving=True,
        storage_profile='compact-v2', fulltext_granularity='unit', audit_profile='factorized-v1') == results['new']
    with pytest.raises(ValueError, match='inputs changed'):
        build_generation(source, term_glossary, tmp_path / 'new', serving=True,
            storage_profile='compact-v2', fulltext_granularity='unit')


def test_replay_keeps_held_reason_scope_and_pre_final_span_state(tmp_path):
    with closing(sqlite3.connect(':memory:')) as db:
        db.execute('ATTACH DATABASE ? AS construction', (str(tmp_path / 'audit.sqlite'),))
        db.executescript('''
          CREATE TABLE construction.link_catalogue(id TEXT PRIMARY KEY,kind TEXT,key TEXT,term_id TEXT,status TEXT,reason TEXT,json TEXT);
          CREATE TABLE construction.link_occurrence(id TEXT PRIMARY KEY,key TEXT,document_id TEXT,block_id TEXT,unit_id TEXT,start INTEGER,end INTEGER,source_id TEXT,source_text_sha256 TEXT,source_artifact_sha256 TEXT,matched_text TEXT,status TEXT,reason TEXT);
        ''')
        audit.create(db)
        for ident, status, reason, scope, key in [
            ('global', 'ACCEPTED', 'SOURCE_LABEL_CANDIDATE', None, 'surface'),
            ('same', 'ACCEPTED', 'SOURCE_LABEL_CANDIDATE', 'doc', 'surface'),
            ('other', 'ACCEPTED', 'SOURCE_LABEL_CANDIDATE', 'different', 'surface'),
            ('held', 'HELD', 'DEFINITION_DOCUMENT_SCOPE', 'different', 'surface'),
            ('isolated', 'HELD', 'CATALOGUE_MEMBERSHIP_MISMATCH', None, 'isolated')]:
            db.execute('INSERT INTO construction.link_catalogue VALUES (?,?,?,?,?,?,?)',
                       (ident, 'dictionary', key, ident, status, reason, json.dumps({'scope_document_id': scope})))
        for ident, key, status, reason in [('valid', 'surface', 'ACCEPTED', 'VERIFIED_EXACT_SOURCE_SPAN'),
            ('invalid', 'surface', 'HELD', 'INVALID_SOURCE_SPAN'),
            ('changed', 'isolated', 'HELD', 'NO_ACCEPTED_CATALOGUE_CANDIDATE')]:
            db.execute('INSERT INTO construction.link_occurrence VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (ident, key, 'doc', '1', 'u', 0, 1, 'source', 'text-hash', 'artifact-hash', 'x', status, reason))
        values = {(o,c):(status,reason) for o,c,t,s,status,reason in db.execute('SELECT * FROM construction.occurrence_evidence')}
        assert values['valid','global'] == values['valid','same'] == ('ACCEPTED','VERIFIED_SOURCE_LABEL_CANDIDATE')
        assert values['valid','other'] == values['valid','held'] == ('HELD','DEFINITION_DOCUMENT_SCOPE')
        assert all(values['invalid',c] == ('HELD','INVALID_SOURCE_SPAN') for c in ['global','same','other','held'])
        assert values['changed','isolated'] == ('HELD','CATALOGUE_MEMBERSHIP_MISMATCH')


def test_factorized_audit_cannot_be_selected_with_legacy_storage(tmp_path, term_glossary):
    source = corpus(tmp_path / 'source.sqlite')
    with pytest.raises(ValueError, match='requires compact-v2'):
        build_generation(source, term_glossary, tmp_path / 'bad', audit_profile='factorized-v1')
    assert not (tmp_path / 'bad').exists()
