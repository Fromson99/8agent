"""Final display contracts; no model calls, legal grading or search changes."""
from copy import deepcopy
import json

import pytest

from semantic_runtime.legal_agent import completion_contracts as cc
from semantic_runtime.legal_agent import narrative_answer as narrative
from semantic_runtime.legal_agent.errors import ContractError
from test_investigation_completion_adr0678 import assess, sources
from test_main50_request_repair import tree, GAP


def assessment(reason='검토 대상의 별도 승인 절차 원문을 확보하지 못했습니다.', target=''):
    gap = {'issue_id': 'Q1', 'kind': 'MISSING_SOURCE', 'reason': reason,
           'material_id': None, 'material': True, 'missing_target': target,
           'suggested_action': 'READ_SCOPE'}
    value, options, issues = assess([gap], 'PARTIAL')
    result = cc.materialize_assessment(value, options, issues)
    result['completion_contract'] = cc.V8
    return result, issues


def test_reason_without_target_reaches_answer_without_changing_judgment_or_model_input():
    a, _ = assessment(); before = deepcopy(a)
    wire = narrative.input_data('승인 기준은?', a, sources(), None)
    answer = cc.compose(a, cc.default_plan(a))
    assert before == a
    assert wire == narrative.input_data('승인 기준은?', a, sources(), None)
    assert '미확인 사유(AI 판단·검증 전): ' + a['gaps'][0]['reason'] in answer['text']
    assert answer['claims'] == a['claims'] and answer['limitations'] == a['limitations']
    cc.verify_composition(a, answer)


def test_distinct_unlocated_gaps_are_not_lost_to_identical_generic_text():
    a, issues = assessment()
    a['gaps'].append({**a['gaps'][0], 'reason': '예외에 관한 원문을 확보하지 못했습니다.'})
    cc.refresh_limitations(a, issues)
    text = cc.compose(a, cc.default_plan(a))['text']
    assert all(g['reason'] in text for g in a['gaps'])


@pytest.mark.parametrize('status', ['NOT_NEEDED', 'NOT_AVAILABLE', 'UNRESOLVED'])
def test_closed_gap_preserves_status_and_labels_reason_as_historical(status):
    a, issues = assessment(target='검토규정 제8조')
    cc.refresh_limitations(a, issues, closed={cc.gap_key(a['gaps'][0]): status})
    text = cc.compose(a, cc.default_plan(a))['text']
    assert '검토규정 제8조' in text and cc.CLOSED_WORDS[status] in text
    assert '당시 미확인 사유(AI 판단·검증 전)' in text


@pytest.mark.parametrize('reason,material', [('', True), ('별도 참고 사항', False)])
def test_missing_or_nonmaterial_reason_does_not_invent_a_limitation(reason, material):
    a, issues = assessment(reason)
    a['gaps'][0]['material'] = material
    cc.refresh_limitations(a, issues)
    text = cc.compose(a, cc.default_plan(a))['text']
    assert 'AI 판단' not in text


def test_reason_is_literal_text_not_html_link_or_new_heading():
    a, _ = assessment('<img src=x>\n# [확인](https://example.test) **완료**')
    text = cc.compose(a, cc.default_plan(a))['text']
    assert '<img' not in text and '&lt;img' in text
    assert '\n# ' not in text and '[확인](' not in text and '**완료**' not in text


@pytest.mark.parametrize('version', cc.KNOWN)
def test_saved_legacy_plan_keeps_exact_historical_rendering(version):
    a, _ = assessment(); a['completion_contract'] = version
    plan = cc.default_plan(a)
    old = cc.compose(a, plan)
    old['composition_plan'].pop('gap_reason_presentation', None)
    old['text'] = cc.render(a, old['composition_plan'])
    assert 'AI 판단' not in old['text']
    cc.verify_composition(a, old)


def test_changed_reason_text_or_unknown_presentation_cannot_publish():
    a, _ = assessment(); answer = cc.compose(a, cc.default_plan(a))
    answer['text'] = answer['text'].replace(a['gaps'][0]['reason'], '확인이 완료되었습니다.')
    with pytest.raises(ContractError): cc.verify_composition(a, answer)
    with pytest.raises(ContractError): cc.render(a, {**cc.default_plan(a), 'gap_reason_presentation': 'unknown'})


def test_streamed_narrative_keeps_prefix_and_appends_exact_reason_suffix():
    a, _ = assessment(); sent = []
    value = {'paragraphs': [{'claim_ids': ['C1'], 'text': '확인된 모의 규칙을 설명합니다.'}]}
    stream = narrative.TokenStream(sent.append, ['C1'])
    raw = json.dumps(value, ensure_ascii=False)
    for start in range(0, len(raw), 5): stream.feed(raw[start:start + 5])
    answer = cc.compose(a, narrative.plan(a, value))
    prefix = ''.join(sent)
    assert prefix == value['paragraphs'][0]['text'] and answer['text'].startswith(prefix)
    assert a['gaps'][0]['reason'] in answer['text'][len(prefix):]
    cc.verify_composition(a, answer)


@pytest.mark.parametrize('fail', [False, True])
def test_native_streaming_partial_answer_preserves_details_and_reuse(tmp_path, tree, fail):
    from fastapi.testclient import TestClient
    from semantic_runtime.app import create_app
    from semantic_runtime.legal_agent.answer_stream import capture
    from test_narrative_answer import RichTransport
    from test_bounded_source_main import settings
    from test_legal_agent_double_harness import ROOT
    gen, idx = tree; tokens = []; transport = RichTransport(tokens, fail)
    transport.reentry = True
    profile = {**settings(), 'max_model_attempts': 40, 'max_read_chars': 10000,
        'final_review_enabled': False, 'answer_presentation': narrative.VERSION,
        'candidate_navigation': {'mode': 'law-first-v1', 'investigation_control': True,
            'completion_contract': True, 'completion_policy_version': cc.V8,
            'compact_input': True, 'assessment_reentry_limit': 0}}
    app = create_app(tmp_path, gen, contracts_root=ROOT, provider=object(),
        implementation='legal-agent-unified-v6', legal_agent_profile=profile,
        legal_agent_transport=transport, runtime_root=tmp_path/'runtime',
        memory_identity=lambda _: {'user_id': 'synthetic', 'team_id': 'test_team', 'document_ids': ['d']})
    app.state.pipeline.term_agent.unit_fulltext = idx
    body = {'question': '모의승인규정 제1조 승인 기준은?', 'session_id': 'gap-reason', 'request_id': 'r1'}
    with TestClient(app) as api:
        with capture('r1', tokens.append): response = api.post('/v1/rag/ask', json=body)
        assert transport.streamed and transport.compose_calls == 1 and tokens
        if fail:
            assert response.status_code != 200
            assert 'AI 판단·검증 전' not in ''.join(t['text'] for t in tokens)
            return
        assert response.status_code == 200, response.text
        out = response.json()
        assert out['answer']['text'] == ''.join(t['text'] for t in tokens)
        assert GAP['reason'] in out['answer']['text'] and 'AI 판단·검증 전' in out['answer']['text']
        assert out['assembly']['term_agent']['answer_coverage'] == 'PARTIAL'
        calls = len(transport.phases)
        repeated = api.post('/v1/rag/ask', json=body)
        assert repeated.status_code == 200 and repeated.json()['answer'] == out['answer']
        assert len(transport.phases) == calls and transport.compose_calls == 1
