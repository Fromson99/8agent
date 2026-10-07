"""Authoring/publishing verifies retained evidence; serving stays independent."""
import json

import pytest

from lawrag.pipeline import document_release
from test_document_release import ReviewProvider
from test_document_release_stages import failed_run, select


@pytest.mark.parametrize('reviewed', [False, True])
def test_release_and_publish_reject_audit_drift(failed_run, term_glossary, tmp_path, reviewed):
    select(failed_run)
    document_release.build(failed_run, 'success', term_glossary, stage='prepare')
    if reviewed:
        document_release.build(failed_run, 'success', term_glossary, stage='review', provider=ReviewProvider())
        result = document_release.build(failed_run, 'success', term_glossary, stage='index')
    else:
        result = document_release.index_without_meaning_review(failed_run, 'success', reason='contract fixture')
    release = tmp_path / 'TERM_RELEASES/success'
    if not reviewed:
        release = release / 'serving-unreviewed'
    generation, _ = document_release.verify_release(release)
    assert result['completed'] and generation.exists()
    with (release / 'serving/audit/navigation/manifest.json').open('a') as stream:
        stream.write(' ')
    with pytest.raises(ValueError, match='audit manifest changed'):
        document_release.verify_release(release)
    shared = tmp_path / 'shared'; shared.mkdir()
    with pytest.raises(ValueError, match='audit manifest changed'):
        document_release.publish_shared_generation(release, shared)
    assert not list(shared.iterdir())


def test_result_cannot_omit_existing_navigation_audit(failed_run, term_glossary, tmp_path):
    select(failed_run)
    document_release.build(failed_run, 'success', term_glossary, stage='prepare')
    document_release.index_without_meaning_review(failed_run, 'success', reason='contract fixture')
    serving = tmp_path / 'TERM_RELEASES/success/serving-unreviewed/serving'
    path = serving / 'result.json'
    result = json.loads(path.read_text()); result.pop('navigation_audit')
    path.write_text(json.dumps(result))
    with pytest.raises(ValueError, match='Missing compact navigation audit receipt'):
        document_release._verify_navigation_audit(serving)
