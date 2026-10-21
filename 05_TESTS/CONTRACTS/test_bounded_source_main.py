"""Serving wiring contracts on synthetic originals; no model quality claim."""
import json
import pytest
from conftest import term_glossary
from test_legal_agent_double_harness import generation, wire
from test_legal_agent_v5 import app_for, PROFILE, plan
from semantic_runtime.legal_agent.errors import TransportError
from semantic_runtime.legal_agent.bounded_source_session import BoundedSourceSession
from semantic_runtime.legal_agent.source_bundle import validate_current
from semantic_runtime.legal_agent import obligation_protocol
from semantic_runtime.legal_agent.source_selection import originals


class Transport:
    binding = PROFILE['model_binding']
    def __init__(self, fail=False, *, browse=False):
        self.calls = []
        self.fail = fail
        self.browse = browse

    def validate_model(self):
        return {'verified': True, 'synthetic': True}

    def send_once(self, *, body, ticket):
        self.calls.append(body)
        v = json.loads(body['messages'][1]['content'])['view']
        phase = v.get('source_stage', v['phase'])
        if phase == 'source-query-plan':
            browse = self.browse
            return wire({'mode': 'BROWSE' if browse else 'SEARCH',
                         'law_names': [] if browse else ['모의승인규정'],
                         'queries': [] if browse else ['모의승인규정 제1조', '모의승인규정 제2조'],
                         'answer': '', 'reason': '허용 목록 조회' if browse else '승인 대상과 예외 원문 필요',
                         'document_category': 'all', 'browse_view': 'documents',
                         'title_query': '', 'inspect_documents': False})
        if phase == 'source-triage':
            if self.fail:
                raise TransportError('synthetic provider failure')
            return wire({'issues': ['승인 예외'], 'choices': [{'id': v['candidates']['rows'][0][0], 'reason': '승인 원칙 확인'}]})
        if phase == 'source-omission-review':
            return wire({'issues': [], 'choices': [{'id': v['deferred_candidates']['rows'][0][0], 'reason': '승인 예외 복구'}]})
        if phase == 'bounded-question-plan':
            return wire(plan())
        if phase == 'compose':
            return wire({'paragraphs': [{'text': '모의 승인 대상이며 위임 예외를 확인해야 합니다.',
                'evidence': [e['evidence'] for e in v['exact_evidence']],
                'question_refs': v['question_plan']['demands'][0]['question_refs'],
                'fact_dependencies': [], 'relation_dependencies': [],
                'obligation_refs': [v['question_plan']['demands'][0]['id']]}], 'limitations': []})
        if phase == 'review':
            c = v['claims'][0]
            return wire({'checks': [{'claim': c['claim'], 'verdict': 'SUPPORTED',
                'evidence': c['evidence'], 'issue': '원문 일치', 'reason': '모의 원문 확인',
                'actions': [], 'relation_checks': [], 'source_checks': [{
                    'source': eid, 'quote': next(e for e in v['exact_evidence'] if e['evidence'] == eid)['text'],
                    'draft_quote': c['text'],
                    'dimensions': {k: 'PRESERVED' for k in obligation_protocol.DIMENSIONS},
                    'reason': '원문 조건과 초안 대조'} for eid in c['evidence']]}],
                'question': {'status': 'RESOLVED',
                    'question_refs': v['question_plan']['demands'][0]['question_refs'], 'reason': '분류 확인'},
                'obligation_checks': [{'obligation': d['id'],
                    'status': 'ANSWERED' if i == 0 else 'MISSING_FACT',
                    'claims': [c['claim']] if i == 0 else [],
                    'reason': '분류 확인' if i == 0 else '신청서 제출 사실 필요', 'actions': []}
                    for i, d in enumerate(v['question_plan']['demands'])]})
        raise AssertionError(phase)


def settings():
    return {**PROFILE, 'bounded_source_selection_enabled': True, 'max_tool_actions': 1024,
            'max_core_sources': 24, 'max_supplemental_sources': 24}


def test_real_recall_selection_recovery_and_bundle(tmp_path, generation):
    transport = Transport()
    app = app_for(tmp_path, generation, transport, settings())
    p = app.state.pipeline
    try:
        request = {'question': '모의승인규정의 승인 대상과 예외는?', 'document_ids': ['d'], 'use_llm': True}
        with p.term_agent.open_session(request, query=p.plan(request['question'], ['d']), runtime=tmp_path/'runtime') as s:
            assert isinstance(s, BoundedSourceSession)
            retrieved = s.investigate()
            assert not s.limitations, s.limitations
            selected = s.source_selection_record
            assert len(selected['first_ids']) == 1
            assert len(selected['recovered_ids']) == 1
            assert set(selected['final_ids']) == set(s.source_recall_record['read_complete'])
            assert s.work.budget()['model_reserved'] == 4
            packed = s.select({'retrieval': retrieved})
            assert {x['id'] for x in packed['selected']} == set(selected['final_ids'])
            assert all(e['document_id'] == 'd' for e in s.work.evidence())
            # Inventory/excerpt calls must not claim full-source delivery.
            assert s.work.db.execute('SELECT count(*) FROM presentation').fetchone()[0] == 0
            bundle = s.build_bundle()
            validate_current(s.work, {'assembly': {'term_agent': {'source_bundle': bundle}}}, s.sources.store)
            assert {c['source_id'] for c in bundle['sources']} == set(selected['final_ids'])
            before = len(transport.calls)
            s.investigate()
            assert len(transport.calls) == before
    finally:
        p.store.close()


def test_provider_failure_does_not_adopt_entire_pool(tmp_path, generation):
    transport = Transport(fail=True)
    app = app_for(tmp_path, generation, transport, settings())
    p = app.state.pipeline
    try:
        request = {'question': '모의승인규정의 승인 대상은?', 'document_ids': ['d'], 'use_llm': True}
        with p.term_agent.open_session(request, query=p.plan(request['question'], ['d']), runtime=tmp_path/'runtime') as s:
            s.investigate()
            assert s.work.evidence()
            assert not s.work.heads('source_selection', current=True)
            assert s.limitations
            assert len(transport.calls) == 2
    finally:
        p.store.close()


def test_many_pages_of_selected_originals_are_not_capped_at_twenty(tmp_path, generation):
    app = app_for(tmp_path, generation, Transport(), {**settings(), 'max_read_chars': 2})
    p = app.state.pipeline
    try:
        request = {'question': '모의승인규정의 승인 대상과 예외는?', 'document_ids': ['d'], 'use_llm': True}
        with p.term_agent.open_session(request, query=p.plan(request['question'], ['d']), runtime=tmp_path/'runtime') as s:
            retrieved = s.investigate()
            assert not s.limitations, s.limitations
            selected = s.select({'retrieval': retrieved})
            bundle = s.build_bundle()
            assert len(bundle['sources']) > 20
            assert len(s.packed['evidence_ids']) == len(bundle['sources'])
            assert {r['id'] for r in selected['selected']} == set(s.source_selection_record['final_ids'])
            assert all(r['text'] == originals(s.source_recall_record)[r['id']]['text'] for r in selected['selected'])
            assert {c['source_id'] for c in bundle['sources']} == set(s.source_selection_record['final_ids'])
            validate_current(s.work, {'assembly': {'term_agent': {'source_bundle': bundle}}}, s.sources.store)
    finally:
        p.store.close()


def test_source_only_bypasses_query_planner(tmp_path, generation):
    transport = Transport()
    app = app_for(tmp_path, generation, transport, settings())
    p = app.state.pipeline
    try:
        request = {'question': '자료 목록', 'document_ids': ['d'], 'use_llm': False}
        with p.term_agent.open_session(request, query=p.plan(request['question'], ['d']), runtime=tmp_path/'runtime') as s:
            s.investigate()
            assert s.metadata_only
            assert transport.calls == []
    finally:
        p.store.close()


@pytest.mark.parametrize('numbered', [True])
@pytest.mark.parametrize('review_enabled', [False, True])
def test_ask_endpoint_publishes_recovered_originals(tmp_path, generation, numbered, review_enabled):
    transport = Transport()
    app = app_for(tmp_path, generation, transport,
                  {**settings(), 'numbered_references_enabled': numbered, 'final_review_enabled': review_enabled})
    try:
        ask = next(r.endpoint for r in app.routes if r.path == '/v1/rag/ask')
        result = ask({'question': '모의승인규정의 승인 대상과 위반 여부는?', 'document_ids': ['d']})
        assert result['answer']['claims'], result['answer']
        meta = result['assembly']['term_agent']
        assert len(meta['source_bundle']['sources']) == 2
        assert [i['status'] for i in meta['question_obligations']['items']] == (['ANSWERED', 'MISSING_FACT'] if review_enabled else ['OPEN', 'OPEN'])
        if review_enabled:
            assert '신청서 제출' in result['answer']['text']
        else:
            assert result['answer']['text'] == '모의 승인 대상이며 위임 예외를 확인해야 합니다.'
            assert result['answer']['provider_receipt']['final_review_status'] == 'SKIPPED'
            assert set(result['answer']['provider_receipt']['claim_review_status'].values()) == {'UNREVIEWED'}
            assert not result['answer']['unresolved']
        phases = [json.loads(b['messages'][1]['content'])['view'] for b in transport.calls]
        assert [v.get('source_stage', v['phase']) for v in phases] == [
            'source-query-plan', 'source-triage', 'source-omission-review',
            'bounded-question-plan', 'compose'] + (['review'] if review_enabled else [])
    finally:
        app.state.pipeline.store.close()
