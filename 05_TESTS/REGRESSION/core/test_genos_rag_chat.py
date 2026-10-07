import asyncio
import importlib.util
import json
import io
import urllib.error
import pytest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py"


def _load():
    spec = importlib.util.spec_from_file_location("genos_rag_chat", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _stub_stream(monkeypatch, workflow, body):
    """Rendering tests isolate the network; transport has separate contract tests."""
    async def stream(question, data, display):
        return body
    monkeypatch.setattr(workflow, '_stream_code_serving', stream)


def _rag_body():
    return {
        "run_id": "run-123",
        "answer": {
            "text": "검증된 답변입니다.",
            "claims": [{"evidence_ids": ["source:used"]}],
        },
        "assembly": {
            "context": [
                {
                    "id": "source:used",
                    "document_name": "내부규정 A",
                    "ancestors": [{"title": "제1장"}, {"title": "제2조"}],
                },
                {"id": "source:unused", "document_name": "미사용 문서"},
            ]
        },
    }


def test_extracts_nested_question_without_using_metadata():
    workflow = _load()
    data = {
        "chatId": "chat-secret-looking-value",
        "token": "longer-token-that-must-not-become-question",
        "payload": {"message": "내규상 승인 절차는 무엇인가요?"},
    }
    assert workflow._extract_question(data) == "내규상 승인 절차는 무엇인가요?"


def test_missing_question_does_not_use_platform_uuid_or_unknown_strings(monkeypatch):
    workflow = _load()
    def unexpected(*args): raise AssertionError('No model request for metadata')
    monkeypatch.setattr(workflow, 'call_code_serving', unexpected)
    data = {'id': '52a666cd-929a-d448-ff9b-73058af40378',
            'payload': {'nodeId': 'another-long-id', 'description': 'metadata'},
            'history': [{'text': 'earlier question'}]}
    assert workflow._extract_question(data) == ''
    assert asyncio.run(workflow.run(data))['answer_status'] == 'invalid_input'


def test_bare_uuid_in_question_is_rejected_before_serving(monkeypatch):
    workflow = _load()
    monkeypatch.setattr(workflow, 'call_code_serving',
                        lambda *args: pytest.fail('UUID must not become a model question'))
    output = asyncio.run(workflow.run({'question': '7cd01570-8ee2-722c-30ba-3c40055667a8'}))
    assert output['answer_status'] == 'invalid_input'


def test_source_tool_error_is_shown_and_stops_workflow(monkeypatch):
    workflow=_load()
    monkeypatch.setattr(workflow, '_settings', lambda: ('http://fixture/json', 'fixture', 2100))
    payload=json.dumps({'status':500,'body':{'code':'SOURCE_TOOL_ERROR',
        'detail':'tool=search mode=fulltext stage=fulltext_tool.rank cause=OperationalError: interrupted'}}).encode()
    def fail(*args, **kwargs):
        raise urllib.error.HTTPError('http://fixture',500,'failed',{},io.BytesIO(payload))
    monkeypatch.setattr(workflow.urllib.request,'urlopen',fail)
    output=asyncio.run(workflow.run({'question':'승인 기준은?'}))
    assert output['answer_status']=='failed'
    assert 'fulltext_tool.rank' in output['text']
    assert 'interrupted' in output['text']


@pytest.mark.parametrize('operation,state', [('WARMUP', 'RUNNING'), ('WARMUP_STATUS', 'READY')])
def test_workflow_test_forwards_warmup_without_legal_agent(monkeypatch, operation, state):
    workflow = _load()
    sent = []
    def unexpected(*args): raise AssertionError('Must not run LEGAL_AGENT')
    def post(body):
        sent.append(body)
        return {'state': state, 'worker_id': 'worker-1', 'generation_path': '/fixture',
                '_gateway_status': 202 if state == 'RUNNING' else 200}
    monkeypatch.setattr(workflow, 'call_code_serving', unexpected)
    monkeypatch.setattr(workflow, '_post_code_serving', post)
    result = asyncio.run(workflow.run({'API_TYPE': operation, 'question': 'placeholder', 'id': 'uuid'}))
    assert sent == [{'API_TYPE': operation, 'request_id': result['request_id']}]
    assert result['answer_status'] == 'warmup'
    assert result['warmup']['state'] == state
    assert 'worker-1' in result['text']


def test_old_serving_warmup_response_is_not_reported_as_ready(monkeypatch):
    workflow = _load()
    monkeypatch.setattr(workflow, '_post_code_serving', lambda body: _rag_body())
    result = asyncio.run(workflow.run({'API_TYPE': 'WARMUP'}))
    assert result['answer_status'] == 'failed'


def test_question_field_warmup_is_management_not_model(monkeypatch):
    workflow = _load()
    monkeypatch.setattr(workflow, 'call_code_serving',
                        lambda *args: pytest.fail('WARMUP must not run LEGAL_AGENT'))
    sent = []
    def post(body):
        sent.append(body)
        return {'state': 'RUNNING', 'worker_id': 'worker-1', '_gateway_status': 202}
    monkeypatch.setattr(workflow, '_post_code_serving', post)
    output = asyncio.run(workflow.run({'question': 'WARMUP'}))
    assert output['warmup']['state'] == 'RUNNING'
    assert sent[0]['API_TYPE'] == 'WARMUP'


def test_other_api_types_cannot_bypass_question_contract(monkeypatch):
    workflow = _load()
    monkeypatch.setattr(workflow, '_post_code_serving', lambda body: pytest.fail('Unexpected passthrough'))
    assert asyncio.run(workflow.run({'API_TYPE': 'DELETE'}))['answer_status'] == 'invalid_input'


def test_unwraps_service_envelope_and_json_body():
    workflow = _load()
    wrapped = {"status": 200, "body": json.dumps(_rag_body(), ensure_ascii=False)}
    body = workflow.unwrap(wrapped)
    assert body["run_id"] == "run-123"
    assert body["_gateway_status"] == 200


def test_render_preserves_legal_review_notes_for_advisory_answer():
    module = _load()
    text = '모의 승인 대상입니다.\n\n**법률 검토 필요사항**\n- 모의규정 제1조 제2항: 예외 적용 여부를 확인하십시오.\n- 확인 한계: 제출 사실을 확인하십시오.'
    body = {'answer': {'text': text, 'provider_receipt': {'final_review_policy': 'advisory'}}}
    assert module.render(body) == text


def test_render_keeps_answer_and_only_used_sources():
    workflow = _load()
    rendered = workflow.render(_rag_body())
    assert rendered.startswith("검증된 답변입니다.")
    assert "내부규정 A · 제1장 > 제2조" in rendered
    assert "미사용 문서" not in rendered


def test_render_v5_chat_has_short_answer_and_sources_last():
    workflow = _load()
    body = {
        "answer": {"text": "영업일은 영업하는 날입니다.\n\n확인 한계: 내부 검토 미완료"},
        "assembly": {"term_agent": {
            "exploration_v3": {"display_lines": ["UNASSESSED_AT_STOP · 실행 기록"]},
            "source_bundle": {"schema_version": "source-tiers-v4", "sources": [
                {"tier": "CORE", "document_name": "모의내규", "coordinate_label": "제1조", "open_url": ""},
                {"tier": "SUPPLEMENTAL", "document_name": "모의내규", "coordinate_label": "제1조", "open_url": ""},
            ]},
        }},
    }
    rendered = workflow.render(body)
    assert rendered == "영업일은 영업하는 날입니다.\n\n**출처**\n- 핵심 · 모의내규 · 제1조"


def test_found_but_unreviewed_source_is_not_reported_as_not_found(monkeypatch):
    workflow = _load()
    body = {"answer": {"text": "확인 한계: 원문에 근거한 답변 검토가 완료되지 않았습니다.", "claims": []},
            "assembly": {"term_agent": {"exploration_v3": {"totals": {"evidence": 2},
                "evidence_decisions": [{"status": "UNASSESSED_AT_STOP"}]}}}}
    assert workflow.render(body) == "관련 원문은 찾았지만 답변 검토를 완료하지 못했습니다."
    _stub_stream(monkeypatch, workflow, body)
    result = asyncio.run(workflow._run_once({"chatInput": "질문입니다"}))
    assert result["answer_status"] == "incomplete"


def test_render_v5_names_core_and_supplemental_documents_without_original(monkeypatch):
    workflow = _load()
    monkeypatch.setenv("GENOS_RAG_SOURCE_BASE_URL", "https://sources.example")
    body = {"answer": {"text": "최종 답변.\n\n확인 한계: 내부 진단"},
            "assembly": {"term_agent": {"source_bundle": {
                "schema_version": "source-tiers-v4", "sources": [{
                    "tier": "CORE", "document_name": "내규", "coordinate_label": "제1조",
                    "open_url": "/v1/rag/source?run_id=r1&selection_id=SSabc",
                    "excerpt": "채팅에 넣으면 안 되는 원문",
                }, {
                    "tier": "SUPPLEMENTAL", "document_name": "가상법령", "coordinate_label": "제2조",
                    "open_url": "/v1/rag/source?run_id=r1&selection_id=SSdef",
                    "excerpt": "보완 원문",
                }]}}}}
    rendered = workflow.render(body)
    assert rendered == ("최종 답변.\n\n**출처**\n"
                        "- 핵심 · 내규 · 제1조\n"
                        "- 보완 · 가상법령 · 제2조")
    assert "/v1/rag/source" not in rendered
    assert "원문" not in rendered and "확인 한계" not in rendered
    monkeypatch.delenv("GENOS_RAG_SOURCE_BASE_URL")
    assert workflow.render(body) == rendered


def test_render_v3_claim_source_ids_selects_document():
    workflow = _load()
    body = {
        "answer": {"text": "영업일은 영업하는 날입니다.",
                   "claims": [{"source_ids": ["source:used"]}]},
        "assembly": {"context": [
            {"id": "source:used", "document_name": "모의내규"},
            {"id": "source:unused", "document_name": "다른 문서"},
        ]},
    }
    assert workflow.render(body).endswith("**출처**\n- 모의내규")


def test_run_returns_genos_text_contract(monkeypatch):
    workflow = _load()
    _stub_stream(monkeypatch, workflow, _rag_body())
    output = asyncio.run(
        workflow._run_once(
            {
                "chatInput": "질문입니다",
                "chatId": "chat / 42",
                "userInfo": {"user_id": "employee-1"},
            }
        )
    )
    assert output["text"].startswith("검증된 답변입니다.")
    assert output["answer_status"] == "answered"
    assert output["run_id"] == "run-123"
    assert output["session_id"] == "chat---42"
    assert output["history"] == "not_persisted"


def test_run_returns_one_genos_text_dictionary(monkeypatch):
    workflow = _load()
    _stub_stream(monkeypatch, workflow, _rag_body())
    result = asyncio.run(workflow.run({"question": "질문입니다"}))

    assert isinstance(result, dict)
    assert result["text"].startswith("검증된 답변입니다.")
    assert result["answer_status"] == "answered"
    assert result["run_id"] == "run-123"


def test_settings_builds_endpoint_from_base_and_id(monkeypatch):
    workflow = _load()
    monkeypatch.setenv("GENOS_CODESERVING_TOKEN", "secret")
    monkeypatch.setenv("GENOS_BASE_URL", "http://genos.example/")
    monkeypatch.setenv("GENOS_CODESERVING_ID", "497")
    endpoint, token, timeout = workflow._settings()
    assert endpoint == "http://genos.example/api/gateway/code_serving/497/json"
    assert token == "secret"
    assert timeout == 2100.0


def test_workflow_timeout_respects_saved_setting(monkeypatch):
    workflow = _load()
    monkeypatch.setenv('GENOS_BASE_URL', 'http://genos.example')
    monkeypatch.setenv('GENOS_CODESERVING_ID', '497')
    monkeypatch.setenv('GENOS_CODESERVING_TOKEN', 'synthetic-key')
    monkeypatch.setenv('GENOS_CODESERVING_TIMEOUT_SECONDS', '360')
    assert workflow._settings()[2] == 360.0
    monkeypatch.setenv('GENOS_CODESERVING_TIMEOUT_SECONDS', '2400')
    assert workflow._settings()[2] == 2400.0


def test_settings_does_not_accept_a_preassembled_url(monkeypatch):
    workflow = _load()
    monkeypatch.setenv("GENOS_CODESERVING_URL", "http://wrong.example/direct")
    monkeypatch.setenv("GENOS_CODESERVING_TOKEN", "secret")
    monkeypatch.delenv("GENOS_BASE_URL", raising=False)
    monkeypatch.delenv("GENOS_CODESERVING_ID", raising=False)
    try:
        workflow._settings()
    except EnvironmentError as exc:
        assert "GENOS_BASE_URL" in str(exc)
    else:
        raise AssertionError("a direct URL must not bypass base/id configuration")


def test_team_environment_is_read_per_call_and_overrides_payload(monkeypatch):
    workflow = _load()
    monkeypatch.setattr(workflow, "_settings", lambda: ("http://fixture.invalid", "fixture-token", 1))
    sent = []
    class Response:
        status = 200
        headers = {}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return b'{"answer":{"text":"fixture"}}'
    def send(request, timeout):
        sent.append(json.loads(request.data))
        return Response()
    monkeypatch.setattr(workflow.urllib.request, "urlopen", send)
    for team in ("risk_team", "financial_team"):
        monkeypatch.setenv("TEAM_ID", " " + team + " ")
        workflow.call_code_serving("질문", {"team_id": "other_team"})
        assert sent[-1]["team_id"] == team
        assert sent[-1]["API_TYPE"] == "LEGAL_AGENT"
    monkeypatch.delenv("TEAM_ID")
    workflow.call_code_serving("질문", {"team_id": "risk_team"})
    assert sent[-1]["team_id"] == "risk_team"
    workflow.call_code_serving("질문", {})
    assert "team_id" not in sent[-1]
    assert workflow._extract_question({"TEAM_ID": "risk_team"}) == ""


@pytest.mark.parametrize("value", ["", "  ", "../risk_team", "unknown", "risk_team,financial_team"])
def test_invalid_team_environment_stops_before_http(monkeypatch, value):
    workflow = _load()
    monkeypatch.setattr(workflow, "_settings", lambda: ("http://fixture.invalid", "fixture-token", 1))
    monkeypatch.setenv("TEAM_ID", value)
    def unexpected(*args, **kwargs): raise AssertionError("HTTP must not be called")
    monkeypatch.setattr(workflow.urllib.request, "urlopen", unexpected)
    with pytest.raises(ValueError, match="TEAM_ID"):
        workflow.call_code_serving("질문", {"team_id": "risk_team"})
