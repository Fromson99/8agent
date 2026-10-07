"""Explicit unreviewed serving build: no model calls, no audit rewriting."""
import json
import sqlite3
from contextlib import closing

import pytest

from semantic_runtime.contracts import sha
from semantic_runtime.storage import Store
from semantic_runtime.term_index import TermIndex
from lawrag.pipeline import document_release as release, genos_stages
from test_document_release import source, ReviewProvider
from test_document_release_stages import failed_run, select


@pytest.fixture
def prepared(tmp_path, term_glossary, monkeypatch):
    raw = source(tmp_path / 'raw.sqlite', [('doc', '모의규정', [
        '“영업일”이란 은행이 영업하는 날을 말한다.',
        '“영업일”이란 은행이 정상 근무하는 날을 말한다.'])])
    monkeypatch.setattr(release, 'selected_sources', lambda *a: ([raw], {str(raw): sha(raw)}))
    release.build(tmp_path, 'prepared', term_glossary, stage='prepare')
    parent = tmp_path / 'TERM_RELEASES/prepared'
    # Preserve a partial review as in the user's existing run.
    release.build(tmp_path, 'prepared', term_glossary, stage='review', max_jobs=1, provider=ReviewProvider())
    with sqlite3.connect(parent / 'review/review.sqlite') as db:
        db.execute("UPDATE job SET status='failed',error='ValueError' WHERE id=(SELECT id FROM job WHERE status='pending' LIMIT 1)")
    return tmp_path, parent, raw


def test_index_skip_preserves_partial_review_and_builds_searchable_bundle(prepared, monkeypatch):
    data, parent, raw = prepared
    before = {p: sha(p) for p in parent.rglob('*') if p.is_file()}
    def forbidden(*a, **kw):
        pytest.fail('Skip mode must not call the review workflow or prepare again')
    monkeypatch.setattr(release.glossary_review, 'complete', forbidden)
    monkeypatch.setattr(release.glossary_review, 'prepare', forbidden)
    monkeypatch.setattr(release, 'selected_sources', forbidden)
    result = release.index_without_meaning_review(data, 'prepared', '의미 비교 보류')
    assert result['review_status'] == 'SKIPPED' and result['llm_calls'] == 0
    assert result['completed'] and result['canonical_approval'] is False
    assert all(sha(p) == fingerprint for p, fingerprint in before.items())
    assert not (parent / 'review/completion.json').exists()
    output = parent / 'serving-unreviewed'
    generation, receipt = release.verify_release(output)
    with closing(Store(generation)) as store:
        index = TermIndex(generation / 'navigation', store)
        tools = index.tools(['doc'])
        try:
            assert tools.search_labels(['영업일'], ['doc'])
        finally:
            tools.db.close()
    assert release.index_without_meaning_review(data, 'prepared', '의미 비교 보류')['cached']
    with pytest.raises(ValueError, match='inputs changed'):
        release.index_without_meaning_review(data, 'prepared', 'different reason')
    assert not (data / 'generations/CURRENT.json').exists()


def test_unreviewed_release_publishes_to_shared_root_without_activation(prepared):
    data, parent, _ = prepared
    release.index_without_meaning_review(data, 'prepared', '의미 비교 보류')
    shared_root = data / 'shared'
    shared_root.mkdir()
    result = release.publish_shared_generation(parent / 'serving-unreviewed', shared_root)
    assert result['generation_path'] == str(shared_root / 'prepared/unreviewed/generation')
    assert result['published'] and not result['activated']
    assert release.main(['publish-shared', '--release', str(parent / 'serving-unreviewed'),
                         '--shared-root', str(shared_root)]) == 0
    assert not (data / 'generations/CURRENT.json').exists()


@pytest.mark.parametrize('target', ['source', 'glossary', 'audit'])
def test_skip_rejects_changed_inputs_and_audit(prepared, target):
    data, parent, raw = prepared
    if target == 'audit':
        release.index_without_meaning_review(data, 'prepared', '보류')
        p = parent / 'serving-unreviewed/source-selection.json'
        p.write_text(p.read_text() + ' ')
        with pytest.raises(ValueError, match='audit changed'):
            release.verify_release(parent / 'serving-unreviewed')
    else:
        p = parent / ('sources/store.sqlite' if target == 'source' else 'glossary-draft/dictionary.sqlite')
        with p.open('ab') as f:
            f.write(b'drift')
        with pytest.raises(ValueError):
            release.index_without_meaning_review(data, 'prepared', '보류')


def test_cli_explicit_skip_keeps_default_review_gate(prepared, term_glossary, monkeypatch, capsys):
    data, parent, _ = prepared
    monkeypatch.setattr(genos_stages, 'offline_data_root', lambda *a: data)
    with pytest.raises(ValueError, match='review to completion'):
        release.main(['index', '--run-id', 'prepared', '--glossary-dir', str(term_glossary)])
    with pytest.raises(SystemExit):
        release.main(['index', '--run-id', 'prepared', '--skip-meaning-review'])
    assert release.main(['index', '--run-id', 'prepared', '--skip-meaning-review', '--skip-review-reason', '정의 비교 보류']) == 0
    assert release.main(['verify', '--release', str(parent / 'serving-unreviewed')]) == 0


def test_partial_scope_and_old_compiler_lineage_are_preserved(failed_run, term_glossary):
    data = failed_run
    select(data)
    release.build(data, 'success', term_glossary, stage='prepare')
    parent = data / 'TERM_RELEASES/success'
    # A prepared generation may have been produced by the previously shipped code.
    path = parent / 'plan.json'
    plan = json.loads(path.read_text())
    plan['compiler_sha256'] = '0' * 64
    path.write_text(json.dumps(plan))
    result = release.index_without_meaning_review(data, 'success', '의미 검토 생략')
    assert result['structure_coverage']['omitted_count'] == 2
    assert result['structure_coverage']['selected_count'] == 1
    assert result['structure_coverage']['coverage'] == 'PARTIAL'
    release.verify_release(parent / 'serving-unreviewed')
