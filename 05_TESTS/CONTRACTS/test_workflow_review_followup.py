"""Unresolved answers ask for clarification while preserving review and sources."""
import asyncio
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from semantic_runtime import chat_adapter
from semantic_runtime.legal_agent import review_explanation as review
from test_genos_source_accordion import body, rendered


def failed_reply():
    response = body()
    response['answer'].update(text='확인한 원문을 제공합니다.\n\n**확인한 원문: 모의규정**\n\n> 원문 중복',
                             claims=[], unresolved=[{'reason': '미확인 사유(AI 판단·검증 전): 적용 범위 검토가 남았습니다.'}])
    response['assembly']['context'] = response['assembly']['context'][:1]
    assessment = {'claims': [], 'source_excerpt_reply': {'verified': True},
        'model_proposal': {'review_status': 'INCOMPLETE', 'failure_code': 'ASSESSMENT_CONTRACT_UNRESOLVED',
                          'failure': {'category': 'FINAL_READ_REVIEW_INVALID', 'repairable': True,
                                      'issues': [{'code': 'SCOPE_USE_UNSUPPORTED_RANGE'}]}}}
    view = review.bind_case(review.build(assessment, []), {'question_id': 'g1', 'revision': 1, 'route_id': 'r1'})
    response['assembly']['term_agent'] = {'source_reply_contract': 'verified-source-excerpt-reply-v1',
        'text_integrity': 'VERIFIED_SOURCE_EXCERPTS', 'completion_contract': 'investigation-completion-v8',
        'answer_coverage': 'INSUFFICIENT', 'stop_reason': 'ASSESSMENT_CONTRACT_UNRESOLVED',
        'review_explanation': view}
    return response


def test_source_only_asks_conversationally_and_keeps_closed_exact_originals():
    w = chat_adapter.views(); response = failed_reply(); before = deepcopy(response)
    text = w._for_markdown(w.render(response)); dom = rendered(text)
    assert '원문 중복' not in text and '**확인한 원문:' not in text
    assert '상황의 적용 여부는 아직 확인이 필요합니다.' in text
    public = w._public_answer_text(response)
    assert '모의규정' not in public and '원문의 첫 문장' not in public
    assert '어떤 대상이나 상황' in text and '설명해 주시겠어요?' in text
    assert '검토 다시 하기' not in public
    assert text.index('설명해 주시겠어요?') < text.index('GENOS_SOURCES_START')
    for diagnostic in ('답변 검토에서 실패한 부분', '아직 확인하지 못한 내용',
                       '실제 답 문장에는 쓰이지 않은 부분', 'AI 판단'):
        assert diagnostic not in text
    assert '실제 답 문장에는 쓰이지 않은 부분' in w._review_explanation_text(response, diagnostics=True)
    assert not dom.select('details[open]')
    assert len(dom.select('[data-source-text]')) == 1
    assert dom.select_one('[data-source-text]').get_text() == response['assembly']['context'][0]['text']
    assert w._completion_answer_status(response, True) == 'partial'
    assert response == before


@pytest.mark.parametrize('fault', ['untyped', 'accepted', 'missing_original'])
def test_no_text_heuristic_or_accepted_answer_suppression(fault):
    w = chat_adapter.views(); response = failed_reply()
    if fault == 'untyped': response['assembly']['term_agent'].pop('source_reply_contract')
    if fault == 'accepted': response['answer']['claims'] = [{'source_ids': ['used'], 'text': '검증된 답변'}]
    if fault == 'missing_original': response['assembly']['context'][0].pop('text')
    assert '원문 중복' in w.render(response)


def test_invalid_review_projection_and_error_never_leak_raw_failure_or_sources():
    w = chat_adapter.views(); response = failed_reply()
    response['assembly']['term_agent']['review_explanation']['failed_checks'][0]['reason'] = 'UNTRUSTED'
    response['failure'] = {'detail': 'PRIVATE_TRACEBACK'}
    text = w.render(w.public_response(response))
    assert 'UNTRUSTED' not in text and 'PRIVATE_TRACEBACK' not in text
    response['_gateway_status'] = 403
    text = w.render(response)
    assert '원문의 첫 문장' not in text and '같은 대화에서 이어서' not in text


def test_failure_messages_are_literal_and_do_not_replace_missing_fact():
    w = chat_adapter.views(); response = failed_reply()
    view = response['assembly']['term_agent']['review_explanation']
    view['failed_checks'][0]['reason'] = '<script>bad</script> ![image](https://invalid.test/pixel)'
    view['actions'].append({'kind': 'REQUEST_FACT', 'actor': 'USER', 'enabled': True, 'fact_name': '실제 승인일을 알려주세요.'})
    view = review.seal({k: v for k, v in view.items() if k != 'content_sha256'})
    response['assembly']['term_agent']['review_explanation'] = view
    dom = rendered(w._for_markdown(w.render(response)))
    assert not dom.select('script, img, iframe, a')
    assert '실제 승인일을 알려주세요.' in dom.get_text()


@pytest.mark.parametrize('code', ['SCOPE_USE_UNSUPPORTED_RANGE', 'SCOPE_CLAIM_EVIDENCE',
    'SCOPE_RANGE_COVERAGE', 'SCOPE_TARGET_COVERAGE', 'SCOPE_FOREIGN_EVIDENCE',
    'SCOPE_REVIEW_REASON_ISSUE', 'SCOPE_QUOTE_INVALID', 'SCOPE_USE_LINK',
    'SCOPE_EXCLUSION_LINK', 'SCOPE_EXCLUDED_ADOPTED', 'SCOPE_OPEN_GAP',
    'SCOPE_ACQUISITION_INCOMPLETE', 'SCOPE_REVIEW_INCOMPLETE', 'FINAL_REVIEW_PURPOSE_CHANGE'])
def test_typed_failure_explanation_keeps_the_original_failure(code):
    assessment = {'model_proposal': {'review_status': 'INCOMPLETE', 'failure': {'issues': [{'code': code, 'path': '/private'}]}}}
    before = deepcopy(assessment); view = review.build(assessment, [])
    assert view['failed_checks'][0]['code'] == code and view['failed_checks'][0]['reason']
    assert '/private' not in str(view) and assessment == before


@pytest.mark.parametrize('stream', [False, True])
def test_chat_consumer_no_second_call_and_no_source_only_token_duplication(monkeypatch, tmp_path, stream):
    import main
    response = failed_reply(); calls = []
    monkeypatch.setenv('GENOS_RUNTIME_DIR', str(tmp_path))
    monkeypatch.setenv('GENOS_MEMORY_ENABLED', '0')
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', 'off')
    monkeypatch.delenv('TEAM_ID', raising=False)
    monkeypatch.delenv('GENOS_CHAT_TRUST_PLATFORM_IDENTITY', raising=False)
    async def service(request):
        calls.append(request)
        # COMPOSE emits no narrative deltas when no claim was accepted.
        return {'status': 200, 'body': response}
    monkeypatch.setattr(chat_adapter, 'call_service', service)
    raw = TestClient(main.app).post('/chat', json={'question': '모의 질문', 'stream': stream})
    assert raw.status_code == 200 and len(calls) == 1
    if stream:
        import json
        events = [json.loads(line[6:]) for line in raw.text.splitlines() if line.startswith('data: ')]
        result = next(row['data'] for row in events if row.get('event') == 'result')
        assert ''.join(row['data'] for row in events if row.get('event') == 'token') == result['text']
    else:
        result = raw.json()['data']
    assert result['answer_status'] == 'partial'
    assert '설명해 주시겠어요?' in result['text'] and '검토 다시 하기' not in result['text']
    assert len(rendered(result['text']).select('[data-source-text]')) == 1
    assert asyncio.run(chat_adapter.views().workflow_display_result(response, [], request_id='r'))['text'] == result['text']


def test_specific_fact_questions_are_deduplicated_without_turning_failed_drafts_into_answers():
    w = chat_adapter.views(); response = failed_reply()
    view = response['assembly']['term_agent']['review_explanation']
    action = {'kind': 'REQUEST_FACT', 'actor': 'USER', 'enabled': True,
              'fact_name': '거래 유형(일반 대출인지 신탁사 책임준공인지)과 건별 금액을 알려주세요.'}
    view['actions'] += [action, deepcopy(action),
        {**action, 'enabled': False, 'fact_name': '비활성 질문'},
        {**action, 'actor': 'SYSTEM', 'fact_name': '시스템의 원문 확보 작업'}]
    response['assembly']['term_agent']['review_explanation'] = review.seal(
        {k: v for k, v in view.items() if k != 'content_sha256'})
    response['answer']['unresolved'] *= 30
    response['answer']['unresolved'].append({'reason': '최종 검토 미완료 판단: 승인 가능합니다.'})
    before = deepcopy(response)
    text = w._public_answer_text(response)
    assert '어떤 조건을 적용해야 할지는 아직 애매합니다.' in text
    assert text.index('아직 애매합니다.') < text.index(action['fact_name'])
    assert text.count(action['fact_name']) == 1 and '더 알려주시겠어요?' in text
    for hidden in ('비활성 질문', '시스템의 원문 확보 작업', '승인 가능합니다.', '최종 검토 미완료 판단'):
        assert hidden not in text
    assert response == before and w._completion_answer_status(response, True) == 'partial'


def test_originals_and_versions_remain_only_in_source_cards():
    w = chat_adapter.views(); response = failed_reply()
    source = response['assembly']['context'][0]
    source['text'] = '길게 확보한 원문입니다. ' * 100 + '예외 조건은 마지막에 있습니다.'
    source['version'] = '2025'
    response['assembly']['context'] = [source, deepcopy(source),
        {**source, 'id': 'new-version', 'version': '2026'},
        {**source, 'id': 'third', 'document_name': '세 번째 문서', 'text': '세 번째 자료의 전체 원문'}]
    text = w._public_answer_text(response)
    assert '길게 확보한 원문' not in text and '세 번째 문서' not in text
    assert '(2025)' not in text and '(2026)' not in text
    assert '세 번째 자료' not in text and '원문의 일부' not in text
    dom = rendered(w._for_markdown(w.render(response)))
    assert [row.get_text() for row in dom.select('[data-source-text]')] == [
        source['text'], source['text'], '세 번째 자료의 전체 원문']


def test_untrusted_fact_requests_are_not_presented_as_current_questions():
    w = chat_adapter.views(); response = failed_reply()
    response['assembly']['term_agent']['review_explanation']['actions'].append(
        {'kind': 'REQUEST_FACT', 'actor': 'USER', 'enabled': True, 'fact_name': 'UNTRUSTED_FACT'})
    text = w._public_answer_text(response)
    assert 'UNTRUSTED_FACT' not in text and '검토 다시 하기' not in text


def test_source_gap_is_not_asked_as_a_missing_user_fact():
    w = chat_adapter.views(); response = failed_reply()
    assessment = {'claims': [], 'source_excerpt_reply': {'verified': True},
        'gaps': [{'kind': 'MISSING_SOURCE', 'issue_id': 'Q1', 'reason': '별표 원문 확인 필요',
                  'missing_target': '별표 원문'}],
        'model_proposal': {'review_status': 'INCOMPLETE'}}
    response['assembly']['term_agent']['review_explanation'] = review.bind_case(
        review.build(assessment, []), {'question_id': 'g1', 'revision': 1, 'route_id': 'r1'})
    text = w._public_answer_text(response)
    assert '어떤 조건을 적용해야 할지' not in text
    assert '별표 원문을 알려' not in text and '검토 다시 하기' not in text


def test_source_markup_and_storage_ids_are_absent_from_answer_body():
    w = chat_adapter.views(); response = failed_reply()
    source = response['assembly']['context'][0]
    source.update(document_name='<script>title</script>',
                  ancestors=[], block_id='PRIVATE_BLOCK_ID',
                  text='<img src="https://invalid.test/pixel"> ![image](https://invalid.test/pixel)')
    text = w._public_answer_text(response)
    dom = rendered(w._for_markdown(text))
    assert not dom.select('script, img, iframe, a') and 'PRIVATE_BLOCK_ID' not in text
    assert source['text'] not in dom.get_text()
