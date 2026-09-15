"""Legal-ID projection: namespace, ambiguity, direction, coverage and audit guards."""
from contextlib import closing
import json
import sqlite3

import pytest

from lawrag.pipeline import glossary_legal_relations as p
from lawrag.pipeline import glossary_assembly as assembly
from .test_glossary_assembly import assembly_inputs
from .test_glossary_scope import setup


def graph(entries, relations):
    db = sqlite3.connect(':memory:'); db.row_factory = sqlite3.Row; p.tables(db)
    for ident, kind, label, *extra in entries:
        db.execute('INSERT INTO entry VALUES (?,?,?,?,?,?)',
                   (ident, kind, label, '', extra[0] if extra else 'N', 'fixture'))
    for ident, source, target, code in relations:
        db.execute('INSERT INTO official_relation VALUES (?,?,?,?,?,?,?)',
                   (ident, source, target, code, p.CODES.get(code, ''), None, '{}'))
    p.project(db)
    p.verify_db(db)
    return db


def test_bond_meaning_selected_by_reciprocal_edge_not_label_cross_product():
    with closing(graph([
        ('L1', 'knowledge_terms', '채권'), ('L2', 'knowledge_terms', '채권'),
        ('L3', 'knowledge_terms', '국채'), ('D1', 'everyday_terms', '채권'),
        ('D2', 'everyday_terms', '국채'),
    ], [('a', 'L3', 'D1', '140303'), ('b', 'L2', 'D2', '140304')])) as db:
        assert [tuple(r) for r in db.execute('SELECT source_id,target_id,code FROM edge')] == [('L2', 'L3', '140304')]
        row = db.execute("SELECT * FROM decision WHERE relation_id='a'").fetchone()
        assert row['reason'] == 'UNIQUE_RECIPROCAL_RELATION'
        assert json.loads(row['witnesses']) == ['b']
        assert db.execute("SELECT count(*) FROM edge WHERE source_id='L1' OR target_id='L1'").fetchone()[0] == 0
        assert p.summaries(db)['decisions'] == {'CONNECTED': 2}


def test_no_same_label_excluded_including_whitespace_and_related_only():
    with closing(graph([
        ('L1', 'knowledge_terms', '채권'), ('L2', 'knowledge_terms', '국 채'),
        ('D1', 'everyday_terms', '돈받을권리'), ('D2', 'everyday_terms', '국채'),
    ], [('a', 'L1', 'D1', '140305'), ('b', 'L1', 'D2', '140304')])) as db:
        assert p.summaries(db)['decisions'] == {'EXCLUDED': 2}
        assert db.execute('SELECT count(*) FROM edge').fetchone()[0] == 0


def test_multiple_reciprocal_targets_and_ambiguous_anchor_are_held():
    entries = [('A', 'knowledge_terms', '국채'), ('B', 'knowledge_terms', '채권'),
               ('C', 'knowledge_terms', '채권'), ('DA', 'everyday_terms', '국채'),
               ('DB', 'everyday_terms', '채권')]
    with closing(graph(entries, [('a', 'A', 'DB', '140303'), ('b', 'B', 'DA', '140304'),
                                  ('c', 'C', 'DA', '140304')])) as db:
        row = db.execute("SELECT status,reason FROM decision WHERE relation_id='a'").fetchone()
        assert tuple(row) == ('HELD', 'AMBIGUOUS_LEGAL_LABEL')
    with closing(graph(entries + [('A2', 'knowledge_terms', '국채')],
                       [('a', 'A', 'DB', '140303'), ('b', 'B', 'DA', '140304')])) as db:
        assert p.summaries(db)['decisions'] == {'HELD': 2}


def test_all_five_codes_keep_meaning_and_direction():
    entries = [('A', 'knowledge_terms', 'A')]
    relations = []
    for i, code in enumerate(p.CODES):
        entries += [(f'L{i}', 'knowledge_terms', f'word{i}'),
                    (f'D{i}', 'everyday_terms', f'word{i}')]
        relations.append((f'r{i}', 'A', f'D{i}', code))
    with closing(graph(entries, relations)) as db:
        assert p.summaries(db)['decisions'] == {'CONNECTED': 5}
        expected = {('A', 'L0', '140301'), ('A', 'L1', '140302'),
                    ('L2', 'A', '140304'), ('A', 'L3', '140304'), ('A', 'L4', '140305')}
        assert {tuple(r) for r in db.execute('SELECT source_id,target_id,code FROM edge')} == expected


def test_self_synonym_is_identity_but_other_self_and_declared_homonym_held():
    with closing(graph([
        ('A', 'knowledge_terms', 'A'), ('D', 'everyday_terms', 'A'),
        ('B', 'knowledge_terms', 'B', 'Y'), ('DB', 'everyday_terms', 'B'),
    ], [('a', 'A', 'D', '140301'), ('b', 'A', 'D', '140303'),
        ('c', 'A', 'DB', '140305')])) as db:
        assert p.summaries(db)['decision_reasons'] == {
            'DECLARED_HOMONYM': 1, 'SELF_RELATION': 1, 'SELF_SYNONYM': 1}


def test_cycle_edges_held_without_losing_noncyclic_branch():
    entries = [(name, 'knowledge_terms', name) for name in 'ABCD']
    entries += [('d'+name, 'everyday_terms', name) for name in 'ABCD']
    with closing(graph(entries, [('ab', 'A', 'dB', '140304'), ('bc', 'B', 'dC', '140304'),
                                  ('ca', 'C', 'dA', '140304'), ('cd', 'C', 'dD', '140304')])) as db:
        assert p.summaries(db)['decisions'] == {'CONNECTED': 1, 'HELD': 3}
        assert tuple(db.execute("SELECT source_id,target_id FROM edge WHERE status='CONNECTED'").fetchone()) == ('C', 'D')


def test_conflicting_kinds_held_but_related_can_coexist_with_hierarchy():
    entries = [('A', 'knowledge_terms', 'A'), ('B', 'knowledge_terms', 'B'),
               ('DA', 'everyday_terms', 'A'), ('DB', 'everyday_terms', 'B')]
    with closing(graph(entries, [('a', 'A', 'DB', '140301'), ('b', 'B', 'DA', '140302')])) as db:
        assert p.summaries(db)['decision_reasons'] == {'RELATION_KIND_CONFLICT': 2}
    with closing(graph(entries, [('a', 'A', 'DB', '140304'), ('b', 'B', 'DA', '140305')])) as db:
        assert p.summaries(db)['decisions'] == {'CONNECTED': 2}


def test_build_snapshot_exports_inspect_and_hash_rejection(assembly_inputs, tmp_path):
    collection, _, _, glossary = assembly_inputs
    original = assembly.build(*assembly_inputs, emit=lambda *a, **k: None)
    output = tmp_path/'legal-graph'
    report = p.build(glossary, collection, output, emit=lambda *a, **k: None)
    assert report['counts']['input_relations'] == original['counts']['official_relation']
    assert report['api_calls'] == report['model_calls'] == 0
    assert report['runtime_promoted'] is False
    assert p.inspect(output, verify=True)['legal_endpoints_only']
    assert p.inspect(output, '신탁')['semantic_approval'] is False
    with pytest.raises(ValueError, match='already exists'):
        p.build(glossary, collection, output)
    (output/'graph.json').write_text('{}')
    with pytest.raises(ValueError, match='hash mismatch'):
        p.inspect(output)
    assert assembly.inspect(glossary)['dictionary_sha256'] == original['dictionary_sha256']
