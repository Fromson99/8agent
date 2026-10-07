"""MAIN reference stage with scripted model responses; no network or quality scoring."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3

import pytest

from lawrag.pipeline import document_release, reference_resolution as resolution
from lawrag.pipeline.reference_model import MODEL, ROUTE, OpenRouterReferenceTransport
from semantic_runtime.contracts import sha
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.reference_resolution_repository import ReferenceResolutionRepository
from test_document_release import source, ReviewProvider


def scripted_model(tmp_path, monkeypatch, decision='select'):
    binding = {'provider': 'genos', 'model': 'synthetic-contract', 'trust_zone': 'internal',
               'adapter_version': 'genos-single-send-v1', 'endpoint_identity': '0' * 64,
               'max_input_bytes': 2000000}
    profile = tmp_path / 'reference-profile.json'
    profile.write_text(json.dumps({'model_binding': binding, 'max_output_tokens': 4096,
                                  'max_transport_retries': 0, 'max_schema_repairs': 0}))
    calls = []
    class Transport:
        def __init__(self): self.binding = binding
        def validate_model(self): return {'verified': True}
        def send_once(self, *, body, ticket):
            cases = json.loads(body['messages'][1]['content'])['view']['cases']
            calls.append(cases)
            rows = []
            for case in cases:
                ids = ([] if decision == 'abstain' else ['outside'] if decision == 'invalid'
                       else [c['id'] for c in case['candidates']] if decision == 'multi'
                       else [case['candidates'][0]['id']])
                rows.append({'case_id': case['case_id'], 'selected_candidate_ids': ids,
                             'evidence_ids': ['E1'], 'abstain_reason': '모의 기권' if not ids else None,
                             'explanation': '모의 선택'})
            return {'status_code': 200, 'body_json': {'model': binding['model'],
                    'choices': [{'message': {'content': json.dumps({'cases': rows})}}],
                    'usage': {'prompt_tokens': 1, 'completion_tokens': 1}}}
    monkeypatch.setattr(resolution.GenosTransport, 'from_environment', lambda binding: Transport())
    return profile, calls


def selected_input(tmp_path, monkeypatch):
    raw = source(tmp_path / 'input.sqlite', [
        ('internal:v1', '내규', ['관련 규정 제1조에 따른다.', '관련 규정 제1조를 확인한다.']),
        ('external:a', '가상규정A', ['첫 번째 후보']), ('external:b', '가상규정B', ['두 번째 후보'])])
    monkeypatch.setattr(document_release, 'selected_sources', lambda *args: ([raw], {str(raw): sha(raw)}))
    monkeypatch.delenv('REFERENCE_RESOLUTION_PROFILE', raising=False)
    return raw


@pytest.mark.parametrize('decision,state', [('select', 'APPROVED'), ('multi', 'APPROVED'), ('abstain', 'UNKNOWN')])
def test_main_build_automatically_finishes_selections_and_abstentions(tmp_path, term_glossary, monkeypatch, decision, state):
    selected_input(tmp_path, monkeypatch)
    profile, calls = scripted_model(tmp_path, monkeypatch, decision)
    result = document_release.build(tmp_path, 'automatic', term_glossary,
                                    provider=ReviewProvider(), reference_profile=profile)
    assert result['completed'] and result['reference_approval_mode'] == 'automatic'
    journal = tmp_path / 'TERM_RELEASES/automatic/reference-review'
    assert resolution.inspect(journal)['cases'][state] == 2
    with closing(ReferenceResolutionRepository(journal / 'review.sqlite')) as repo:
        assert {row[0] for row in repo.db.execute('SELECT reviewer FROM review')} == {'pipeline:auto-approve'}
        if decision == 'multi':
            assert {row[0] for row in repo.db.execute('SELECT resolution_state FROM observation')} == {'MULTI_TARGET'}
    release = Path(result['path'])
    assert document_release.verify_release(release)
    assert len(calls) == 1
    assert document_release.build(tmp_path, 'automatic', term_glossary,
                                  provider=ReviewProvider(), reference_profile=profile)['cached']
    assert len(calls) == 1
    assert not (tmp_path / 'generations/CURRENT.json').exists()
    assert not (Path(result['generation_path']) / 'review.sqlite').exists()


def test_budget_resume_and_index_never_calls_the_model(tmp_path, term_glossary, monkeypatch):
    selected_input(tmp_path, monkeypatch)
    profile, calls = scripted_model(tmp_path, monkeypatch)
    kwargs = {'provider': ReviewProvider(), 'reference_profile': profile, 'max_reference_cases': 1}
    pending = document_release.build(tmp_path, 'resumable', term_glossary, **kwargs)
    assert pending['status'] == 'REFERENCE_RESOLUTION_PENDING'
    assert pending['reference_resolution']['cases']['APPROVED'] == 1
    assert len(calls) == 1
    pending = document_release.build(tmp_path, 'resumable', term_glossary, stage='index', **kwargs)
    assert pending['status'] == 'REFERENCE_RESOLUTION_PENDING' and len(calls) == 1
    ready = document_release.build(tmp_path, 'resumable', term_glossary, stage='references', **kwargs)
    assert ready['status'] == 'REFERENCES_READY' and len(calls) == 2
    done = document_release.build(tmp_path, 'resumable', term_glossary, stage='index', **kwargs)
    assert done['completed'] and len(calls) == 2


def test_invalid_candidate_id_is_not_automatically_approved(tmp_path, term_glossary, monkeypatch):
    selected_input(tmp_path, monkeypatch)
    profile, calls = scripted_model(tmp_path, monkeypatch, 'invalid')
    with pytest.raises(Exception, match='outside the closed view'):
        document_release.build(tmp_path, 'invalid', term_glossary, provider=ReviewProvider(), reference_profile=profile)
    status = resolution.inspect(tmp_path / 'TERM_RELEASES/invalid/reference-review')
    assert status['cases']['MODEL_FAILED'] == 2
    assert status['reviews'] == {} and len(calls) == 1
    assert not (tmp_path / 'TERM_RELEASES/invalid/release.json').exists()


def test_no_new_filter_rejects_article_candidates_for_subarticle_mentions():
    reference = {'reason': 'DOCUMENT_NAME_UNRESOLVED', 'locator': '제4조제9항', 'document_id': 'source'}
    row = {'id': 'A4', 'document_id': 'target', 'document_name': '가상규정', 'heading': '제4조'}
    candidates = resolution.build_candidates(reference, [row], {'제4조': [row]})
    assert candidates[0]['target_source_id'] == 'A4' and candidates[0]['target_level'] == 'article'


def test_openrouter_route_and_public_scope_are_enforced(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    settings = json.loads((root / '00_SYSTEM/LEGAL_AGENT/reference-qwen-openrouter.json').read_text())
    grant = json.loads((root / '00_SYSTEM/LEGAL_AGENT/reference-qwen-public.json').read_text())
    grant.update(generation_id='synthetic', source_store_sha256='1' * 64, public_document_ids=['public'])
    grant_path = tmp_path / 'grant.json'; grant_path.write_text(json.dumps(grant))
    settings.update(export_grant='grant.json', export_grant_sha256=sha(grant_path))
    monkeypatch.setenv('OPEN_ROUTER', 'contract-test-key')
    transport = OpenRouterReferenceTransport(settings, tmp_path / 'profile.json')
    context = resolution.BuildContext({'reference_identity': {'generation_id': 'synthetic', 'source_store_sha256': '1' * 64},
                                        'reference_cases': [{'source': {'document_id': 'public'},
                                                             'candidates': [{'document_id': 'public'}]}]}, 0)
    transport.validate_authorization(context)
    request = transport.prepare_body({'model': MODEL, 'stream': False, 'chat_template_kwargs': {'enable_thinking': False}})
    assert request['provider'] == ROUTE and request['reasoning'] == {'effort': 'none'}
    assert 'chat_template_kwargs' not in request
    sent = []
    async def response(method, path, body, seconds, **kwargs):
        sent.append(body)
        return {'status_code': 200, 'body_json': {'model': MODEL, 'provider': 'Parasail',
                'choices': [{'finish_reason': 'stop', 'message': {'content': '{}'}}],
                'usage': {'completion_tokens_details': {'reasoning_tokens': 0}}}}
    monkeypatch.setattr(transport, '_request', response)
    assert transport.send_once(body=request, ticket={'remaining_seconds': 10})['status_code'] == 200
    assert sent == [request]
    context.binding['reference_cases'][0]['source']['document_id'] = 'internal'
    with pytest.raises(ContractError, match='outside the public'):
        transport.validate_authorization(context)
    context.binding['reference_cases'][0]['source']['document_id'] = 'public'
    context.binding['reference_identity']['source_store_sha256'] = '2' * 64
    with pytest.raises(ContractError, match='source generation'):
        transport.validate_authorization(context)


def test_scope_v2_overlay_preserves_navigation_schema(tmp_path, term_glossary, monkeypatch):
    selected_input(tmp_path, monkeypatch)
    monkeypatch.setenv('GENOS_REFERENCE_SCOPE_V2', '1')
    profile, calls = scripted_model(tmp_path, monkeypatch)
    result = document_release.build(tmp_path, 'scoped', term_glossary,
                                    provider=ReviewProvider(), reference_profile=profile)
    assert result['completed']
    manifest = json.loads((Path(result['generation_path']) / 'navigation/manifest.json').read_text())
    assert manifest['schema_version'] == 'term-navigation-index-v5'
    assert manifest['scope_contract'] == 'reference-scope-v2'
    assert document_release.verify_release(result['path'])


def test_profile_change_cannot_reuse_pending_run(tmp_path, term_glossary, monkeypatch):
    selected_input(tmp_path, monkeypatch)
    profile, calls = scripted_model(tmp_path, monkeypatch)
    document_release.build(tmp_path, 'pinned', term_glossary, provider=ReviewProvider(),
                           reference_profile=profile, max_reference_cases=1)
    settings = json.loads(profile.read_text()); settings['max_output_tokens'] += 1
    profile.write_text(json.dumps(settings))
    with pytest.raises(ValueError, match='Release inputs changed'):
        document_release.build(tmp_path, 'pinned', term_glossary, provider=ReviewProvider(), reference_profile=profile)
    assert len(calls) == 1
