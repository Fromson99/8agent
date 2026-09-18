"""Progress events must not stop ingestion when credentials resemble JSON tokens."""
import json
from io import StringIO
import pytest
from lawrag.pipeline.genos_progress import Progress


def test_call_budget_progress_is_distinct_from_input_token_limit():
    from lawrag.pipeline.genos_progress import vlm_detail, reason
    text = vlm_detail({'event':'recipe.review.budget', 'total_pages':404,
                      'window_width':1, 'fresh_pass_min_calls':404, 'max_calls':64,
                      'minimum_exceeds_limit':True})
    assert '404회' in text and '64회' in text and '완료 불가' in text
    assert '호출 횟수' in reason('model_call_budget_exhausted')
    text = vlm_detail({'event':'recipe.review.budget_exhausted', 'calls':64,
                      'max_calls':64, 'pending_pages':340})
    assert '340쪽 시각 미검수' in text and '입력 토큰 한도와 별개' in text


def test_token_budget_visible_but_real_tokens_still_redacted(monkeypatch):
    from semantic_runtime.genos_backend import safe
    from semantic_runtime.observability import _redact_secrets
    from lawrag.pipeline.genos_status import safe as status_safe
    monkeypatch.setenv('STRUCTURE_RECIPE_MAX_TOKENS', '16384')
    monkeypatch.setenv('GENOS_LLM_KEY', 'mock-credential')
    monkeypatch.setenv('TEST_ACCESS_TOKEN', '987654')
    text = 'max_tokens=16384 mock-credential 987654'
    for redact in (safe, _redact_secrets, status_safe):
        assert redact(text) == 'max_tokens=16384 [REDACTED] [REDACTED]'

@pytest.mark.parametrize('prefix,row',[
    ('[STRUCTURE VLM] ',{'event':'model.response','run_id':'test','seconds':1.6384,'input_count':16384,'output_count':4096}),
    ('[QUEUE] ',{'state':'READY','error':'','passed':0,'total':16384,'stage':'test','attempt':1}),
    ('[TASK] ',{'stage':'review','number':1,'total':16384,'label':'test'}),
])
def test_numeric_budget_never_corrupts_json(tmp_path,monkeypatch,prefix,row):
    monkeypatch.setenv('STRUCTURE_RECIPE_MAX_TOKENS','16384')
    monkeypatch.setenv('GENOS_LLM_KEY','mock-credential')
    row['nested']={'secret':'mock-credential'}
    progress=Progress(tmp_path,StringIO())
    try:
        progress.document(1,1,'synthetic.pdf','structure')
        progress.emit(prefix+json.dumps(row))
        text=(tmp_path/'detail.log').read_text()
        assert 'mock-credential' not in text
        parsed=json.loads(text.split(prefix,1)[1])
        assert parsed['nested']['secret']=='[REDACTED]'
        numeric='input_count' if 'input_count' in row else 'total'
        assert parsed[numeric]==16384
    finally:progress.close()


def test_malformed_event_does_not_abort_document_or_dump_secrets(tmp_path):
    progress=Progress(tmp_path,StringIO())
    try:
        progress.document(1,1,'synthetic.pdf','structure')
        progress.emit('[STRUCTURE VLM] {"secret":"do-not-log", "count": [REDACTED]}')
        text=(tmp_path/'detail.log').read_text()
        assert 'Invalid event JSON' in text and 'do-not-log' not in text
        progress.emit('[STRUCTURE VLM] '+json.dumps({'event':'model.request','run_id':'test','call':1,'attempt':1}))
        assert '응답 대기' in progress.state['detail']
    finally:progress.close()
