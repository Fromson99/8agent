import asyncio
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py"


def _load():
    spec = importlib.util.spec_from_file_location("genos_rag_chat", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


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


def test_unwraps_service_envelope_and_json_body():
    workflow = _load()
    wrapped = {"status": 200, "body": json.dumps(_rag_body(), ensure_ascii=False)}
    body = workflow.unwrap(wrapped)
    assert body["run_id"] == "run-123"
    assert body["_gateway_status"] == 200


def test_render_keeps_answer_and_only_used_sources():
    workflow = _load()
    rendered = workflow.render(_rag_body())
    assert rendered.startswith("검증된 답변입니다.")
    assert "내부규정 A · 제1장 > 제2조" in rendered
    assert "미사용 문서" not in rendered


def test_run_returns_genos_text_contract(monkeypatch):
    workflow = _load()
    monkeypatch.setattr(workflow, "call_code_serving", lambda question, data: _rag_body())
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
    monkeypatch.setattr(workflow, "call_code_serving", lambda question, data: _rag_body())
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
    assert timeout == 120.0


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
