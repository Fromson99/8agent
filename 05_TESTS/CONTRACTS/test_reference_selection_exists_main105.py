"""Installed-code four-view SQL contracts using tiny in-memory data only.

This file is copied into the extracted checkout by the handoff validator. It
imports that checkout, preserves real relation keys, and makes no timing claim.
"""
from collections import Counter
import json
from pathlib import Path
import re
import sqlite3
import sys

import pytest

CHECKOUT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(CHECKOUT / '02_BACKEND'))
from semantic_runtime import search_selection as selection
from semantic_runtime.contracts import sha
from semantic_runtime.legal_agent.repository import text_hash
from semantic_runtime.reference_build import shared_reference_schema
from semantic_runtime.resident_data import _readonly

VIEWS = ('reference_end', 'reference_target', 'reference_candidate', 'reference_candidate_end')
DDL = '''
CREATE TABLE source(id TEXT PRIMARY KEY,document_id TEXT,article TEXT,json TEXT);
CREATE INDEX source_document ON source(document_id);
CREATE TABLE reference(id TEXT PRIMARY KEY,document_id TEXT,json TEXT);
CREATE TABLE reference_end(source_id TEXT,reference_id TEXT,PRIMARY KEY(source_id,reference_id));
CREATE TABLE reference_target(reference_id TEXT,ordinal INTEGER,source_id TEXT,unit_id TEXT,
 unit_path TEXT,block_ids TEXT,target_level TEXT,PRIMARY KEY(reference_id,ordinal));
CREATE INDEX reference_target_source ON reference_target(source_id,reference_id);
CREATE TABLE reference_candidate(reference_id TEXT,candidate_id TEXT,ordinal INTEGER,source_id TEXT,
 unit_id TEXT,unit_path TEXT,block_ids TEXT,target_level TEXT,basis TEXT,json TEXT,
 PRIMARY KEY(reference_id,candidate_id));
CREATE TABLE reference_candidate_end(source_id TEXT,reference_id TEXT,candidate_id TEXT,
 PRIMARY KEY(source_id,reference_id,candidate_id));
'''
REFERENCES = (
    ('r-keep', 'visible'), ('r-owner-hidden', 'hidden'),
    ('r-end-hidden', 'visible'), ('r-target-hidden', 'visible'),
    ('r-candidate-hidden', 'visible'), ('r-candidate-end-hidden', 'visible'),
    ('r-missing-source', 'visible'), ('r-null-document', None),
    ('', 'visible'), (None, 'visible'),
)


def actual_selection(tmp_path, monkeypatch, mode):
    assert Path(selection.__file__).resolve() == CHECKOUT / '02_BACKEND/semantic_runtime/search_selection.py'
    generation = tmp_path / 'generation'
    generation.mkdir()
    manifest = {'generation_id': 'tiny-installed-fixture', 'store_sha256': 'synthetic-store'}
    (generation / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    monkeypatch.setattr(selection, 'CODE_ROOT', tmp_path / 'no-deployment')
    if mode != 'early_return':
        value = {'schema_version': selection.LATEST_VERSION if mode == 'latest_only' else selection.VERSION,
                 **manifest, 'manifest_sha256': sha(generation / 'manifest.json'),
                 'excluded': [] if mode == 'latest_only' else [
                     {'document_id': 'hidden', 'source_artifact_sha256': 'synthetic-artifact'}]}
        if mode == 'latest_only':
            value['latest_documents'] = [{'document_id': 'visible', 'is_latest': True}]
        path = selection.selection_path(generation)
        path.parent.mkdir()
        path.write_text(json.dumps(value), encoding='utf-8')
    return selection.Selection(generation, manifest)


def database(shared):
    db = sqlite3.connect(':memory:')
    db.executescript(DDL)
    db.executemany('INSERT INTO source VALUES(?,?,?,?)', [
        ('s-a', 'visible', '제1조', '{}'), ('s-b', 'visible', '제2조', '{}'),
        ('s-hidden', 'hidden', '제3조', '{}')])
    if shared:
        shared_reference_schema(db)
    for ident, document in REFERENCES:
        witness = '합성 원문 ' + repr(ident)
        value = {'id': ident, 'source_text_sha256': text_hash(witness), 'source_text': witness}
        db.execute('INSERT INTO reference VALUES(?,?,?)', (ident, document, json.dumps(value, ensure_ascii=False)))
    rows = {name: [] for name in VIEWS}
    for ident in [ident for ident, _ in REFERENCES] + ['r-orphan']:
        for ordinal, default_source in enumerate(('s-a', 's-b')):
            source = 's-hidden' if ident == 'r-end-hidden' and ordinal == 0 else default_source
            if ident == 'r-missing-source':
                source = 'missing-source-' + str(ordinal)  # Distinct valid PKs; both sources are absent.
            rows['reference_end'].append((source, ident))
            source = 's-hidden' if ident == 'r-target-hidden' and ordinal == 0 else default_source
            rows['reference_target'].append((ident, ordinal, source, 'U', '["제1조"]', '["B"]', 'article'))
            source = 's-hidden' if ident == 'r-candidate-hidden' and ordinal == 0 else default_source
            rows['reference_candidate'].append((ident, 'C' + str(ordinal), ordinal, source,
                'U', '["제1조"]', '["B"]', 'article', 'EXPLICIT', '{"fixture":true}'))
            # This relation alone is not an endpoint exclusion rule in the existing contract.
            source = 's-hidden' if ident == 'r-candidate-end-hidden' and ordinal == 0 else default_source
            rows['reference_candidate_end'].append((source, ident, 'C' + str(ordinal)))
    # SQLite allows these identical rows under the real nullable composite PK.
    rows['reference_end'].extend([(None, 'r-keep'), (None, 'r-keep')])
    for name, values in rows.items():
        db.executemany('INSERT INTO ' + name + ' VALUES(' + ','.join('?' for _ in values[0]) + ')', values)
    db.commit()
    db.execute('PRAGMA query_only=ON')
    db.set_authorizer(_readonly)
    return db, rows


def assert_main_and_guard(db, before):
    assert db.serialize(name='main') == before
    assert db.execute('PRAGMA query_only').fetchone()[0] == 1
    for sql in ('DELETE FROM main.reference_end', 'PRAGMA query_only=OFF'):
        with pytest.raises(sqlite3.DatabaseError):
            db.execute(sql)
    assert db.serialize(name='main') == before


@pytest.mark.parametrize('shared', [False, True], ids=['legacy', 'compact'])
@pytest.mark.parametrize('mode', ['excluded', 'latest_only'])
def test_four_views_preserve_visibility_rows_and_consumer_order(tmp_path, monkeypatch, shared, mode):
    selected = actual_selection(tmp_path, monkeypatch, mode)
    db, rows = database(shared)
    before = db.serialize(name='main')
    state = (selected.excluded, selected.fingerprint, json.dumps(selected.latest, sort_keys=True))
    try:
        selected.bind(db, navigation=True)
        allowed = ({'r-keep', 'r-candidate-end-hidden', 'r-missing-source', ''} if mode == 'excluded'
                   else {ident for ident, _ in REFERENCES if ident is not None})
        for name in VIEWS:
            rid_column = 0 if name in ('reference_target', 'reference_candidate') else 1
            expected = [row for row in rows[name] if row[rid_column] is not None and row[rid_column] in allowed]
            old = db.execute('SELECT * FROM main.' + name + ' AS original '
                             'WHERE original.reference_id IN (SELECT id FROM temp.reference)').fetchall()
            actual = db.execute('SELECT * FROM temp.' + name).fetchall()
            assert Counter(actual) == Counter(old) == Counter(expected), name
        assert db.execute("SELECT count(*) FROM temp.reference_end WHERE reference_id='r-keep' AND source_id IS NULL").fetchone()[0] == 2
        assert db.execute('SELECT ordinal,source_id FROM reference_target WHERE reference_id=? ORDER BY ordinal',
                          ('r-keep',)).fetchall() == [(0, 's-a'), (1, 's-b')]
        assert db.execute('SELECT candidate_id,ordinal FROM reference_candidate WHERE reference_id=? ORDER BY ordinal,candidate_id',
                          ('r-keep',)).fetchall() == [('C0', 0), ('C1', 1)]
        assert state == (selected.excluded, selected.fingerprint, json.dumps(selected.latest, sort_keys=True))
        assert_main_and_guard(db, before)
    finally:
        db.close()


@pytest.mark.parametrize('shared', [False, True], ids=['legacy', 'compact'])
def test_four_views_use_correlated_reference_id_lookup(tmp_path, monkeypatch, shared):
    selected = actual_selection(tmp_path, monkeypatch, 'excluded')
    db, _ = database(shared)
    before = db.serialize(name='main')
    try:
        selected.bind(db, navigation=True)
        index = 'sqlite_autoindex_reference_payload_1' if shared else 'sqlite_autoindex_reference_1'
        alias = 'r' if shared else 'original'
        for name in VIEWS:
            ddl = db.execute('SELECT sql FROM sqlite_temp_master WHERE name=?', (name,)).fetchone()[0]
            assert 'EXISTS (SELECT 1 FROM temp.reference r WHERE r.id=original.reference_id)' in ddl
            plan = [row[3] for row in db.execute('EXPLAIN QUERY PLAN SELECT * FROM ' + name +
                ' WHERE source_id=? AND reference_id=?', ('s-a', 'r-keep'))]
            assert any('CORRELATED' in row and 'SUBQUERY' in row for row in plan), (name, plan)
            assert any(row.startswith('SEARCH ') and index in row and '(id=?)' in row for row in plan), (name, plan)
            assert not any(re.match(r'^SCAN ' + alias + r'(?:$| )', row) for row in plan), (name, plan)
            assert not any('MATERIALIZE' in row for row in plan), (name, plan)
            # Other endpoint-visibility LIST/SCAN subqueries are unchanged and permitted.
        assert_main_and_guard(db, before)
    finally:
        db.close()


def test_empty_selection_keeps_original_connection_without_temp_views(tmp_path, monkeypatch):
    selected = actual_selection(tmp_path, monkeypatch, 'early_return')
    db, rows = database(False)
    before = db.serialize(name='main')
    try:
        selected.bind(db, navigation=True)
        assert db.execute("SELECT name FROM sqlite_temp_master WHERE type='view'").fetchall() == []
        for name in VIEWS:
            assert Counter(db.execute('SELECT * FROM ' + name).fetchall()) == Counter(rows[name])
        assert_main_and_guard(db, before)
    finally:
        db.close()
