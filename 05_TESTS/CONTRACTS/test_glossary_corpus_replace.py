"""Corpus rebinding uses synthetic documents and a scripted provider only."""
import json
import sqlite3

import pytest

from semantic_runtime.contracts import sha, write
from lawrag.pipeline import glossary_document_update as update, glossary_review, document_release
from lawrag.pipeline import glossary_v1 as v1
from test_document_release import source, ReviewProvider


def lexical_pair(glossary):
    with sqlite3.connect(glossary / 'dictionary.sqlite') as db:
        v1.add_entry(db, 'fixture:other', 'nts', '영업일', '은행이 영업하는 날이다.')
        db.execute("INSERT INTO external_candidate VALUES ('lexical-pair','fixture:other','fixture:day','fixture:day','영업일','LABEL',NULL,'MEANING_REVIEW')")
        db.execute("INSERT INTO review_queue VALUES ('fixture:other','MEANING_REVIEW',1)")
    report = json.loads((glossary / 'report.json').read_text())
    report['dictionary_sha256'] = sha(glossary / 'dictionary.sqlite')
    (glossary / 'report.json').write_text(json.dumps(report))


def test_replace_rebuilds_evidence_and_preserves_parent_and_lexical_reviews(tmp_path, term_glossary):
    lexical_pair(term_glossary)
    old = source(tmp_path / 'old.sqlite', [('same-id', '가상규정', ['“영업일”이란 예전 은행 영업일을 말한다.']),
                                         ('removed-id', '과거규정', ['“옛말”이란 과거의 용어를 말한다.'])])
    # prepare expects the source store basename used by the pipeline.
    merged = document_release.merge_sources([old], tmp_path / 'old-sources')
    update.augment(term_glossary, merged, tmp_path / 'old-draft')
    provider = ReviewProvider()
    glossary_review.complete(tmp_path / 'old-draft', tmp_path / 'old-review', tmp_path / 'parent', provider=provider)
    parent = tmp_path / 'parent'
    before = {p.name: sha(p) for p in parent.iterdir() if p.is_file()}
    current = source(tmp_path / 'new.sqlite', [('same-id', '가상규정', ['앞부분이 추가됨.', '“영업일”이란 현재 은행이 일하는 날을 말한다.', '영업일 기준으로 적용한다.'])])
    merged = document_release.merge_sources([current], tmp_path / 'new-sources')
    with pytest.raises(ValueError, match='version ID reused'):
        update.augment(parent, merged, tmp_path / 'blocked')
    report = update.augment(parent, merged, tmp_path / 'new-draft', corpus_policy='replace')
    assert update.augment(parent, merged, tmp_path / 'new-draft', corpus_policy='replace') == report
    assert all(sha(parent / name) == value for name, value in before.items())
    assert report['document_update']['corpus_replacement']['removed_definitions'] == 2
    assert report['document_update']['corpus_replacement']['removed_reviews'] > 0
    with sqlite3.connect(tmp_path / 'new-draft/dictionary.sqlite') as db:
        assert db.execute('SELECT document_id FROM corpus_document').fetchall() == [('same-id',)]
        assert db.execute('SELECT block_id FROM corpus_definition').fetchall() == [('1',)]
        assert db.execute("SELECT count(*) FROM occurrence WHERE block_id='2'").fetchone()[0] > 0
        assert db.execute("SELECT count(*) FROM occurrence WHERE document_id='removed-id'").fetchone()[0] == 0
        assert db.execute('SELECT external_id,target_id FROM llm_review_v3').fetchall() == [('fixture:other', 'fixture:day')]
        assert not db.execute("SELECT 1 FROM sense_source WHERE payload LIKE '%예전%'").fetchone()
        assert db.execute("SELECT definition FROM entry WHERE id='fixture:day'").fetchone()[0] == '영업일은 은행이 영업하는 날을 말한다.'
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    plan = glossary_review.prepare(tmp_path / 'new-draft', tmp_path / 'new-review')
    assert plan['total_jobs'] > 0
    with sqlite3.connect(tmp_path / 'new-review/review.sqlite') as db:
        assert db.execute('SELECT count(*) FROM reused_job').fetchone()[0] == 1
        assert not db.execute("SELECT 1 FROM job WHERE input_json LIKE '%예전%'").fetchone()
    completed = glossary_review.complete(tmp_path / 'new-draft', tmp_path / 'new-review', tmp_path / 'new-reviewed', provider=provider)
    assert completed['completed']
    assert document_release.verify_glossary(tmp_path / 'new-reviewed')['verified']


def test_release_replace_runs_through_index_and_pins_policy(tmp_path, term_glossary, monkeypatch):
    old = source(tmp_path / 'old.sqlite', [('doc', '가상규정', ['“영업일”이란 과거의 정의를 말한다.'])])
    update.augment(term_glossary, old, tmp_path / 'parent')
    current = source(tmp_path / 'current.sqlite', [('doc', '가상규정', ['“영업일”이란 은행이 영업하는 날을 말한다.'])])
    monkeypatch.setattr(document_release, 'selected_sources', lambda *a: ([current], {str(current): sha(current)}))
    provider = ReviewProvider()
    args = dict(glossary_corpus_policy='replace', provider=provider)
    assert document_release.build(tmp_path, 'new-run', tmp_path / 'parent', stage='prepare', **args)['status'] == 'PREPARED'
    assert provider.calls == 0
    with pytest.raises(ValueError, match='inputs changed'):
        document_release.build(tmp_path, 'new-run', tmp_path / 'parent', stage='prepare')
    assert document_release.build(tmp_path, 'new-run', tmp_path / 'parent', stage='review', **args)['status'] == 'REVIEWED'
    calls = provider.calls
    result = document_release.build(tmp_path, 'new-run', tmp_path / 'parent', stage='index', **args)
    assert result['completed'] and provider.calls == calls
    assert document_release.verify_release(tmp_path / 'TERM_RELEASES/new-run')
    assert sha(current) == json.loads((tmp_path / 'TERM_RELEASES/new-run/plan.json').read_text())['pins'][str(current)]
