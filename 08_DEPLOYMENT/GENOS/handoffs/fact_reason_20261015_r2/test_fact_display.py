"""Actual API rendering and unchanged partial outcome for a synthetic fact gap."""
import json
from copy import deepcopy
from conftest import term_glossary
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent import completion_contracts as cc
from test_main50_request_repair import tree, GAP
from test_source_span_norm import SpanTransport
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT
from test_unified_legal_agent import ok


class FactTransport(SpanTransport):
    def send_once(self, *, body, ticket):
        result = super().send_once(body=body, ticket=ticket)
        view = json.loads(body['messages'][1]['content'])['view']
        if view.get('source_stage', view['phase']).startswith('memory-assess'):
            message = result['body_json']['choices'][0]['message']
            value = json.loads(message['content'])
            value['gaps'] = [{**deepcopy(GAP), 'kind': 'MISSING_FACT',
                'reason': '개별 사건의 적용 조건 미제공', 'material_id': None,
                'missing_target': '', 'suggested_action': 'REQUEST_FACT'}]
            message['content'] = json.dumps(value, ensure_ascii=False)
        return result


def test_missing_fact_explains_purpose_and_preserves_partial_api_response(tmp_path, tree):
    gen, index = tree
    transport = FactTransport()
    profile = {**settings(), 'max_model_attempts': 40, 'max_read_chars': 10000,
        'candidate_navigation': {'mode': 'law-first-v1', 'investigation_control': True,
            'completion_contract': True, 'completion_policy_version': cc.V8, 'compact_input': True}}
    app = create_app(tmp_path, gen, contracts_root=ROOT, provider=object(),
        implementation='legal-agent-unified-v6', legal_agent_profile=profile,
        legal_agent_transport=transport,
        memory_identity=lambda _: {'user_id': 'u', 'team_id': 't', 'document_ids': ['d']})
    app.state.pipeline.term_agent.unit_fulltext = index
    with TestClient(app) as api:
        body = {'question': '모의승인규정 제1조 승인 기준은?',
                'session_id': 'fact-purpose', 'request_id': 'fact-purpose-1'}
        out = ok(api.post('/v1/rag/ask', json=body))
        text = out['answer']['text']
        assert '승인 후 보고한다.' in text
        assert '확인 범위' in text
        assert '해당 사안에 적용할 결론을 하나로 확정하려면 추가 사실 정보가 필요합니다.' in text
        assert out['assembly']['term_agent']['accepted_outcome']['answer_coverage'] == 'PARTIAL'
        meta = out['assembly']['term_agent']
        assert meta['gaps'][0]['kind'] == 'MISSING_FACT'
        shown = [item for stage in meta['judgment_view']['stages']
                 for item in stage.get('limitation_items', [])]
        assert shown and all(item['kind'] == 'MISSING_FACT' for item in shown)
        assert all('결론을 하나로 확정하려면' in item['text'] for item in shown)
        assert transport.phases.count('memory-assess') == 1
        calls = len(transport.phases)
        assert ok(api.post('/v1/rag/ask', json=body))['answer'] == out['answer']
        assert len(transport.phases) == calls
