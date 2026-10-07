"""Completed input reuse through serving assets and the offline generation gate."""
import io
import json
from pathlib import Path
import sys
import pytest
from semantic_runtime.contracts import sha
from test_genos_meaning_variants import prepared

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '06_TOOLS/OFFLINE'))
import genos_reindex_only as index
import genos_reindex_runner as runner
from genos_reindex_logging import BuildLog


@pytest.mark.parametrize('storage_profile', ['legacy', 'compact-v1'])
@pytest.mark.parametrize('granularity', ['article', 'unit'])
def test_prepared_full_serving_reuse_preserves_inputs_and_resume(prepared, tmp_path, monkeypatch, granularity, storage_profile):
    from lawrag.pipeline import glossary_review, reference_resolution, term_generation
    from semantic_runtime.fulltext import open_index
    from contextlib import closing
    def forbidden(*a, **k):
        raise AssertionError('Completed authoring and model review must be reused')
    monkeypatch.setattr(glossary_review, 'complete', forbidden)
    monkeypatch.setattr(reference_resolution, 'advance', forbidden)
    monkeypatch.setattr(reference_resolution, 'apply', forbidden)
    context = index.prepared(tmp_path, 'prepared')
    before = dict(context['pins'])
    context.update(code_root=ROOT, reindex_policy='prepared-reuse-serving-v1')
    context['reindex_settings'].update(serving=True, fulltext_granularity=granularity, storage_profile=storage_profile)
    manifest = tmp_path / 'code.json'; manifest.write_text('{}')
    context = runner.fork_prepared(context, tmp_path, 'new-serving', manifest)
    log = BuildLog(tmp_path / 'log', terminal=io.StringIO())
    try:
        result = runner.rebuild(context, log=log)
        assert result['completed'] and result['serving_verified'] and result['model_calls'] == 0
        assert result['offline_e2e'] == 'PASS' and result['live_workflow_e2e'] == 'NOT_RUN'
        assert not result['activated'] and not (tmp_path / 'generations/CURRENT.json').exists()
        generation = Path(result['generation_path'])
        navigation = json.loads((generation / 'navigation/manifest.json').read_text())
        search = open_index(generation / 'fulltext', navigation)
        with closing(search.connect()) as db:
            assert search.rank(db, ['은행'])
        assert all(sha(p) == expected for p, expected in before.items())
        repeated = runner.rebuild(context, log=log)
        assert repeated == result
        shared = tmp_path / 'shared'; shared.mkdir()
        publication = index.publish_serving(context, shared, log=log)
        assert publication['published'] and not publication['activated']
        assert index.publish_serving(context, shared, log=log) == publication
        assert not (shared / 'CURRENT.json').exists()
        with (Path(publication['generation_path']) / 'store.sqlite').open('ab') as stream:
            stream.write(b'tampered')
        with pytest.raises(ValueError, match='Shared generation differs'):
            index.publish_serving(context, shared, log=log)
        # A completed output is validated again, never silently accepted by presence.
        ft = generation / 'fulltext' / ('units.sqlite' if granularity == 'unit' else 'fulltext.sqlite')
        with ft.open('ab') as stream: stream.write(b'tampered')
        with pytest.raises(ValueError): runner.rebuild(context, log=log)
    finally:
        log.close(0)


def test_prepared_serving_requires_full_knowledge_and_explicit_granularity(prepared, tmp_path):
    context = index.prepared(tmp_path, 'prepared')
    context['reindex_settings'].update(serving=True, fulltext_granularity='unit')
    context['knowledge'] = None
    log = BuildLog(tmp_path / 'log', terminal=io.StringIO())
    try:
        with pytest.raises(ValueError, match='full knowledge'):
            runner.rebuild(context, log=log)
        assert not (context['parent'] / 'serving').exists()
    finally: log.close(0)
    with pytest.raises(SystemExit):
        runner.arguments(['build', '--dev', str(ROOT), '--data-root', str(tmp_path),
            '--prepared-run', 'prepared', '--run-id', 'new', '--code-manifest', str(tmp_path / 'code.json'),
            '--log-dir', str(tmp_path / 'log'), '--serving'])


def test_select_completed_review_reuses_exact_dictionary_without_calls(prepared, tmp_path, monkeypatch):
    from lawrag.pipeline import glossary_review
    from test_document_release import ReviewProvider
    selected = tmp_path / 'reviewed'
    completion = glossary_review.complete(prepared['draft'], tmp_path / 'finished-review', selected,
                                          max_jobs=100, provider=ReviewProvider())
    assert completion['completed']
    def forbidden(*a, **k): raise AssertionError('Do not rerun completed meaning review')
    monkeypatch.setattr(glossary_review, 'complete', forbidden)
    context = index.select_completed_glossary(index.prepared(tmp_path, 'prepared'), selected)
    assert context['draft'] == selected
    assert context['reindex_settings']['reused_review_status'] == completion['review_status']
    assert context['pins'][str(selected / 'dictionary.sqlite')] == completion['dictionary_sha256']
    context['code_root'] = ROOT
    context['reindex_settings'].update(serving=True, fulltext_granularity='unit')
    manifest = tmp_path / 'code.json'; manifest.write_text('{}')
    context = runner.fork_prepared(context, tmp_path, 'reviewed-reuse', manifest)
    log = BuildLog(tmp_path / 'log-reviewed', terminal=io.StringIO())
    try:
        result = runner.rebuild(context, log=log)
        assert result['offline_e2e'] == 'PASS'
        copied = Path(result['generation_path']) / 'glossary/dictionary.sqlite'
        assert sha(copied) == completion['dictionary_sha256']
    finally: log.close(0)
