"""Reference-resolution journal and immutable overlay contracts; no live model calls."""
from contextlib import closing
import json
import sqlite3

import pytest

from lawrag.pipeline.reference_resolution import apply, inspect, prepare
from lawrag.pipeline.term_generation import build_generation
from lawrag.pipeline.term_serving_bundle import verify_assets
from semantic_runtime.contracts import sha
from semantic_runtime.reference_resolution_repository import ReferenceResolutionRepository
from semantic_runtime import reference_resolution_protocol as protocol
from test_document_release import source


def test_server_cardinality_and_closed_ids():
    cases = [{'case_id': 'c', 'candidates': [{'id': 'T1'}, {'id': 'T2'}],
              'evidence': [{'id': 'E1'}]}]
    value = {'cases': [{'case_id': 'c', 'selected_candidate_ids': ['T1', 'T2'],
                        'evidence_ids': ['E1'], 'abstain_reason': None, 'explanation': '둘 다 명시됨'}]}
    assert protocol.validate_batch(value, cases)[0]['resolution_state'] == 'MULTI_TARGET'


def test_observation_requires_a_successful_physical_attempt(tmp_path):
    identity = {'generation': 'synthetic', 'navigation_sha256': '0' * 64}
    case = {
        'case_id': 'C1', 'reference_id': 'R1', 'binding_hash': '1' * 64,
        'source': {'mention_text': '관련 규정'},
        'parse': {'kind': 'DOCUMENT_NAME_UNRESOLVED', 'current_reason': 'ambiguous'},
        'candidates': [{'id': 'T1', 'basis': 'exact_title', 'document_name': '관련 규정'}],
        'evidence': [{'id': 'E1', 'kind': 'mention', 'text': '관련 규정'}],
        'candidate_set_sha256': '2' * 64,
    }
    journal = tmp_path / 'review.sqlite'
    with closing(ReferenceResolutionRepository(journal, identity=identity, max_model_attempts=1)) as repo:
        repo.add_case(case, 'CANDIDATES_READY')
        view = repo.save_view([repo.case_view('C1')])
        rows = protocol.validate_batch({'cases': [{
            'case_id': 'C1', 'selected_candidate_ids': ['T1'], 'evidence_ids': ['E1'],
            'abstain_reason': None, 'explanation': 'synthetic',
        }]}, [case])
        with pytest.raises(Exception, match='no successful physical attempt'):
            repo.store_observations(view['view_id'], rows)
        abstained = {'cases': [{
            'case_id': 'C1', 'selected_candidate_ids': [], 'evidence_ids': ['E1'],
            'abstain_reason': 'insufficient evidence', 'explanation': 'synthetic',
        }]}
        attempt = repo.reserve_attempt(view, {'model': 'synthetic-contract'}, 'L1', 1, 'reference_resolution')
        repo.attempt_sent(attempt)
        repo.finish_attempt(attempt, 'SUCCEEDED', {'body_json': abstained},
                            {'model': 'synthetic-contract', 'usage': None})
        repo.store_observations(view['view_id'], protocol.validate_batch(abstained, [case]))
        with pytest.raises(Exception, match='abstained observation cannot be approved'):
            repo.review_case('C1', 'APPROVE', 'contract-reviewer', 'must not approve an abstention')


@pytest.mark.parametrize('archived_audit', [False, True])
def test_prepare_review_and_apply_builds_a_new_generation(tmp_path, term_glossary, archived_audit):
    original = source(tmp_path / 'source.sqlite', [
        ('internal:v1', '내부규정', ['관련 규정 제1조에 따른다.']),
        ('external:a', '가상규정A', ['첫 번째 후보 원문']),
        ('external:b', '가상규정B', ['두 번째 후보 원문'])])
    build_generation(original, term_glossary, tmp_path / 'built', serving=True)
    if archived_audit:
        from semantic_runtime.navigation_storage import archive_audit
        archive_audit(tmp_path / 'built/audit/navigation')
    generation = tmp_path / 'built/generation'
    parent_hash = sha(generation / 'navigation/navigation.sqlite')
    plan = prepare(generation, tmp_path / 'reference-review', max_model_attempts=4)
    assert plan['live_model_calls'] == 0
    assert plan['cases']['CANDIDATES_READY'] == 1

    journal = tmp_path / 'reference-review/review.sqlite'
    with closing(ReferenceResolutionRepository(journal)) as repo:
        case_row = repo.cases(('CANDIDATES_READY',))[0]
        case = repo.case_view(case_row['case_id'])
        chosen = next(candidate for candidate in case['candidates']
                      if candidate['document_name'].endswith('가상규정A'))
        view = repo.save_view([case])
        output = {'cases': [{'case_id': case['case_id'], 'selected_candidate_ids': [chosen['id']],
                             'evidence_ids': ['E1'], 'abstain_reason': None,
                             'explanation': '모의 observation'}]}
        attempt = repo.reserve_attempt(view, {'model': 'synthetic-contract'}, 'L1', 1, 'reference_resolution')
        repo.attempt_sent(attempt)
        repo.finish_attempt(attempt, 'SUCCEEDED', {'body_json': output},
                            {'model': 'synthetic-contract', 'usage': None})
        repo.store_observations(view['view_id'], protocol.validate_batch(output, [case]))
        repo.review_case(case['case_id'], 'APPROVE', 'contract-reviewer', '모의 계약 승인')

    result = apply(tmp_path / 'reference-review', generation, tmp_path / 'reviewed/generation')
    assert result['approved_cases'] == 1
    from lawrag.pipeline.document_release import _copy_reference_audit, _verify_navigation_audit
    from semantic_runtime.navigation_storage import verify_build
    overlay = tmp_path / 'reviewed'
    audit = _copy_reference_audit(tmp_path / 'built', overlay)
    generated = json.loads((overlay / 'generation/manifest.json').read_text())
    built = json.loads((tmp_path / 'built/result.json').read_text())
    built.update(manifest_sha256=sha(overlay / 'generation/manifest.json'),
                 navigation=generated['navigation'], navigation_audit=audit)
    (overlay / 'result.json').write_text(json.dumps(built))
    assert verify_build(overlay)
    _verify_navigation_audit(overlay)
    assert sha(generation / 'fulltext/fulltext.sqlite') == sha(overlay / 'generation/fulltext/fulltext.sqlite')
    assert sha(generation / 'fulltext/manifest.json') != sha(overlay / 'generation/fulltext/manifest.json')
    baseline_audit = json.loads((tmp_path / 'built/audit/navigation/manifest.json').read_text())
    assert baseline_audit['audit_sha256'] == sha(overlay / 'audit/navigation/navigation.sqlite')
    assert not list((tmp_path / 'built/audit').glob('.audit-restore-*'))
    proof = json.loads((overlay / 'audit/navigation/manifest.json').read_text())
    assert proof['parent_audit_manifest_sha256'] == sha(tmp_path / 'built/audit/navigation/manifest.json')
    assert proof['reference_resolution_parent_index_sha256'] == parent_hash
    assert verify_assets(tmp_path / 'reviewed/generation')['verified']
    assert sha(generation / 'navigation/navigation.sqlite') == parent_hash
    assert not (tmp_path / 'reviewed/generation/reference-review.sqlite').exists()
    assert (tmp_path / 'reviewed/generation/navigation/reference-resolution-apply.json').is_file()
    with sqlite3.connect(tmp_path / 'reviewed/generation/navigation/navigation.sqlite') as db:
        reference = json.loads(db.execute("SELECT json FROM reference WHERE json_extract(json,'$.resolution')="
                                          "'REVIEWED_MODEL_SELECTION'").fetchone()[0])
        assert reference['resolution_state'] == 'RESOLVED'
        assert reference['resolution_basis'] == 'reviewed_model_observation'
        assert len(reference['targets']) == 1
        assert db.execute('SELECT count(*) FROM reference_candidate').fetchone()[0] >= 2
        assert db.execute('SELECT count(*) FROM reference_target WHERE reference_id=?',
                          (reference['id'],)).fetchone()[0] == 1
    status = inspect(tmp_path / 'reference-review')
    assert status['cases']['APPROVED'] == 1
