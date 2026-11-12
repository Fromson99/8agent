"""Reference reads by indexed keys on Oracle (2026-11-12, reference-joins-indexed on MAIN216).

`reference r JOIN reference_end x ON x.reference_id=r.id WHERE x.source_id=?` went through the plan translator,
which expanded every reference row of the release (field 6ca98162: 60 s ReadTimeout). Ten callers (FOLLOW,
comparison reference hop, recall, relation cards, navigation loops) now use term_index.references_at:
Oracle tools answer with Tools.references_from (two indexed reads), SQLite keeps the join.
"""
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from semantic_runtime import term_index


def sqlite_tools():
    db = sqlite3.connect(':memory:')
    db.executescript('CREATE TABLE reference(id TEXT PRIMARY KEY,document_id TEXT,json TEXT);'
                     'CREATE TABLE reference_end(source_id TEXT,reference_id TEXT,PRIMARY KEY(source_id,reference_id));')
    for rid, src in (('ref:b', 's1'), ('ref:a', 's1'), ('ref:c', 's2')):
        db.execute('INSERT INTO reference VALUES(?,?,?)', (rid, 'd', json.dumps({'id': rid, 'source_id': src})))
        db.execute('INSERT INTO reference_end VALUES(?,?)', (src, rid))
    db.execute('INSERT INTO reference_end VALUES(?,?)', ('s1', 'ref:c'))  # incoming end
    return SimpleNamespace(db=db)


def test_sqlite_keeps_the_join_in_reference_order():
    tools = sqlite_tools()
    old = [r[0] for r in tools.db.execute('SELECT r.json FROM reference r JOIN reference_end x ON x.reference_id=r.id '
                                          'WHERE x.source_id=? ORDER BY r.id', ('s1',))]
    assert term_index.references_at(tools, 's1') == old
    assert [json.loads(t)['id'] for t in old] == ['ref:a', 'ref:b', 'ref:c']
    assert term_index.references_at(tools, 'none') == []


def test_oracle_tools_use_indexed_reads_not_the_join():
    asked = []

    class DB:
        def execute(self, *a):
            raise AssertionError('the reference join must not be sent on Oracle')
    tools = SimpleNamespace(db=DB(), references_from=lambda anchor, after, only, limit: asked.append(
        (anchor, after, only)) or ['{"id":"ref:a"}'])
    assert term_index.references_at(tools, 's1') == ['{"id":"ref:a"}']
    assert asked == [('s1', '', None)]


def test_no_caller_sends_the_reference_join_directly():
    root = Path(term_index.__file__).resolve().parent
    callers = ['legal_agent/source_tools.py', 'legal_agent/source_investigation.py', 'legal_agent/source_recall.py',
               'legal_agent/source_recall_global.py', 'legal_agent/relation_cards.py', 'legal_agent/exploration_tools.py',
               'navigation_loop.py', 'multi_entry_navigation.py', 'work_navigation.py', 'legal_agent/workflow_relation_cards.py']
    for name in callers:
        text = (root / name).read_text(encoding='utf-8')
        assert 'references_at(' in text, name
        assert 'JOIN reference_end' not in text and 'FROM reference_end x\n' not in text, name
