"""Actual Selection.bind against tiny table/shared-view fixtures, no corpus."""
import json
from pathlib import Path
import sqlite3
import sys

import pytest

SNAPSHOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(SNAPSHOT/'02_BACKEND'))
from semantic_runtime import search_selection as selection
from semantic_runtime.contracts import sha
from semantic_runtime.reference_build import shared_reference_schema


def actual_selection(tmp_path,monkeypatch):
    generation=tmp_path/'generation';generation.mkdir()
    manifest={'generation_id':'synthetic','store_sha256':'synthetic-store-sha'}
    (generation/'manifest.json').write_text(json.dumps(manifest))
    monkeypatch.setattr(selection,'CODE_ROOT',tmp_path/'no-deployment')
    path=selection.selection_path(generation);path.parent.mkdir()
    path.write_text(json.dumps({'schema_version':selection.VERSION,**manifest,
        'manifest_sha256':sha(generation/'manifest.json'),
        'excluded':[{'document_id':'hidden','source_artifact_sha256':'synthetic-artifact'}]}))
    return selection.Selection(generation,manifest)


def database(shared):
    db=sqlite3.connect(':memory:')
    db.executescript('''
      CREATE TABLE source(id TEXT PRIMARY KEY,document_id TEXT,json TEXT);
      INSERT INTO source VALUES('s-good','visible','{}'),('s-hidden','hidden','{}');
      CREATE TABLE definition(id TEXT PRIMARY KEY,document_id TEXT,json TEXT);
      INSERT INTO definition VALUES('d-good','visible','{}'),('d-hidden','hidden','{}'),(NULL,'visible','{}');
      CREATE TABLE reference(id TEXT PRIMARY KEY,document_id TEXT,json TEXT);
      CREATE TABLE reference_end(reference_id TEXT,source_id TEXT);
      CREATE TABLE definition_reference(definition_id TEXT,reference_id TEXT);
      CREATE INDEX link_ids ON definition_reference(definition_id,reference_id);
    ''')
    if shared:shared_reference_schema(db)
    for ident,doc in [('r-b','visible'),('r-a','visible'),('r-hidden','hidden'),('r-touch','visible'),(None,'visible')]:
        value={'id':ident,'source_text':'synthetic witness','source_text_sha256':'synthetic-sha'}
        db.execute('INSERT INTO reference VALUES(?,?,?)',(ident,doc,json.dumps(value)))
    db.executemany('INSERT INTO reference_end VALUES(?,?)',[
        ('r-a','s-good'),('r-b','s-good'),('r-touch','s-hidden'),('r-hidden','s-hidden')])
    # Nonunique fixture deliberately verifies EXISTS does not deduplicate links.
    db.executemany('INSERT INTO definition_reference VALUES(?,?)',[
        ('d-good','r-b'),('d-good','r-a'),('d-good','r-a'),('d-good','r-hidden'),
        ('d-good','r-touch'),('d-hidden','r-a'),('d-missing','r-a'),('d-good','r-missing'),
        (None,'r-a'),('d-good',None),(None,None)])
    db.commit()
    return db


@pytest.mark.parametrize('shared',[False,True])
def test_actual_bind_keeps_same_acl_null_orphan_duplicate_and_order_rows(tmp_path,monkeypatch,shared):
    selected=actual_selection(tmp_path,monkeypatch)
    db=database(shared)
    before=db.execute('SELECT * FROM main.definition_reference').fetchall()
    try:
        selected.bind(db,navigation=True)
        old=db.execute('''SELECT original.definition_id,original.reference_id FROM main.definition_reference original
            WHERE original.definition_id IN (SELECT id FROM temp.definition)
              AND original.reference_id IN (SELECT id FROM temp.reference)
            ORDER BY original.definition_id,original.reference_id''').fetchall()
        new=db.execute('SELECT * FROM temp.definition_reference ORDER BY definition_id,reference_id').fetchall()
        assert new==old==[('d-good','r-a'),('d-good','r-a'),('d-good','r-b')]
        assert db.execute('SELECT reference_id FROM definition_reference WHERE definition_id=? ORDER BY reference_id',('d-good',)).fetchall()==[('r-a',),('r-a',),('r-b',)]
        assert db.execute('SELECT * FROM main.definition_reference').fetchall()==before
        assert db.execute('PRAGMA query_only').fetchone()[0]==1
        with pytest.raises(sqlite3.DatabaseError):db.execute('DELETE FROM main.definition_reference')
        with pytest.raises(sqlite3.DatabaseError):db.execute('PRAGMA query_only=OFF')
    finally:db.close()


def test_bound_compact_temp_view_uses_correlated_point_lookups(tmp_path,monkeypatch):
    selected=actual_selection(tmp_path,monkeypatch)
    db=database(True)
    try:
        selected.bind(db,navigation=True)
        ddl=db.execute("SELECT sql FROM sqlite_temp_master WHERE name='definition_reference'").fetchone()[0]
        assert 'EXISTS (SELECT 1 FROM temp.definition d WHERE d.id=original.definition_id)' in ddl
        assert 'EXISTS (SELECT 1 FROM temp.reference r WHERE r.id=original.reference_id)' in ddl
        plan=[r[3] for r in db.execute('EXPLAIN QUERY PLAN SELECT reference_id FROM definition_reference WHERE definition_id=? ORDER BY reference_id',('d-good',))]
        assert sum('CORRELATED SCALAR SUBQUERY' in row for row in plan)>=2
        assert any('SEARCH original USING COVERING INDEX link_ids (definition_id=?)' in row for row in plan)
        assert any('sqlite_autoindex_definition_1 (id=?)' in row for row in plan)
        assert any('sqlite_autoindex_reference_payload_1 (id=?)' in row for row in plan)
        assert not any('MATERIALIZE' in row for row in plan)
        # Unchanged endpoint ACL subqueries may scan their tiny endpoint table.
        # Neither the definition nor shared reference payload is enumerated.
        assert not any(row.startswith('SCAN original') or row.startswith('SCAN r') for row in plan)
    finally:db.close()
