"""Incremental publication keeps old rows, scopes and failed attempts intact."""
from contextlib import closing
import json
import sqlite3
import pytest
from lawrag.pipeline import document_append as appending
from lawrag.pipeline.term_generation import build_generation
from semantic_runtime import unit_fulltext
from semantic_runtime.contracts import sha
from test_document_release import source


@pytest.fixture
def inputs(tmp_path, term_glossary):
    for name, title, text in [('base', '기존규정', '영업일에 보고한다.'), ('delta', '추가규정', '분기별 위험관리위원회를 개최한다.')]:
        raw = source(tmp_path / (name + '.sqlite'), [(name, title, [text])])
        build_generation(raw, term_glossary, tmp_path / name, serving=name == 'base',
                         storage_profile='compact-v2', audit_profile='factorized-v1', fulltext_granularity='unit', fulltext_workers=1)
    base, delta = (tmp_path / n / 'generation' for n in ('base', 'delta'))
    ft = tmp_path / 'delta-fulltext'
    unit_fulltext.build(delta, delta / 'navigation', ft, workers=1)
    return base, delta, ft


def test_append_preserves_search_scope_and_is_idempotent(inputs, tmp_path):
    base, delta, ft = inputs
    before = sha(base / 'store.sqlite')
    output = tmp_path / 'combined'
    result = appending.append(*inputs, output)
    assert result['counts']['document'] == 2
    assert result['retokenized_base_documents'] == 0
    assert sha(base / 'store.sqlite') == before
    assert appending.append(*inputs, output) == result
    nav = json.loads((output / 'generation/navigation/manifest.json').read_text())
    index = unit_fulltext.UnitFulltextIndex(output / 'generation/fulltext', nav)
    with closing(index.connect()) as db:
        hits = index.rank_units(db, ['분기'])
        assert hits and {h['document_id'] for h in hits} == {'delta'}
        assert index.rank_units(db, ['분기'], set()) == []
        with pytest.raises(ValueError, match='scope'):
            index.rank_units(db, ['분기'], {'not-authorized'})
    with (output / 'generation/store.sqlite').open('ab') as stream:
        stream.write(b'drift')
    with pytest.raises(ValueError, match='drift'):
        appending.verify(output)


def test_duplicate_and_changed_inputs_fail_closed(inputs, tmp_path):
    base, delta, ft = inputs
    with pytest.raises(ValueError, match='overlap'):
        appending.append(base, base, base / 'fulltext', tmp_path / 'duplicate')
    assert not (tmp_path / 'duplicate').exists()
    with (delta / 'store.sqlite').open('ab') as stream:
        stream.write(b'drift')
    with pytest.raises(ValueError, match='hash'):
        appending.append(*inputs, tmp_path / 'drift')
    assert not (tmp_path / 'drift').exists()


def test_failed_attempt_is_recorded_and_retry_does_not_repeat_base_tokenization(inputs, tmp_path, monkeypatch):
    original = appending.combine
    def fail(*args, **kwargs):
        raise RuntimeError('injected storage failure')
    monkeypatch.setattr(appending, 'combine', fail)
    output = tmp_path / 'recovered'
    with pytest.raises(RuntimeError, match='storage failure'):
        appending.append(*inputs, output)
    failures = list(tmp_path.glob('.recovered.attempt-*/failure.json'))
    assert len(failures) == 1 and not output.exists()
    assert json.loads(failures[0].read_text())['published'] is False
    monkeypatch.setattr(appending, 'combine', original)
    monkeypatch.setattr(unit_fulltext, 'build', lambda *a, **k: pytest.fail('must reuse existing token indexes'))
    assert appending.append(*inputs, output)['base_rows_preserved']
    assert failures[0].exists()


def test_shared_concept_allows_only_verified_alternate_label(tmp_path):
    for name, label in [('base', 'Company'), ('delta', '회사')]:
        with sqlite3.connect(tmp_path / (name + '.sqlite')) as db:
            db.executescript('CREATE TABLE term(id TEXT PRIMARY KEY,json TEXT); CREATE TABLE term_surface(term_id,key,text,kind);')
            db.execute('INSERT INTO term VALUES (?,?)', ('concept:company', json.dumps({'id': 'concept:company', 'label': label, 'meaning': 'same'})))
            db.execute('INSERT INTO term_surface VALUES (?,?,?,?)', ('concept:company', label, label, 'label'))
    with sqlite3.connect(tmp_path / 'base.sqlite') as db:
        appending.attach(db, tmp_path / 'delta.sqlite', 'delta')
        appending.merge_rows(db, 'term', shared=True)
        assert json.loads(db.execute('SELECT json FROM term').fetchone()[0])['label'] == 'Company'
    with sqlite3.connect(tmp_path / 'delta.sqlite') as db:
        db.execute("UPDATE term SET json=json_set(json,'$.meaning','changed')")
    with sqlite3.connect(tmp_path / 'base.sqlite') as db:
        appending.attach(db, tmp_path / 'delta.sqlite', 'delta')
        with pytest.raises(ValueError, match='collision'):
            appending.merge_rows(db, 'term', shared=True)
