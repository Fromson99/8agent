"""GENOS service(config, data) integration contract."""
from __future__ import annotations

import asyncio
import importlib
import json
import sys
from pathlib import Path

import pytest
from semantic_runtime import observability as obs


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT))
pytest.importorskip("fastapi")


@pytest.fixture()
def svc(monkeypatch, tmp_path):
    monkeypatch.delenv("GENOS_GENERATION", raising=False)
    monkeypatch.setenv("GENOS_RUNTIME_DIR", str(tmp_path / "runtime"))
    sys.modules.pop("service", None)
    module = importlib.import_module("service")
    yield module


def run(svc, data):
    result = asyncio.run(svc.service({}, data))
    svc.request_report._FINALIZER_QUEUE.join()
    return result


def test_genos_wait_extension_keeps_pinned_profile_unchanged(svc, monkeypatch):
    monkeypatch.delenv('GENOS_RAG_WALL_SECONDS', raising=False)
    pinned = {'wall_seconds': 300, 'model_binding': {'model': 'fixture'}}
    configured = svc._genos_v5_wait_profile(pinned)
    assert configured['wall_seconds'] == 1800
    assert pinned['wall_seconds'] == 300
    assert configured['model_binding'] == pinned['model_binding']
    assert svc._genos_v5_wait_profile({'wall_seconds': 3600})['wall_seconds'] == 3600
    monkeypatch.setenv('GENOS_RAG_WALL_SECONDS', '2400')
    assert svc._genos_v5_wait_profile(pinned)['wall_seconds'] == 2400


@pytest.mark.parametrize('value', ['0', '-1', 'nan', '1.5'])
def test_genos_wait_extension_rejects_invalid_setting(svc, monkeypatch, value):
    monkeypatch.setenv('GENOS_RAG_WALL_SECONDS', value)
    with pytest.raises(ValueError, match='GENOS_RAG_WALL_SECONDS'):
        svc._genos_v5_wait_profile({'wall_seconds': 300})


def test_ping_is_lazy_and_api_type_compatible(svc):
    assert svc._APP is None
    direct = run(svc, {"op": "ping"})
    compat = run(svc, {"API_TYPE": "PING"})
    assert direct == compat
    assert direct["ok"] is True
    assert direct["service"] == "8-AGENT"
    assert direct["runtime"] == "genos-semantic-v2"
    assert direct["app_loaded"] is False
    assert svc._APP is None


def test_legacy_tokenizer_is_rejected_before_frozen_runtime_import(svc, tmp_path, monkeypatch):
    generation = tmp_path / 'generation'
    (generation / 'fulltext').mkdir(parents=True)
    (generation / 'manifest.json').write_text(json.dumps({'fulltext': {'path': 'fulltext'}}))
    (generation / 'fulltext/manifest.json').write_text(json.dumps({
        'schema_version': 'semantic-fulltext-v1', 'tokenizer': {'kiwipiepy': '0.23.2'}}))
    monkeypatch.setattr(svc, '_resolve_binding', lambda: (tmp_path/'absent-frozen-code', generation,
                                                       {'mode': 'local-release'}))
    with pytest.raises(RuntimeError, match='PeCab 1.0.8'):
        svc.application()
    assert svc._APP is None


def test_legacy_frozen_code_is_rejected_even_without_fulltext_binding(svc, tmp_path, monkeypatch):
    generation = tmp_path / 'generation'
    generation.mkdir()
    (generation / 'manifest.json').write_text('{}')
    module = tmp_path / 'code/02_BACKEND/semantic_runtime/fulltext.py'
    module.parent.mkdir(parents=True)
    module.write_text('from kiwipiepy import Kiwi\n')
    monkeypatch.setattr(svc, '_resolve_binding', lambda: (tmp_path/'code', generation, {'mode':'local-release'}))
    with pytest.raises(RuntimeError, match='selected frozen code'):
        svc.application()
    assert svc._APP is None


def test_connections_does_not_require_generation(svc, monkeypatch):
    expected = {"ok": True, "checks": [{"component": "llm", "status": "PASS"}]}
    monkeypatch.setattr("semantic_runtime.genos.smoke", lambda execute=False: expected)
    out = run(svc, {"API_TYPE": "CONNECTIONS", "execute": False})
    assert out == {"status": 200, "body": expected}
    assert svc._APP is None


def test_diagnostics_runs_three_axis_check_without_generation(svc, monkeypatch):
    expected = {
        "ok": True,
        "checks": [
            {"component": "llm", "status": "PASS"},
            {"component": "embed", "status": "PASS"},
            {"component": "vdb", "status": "PASS"},
        ],
    }
    monkeypatch.setattr("semantic_runtime.genos.diagnostics", lambda: expected)
    out = run(svc, {"API_TYPE": "DIAGNOSTICS"})
    assert out == {"status": 200, "body": expected}
    assert svc._APP is None


def test_missing_generation_is_classified_as_503(svc, monkeypatch):
    monkeypatch.setattr(
        svc,
        "_local_release",
        lambda: (_ for _ in ()).throw(RuntimeError("not packaged")),
    )
    out = run(svc, {"op": "call", "method": "GET", "path": "/health"})
    assert out["status"] == 503
    assert out["body"]["error"] == "generation/runtime unavailable"
    assert out["body"]["error_type"] == "RuntimeError"
    assert "not packaged" not in str(out)


def test_bare_uuid_question_fails_before_loading_generation(svc):
    out = run(svc, {'API_TYPE': 'LEGAL_AGENT',
                    'question': '7cd01570-8ee2-722c-30ba-3c40055667a8'})
    assert out['status'] == 422
    assert out['body']['error_type'] == 'InvalidQuestion'
    assert svc._APP is None


def test_old_workflow_question_warmup_is_control_call(svc):
    result = run(svc, {'API_TYPE': 'LEGAL_AGENT', 'question': 'WARMUP_STATUS'})
    assert result['body']['state'] == 'NOT_STARTED'
    assert svc._APP is None


def test_query_only_allowlist_blocks_mutation_and_unknown_api_type(svc):
    blocked = run(
        svc,
        {"op": "call", "method": "POST", "path": "/v1/rag/feedback", "json": {}},
    )
    assert blocked == {"status": 403, "body": {"error": "route not allowed"}}
    unknown = run(svc, {"API_TYPE": "DELETE_ALL"})
    assert unknown["status"] == 400
    assert unknown["body"]["supported"] == sorted(svc._API_TYPES)


def test_legacy_semantic_generation_requires_migration(svc, monkeypatch):
    generation = ROOT / "01_DATA/SEMANTIC/GENERATIONS/semantic-main-20260907-v1"
    monkeypatch.setenv("GENOS_GENERATION", str(generation))
    health = run(svc, {"API_TYPE": "HEALTH"})
    # The source-only runtime intentionally rejects the retired semantic schema.
    # A current synthetic generation is exercised in test_genos_team_selection.
    assert health["status"] == 503
    assert health["body"]["error_type"] == "RuntimeError"
    assert svc._APP is None


def test_rag_ask_alias_preserves_body(svc, monkeypatch):
    captured = {}

    async def fake_call(data):
        captured.update(data)
        return {"status": 200, "body": {"ok": True}}

    monkeypatch.setattr(svc, "_call", fake_call)
    out = run(
        svc,
        {"API_TYPE": "RAG_ASK", "question": "신탁재산 구분", "use_llm": False},
    )
    assert out["status"] == 200
    assert captured["path"] == "/v1/rag/ask"
    assert captured["json"] == {"question": "신탁재산 구분", "use_llm": False}


def test_service_writes_one_shared_report_per_turn(svc, monkeypatch, tmp_path):
    shared = tmp_path / "shared"
    monkeypatch.setenv("GENOS_SHARED_LOG_DIR", str(shared))

    async def fake_call(data):
        await asyncio.to_thread(obs.event, obs.get_logger("worker-test"), "worker.step")
        return {"status": 200, "body": {"run_id": "b" * 32,
                                         "answer": {"text": "근거 부족", "claims": [], "unresolved": [1]}}}

    monkeypatch.setattr(svc, "_call", fake_call)
    result = run(svc, {"API_TYPE": "LEGAL_AGENT", "question": "질문", "request_id": "turn-1"})
    assert result["status"] == 200
    files = list(shared.rglob("*.json"))
    assert len(files) == 1
    text_files = list(shared.rglob("*.txt"))
    assert len(text_files) == 1
    assert text_files[0].stem == files[0].stem
    trace = text_files[0].read_text(encoding="utf-8")
    assert "request.started" in trace and "request.finished" in trace
    assert "worker.step" in trace
    report = json.loads(files[0].read_text())
    assert report["request_id"] == "turn-1"
    assert report["result"]["body"]["answer"]["text"] == "근거 부족"
    assert [item["event"] for item in report["service_events"]] == ["request.started", "worker.step", "request.finished", "request.returning"]


def test_shared_report_failure_does_not_change_answer(svc, monkeypatch):
    monkeypatch.setenv("GENOS_SHARED_LOG_DIR", "relative-path-is-invalid")

    async def fake_call(data):
        return {"status": 200, "body": {"answer": {"text": "답변"}}}

    monkeypatch.setattr(svc, "_call", fake_call)
    assert run(svc, {"API_TYPE": "LEGAL_AGENT", "question": "질문"}) == {
        "status": 200, "body": {"answer": {"text": "답변"}}
    }


def test_readable_trace_failure_keeps_json_and_answer(svc, monkeypatch, tmp_path):
    shared = tmp_path / "shared"
    monkeypatch.setenv("GENOS_SHARED_LOG_DIR", str(shared))
    async def fake_call(data):
        return {"status": 200, "body": {"run_id": "c" * 32,
                                        "answer": {"text": "답변", "claims": []}}}
    monkeypatch.setattr(svc, "_call", fake_call)
    def fail_trace(path):
        raise OSError("synthetic trace failure")
    monkeypatch.setattr(svc.request_report, "write_readable_report", fail_trace)
    result = run(svc, {"API_TYPE": "LEGAL_AGENT", "question": "질문"})
    assert result["status"] == 200
    assert len(list(shared.rglob("*.json"))) == 1
    assert list(shared.rglob("*.txt")) == []


def test_els_query_alias_uses_the_same_grounded_rag_path(svc, monkeypatch):
    captured = {}

    async def fake_call(data):
        captured.update(data)
        return {"status": 200, "body": {"answer": {"text": "답변"}}}

    monkeypatch.setattr(svc, "_call", fake_call)
    out = run(
        svc,
        {
            "API_TYPE": "ELS_QUERY",
            "question": "내규상 승인 절차",
            "channel": "genos-chat",
            "session_id": "chat-1",
        },
    )
    assert out["status"] == 200
    assert captured["path"] == "/v1/rag/ask"
    assert captured["json"]["question"] == "내규상 승인 절차"
    assert "channel" not in captured["json"]
    assert "session_id" not in captured["json"]


def test_genos_environment_selects_integrated_bounded_controller(svc, monkeypatch):
    from types import SimpleNamespace
    from semantic_runtime import genos
    monkeypatch.setenv('GENOS_LLM_URL', 'http://synthetic.invalid')
    monkeypatch.setenv('GENOS_LLM_KEY', 'synthetic-contract-token')
    monkeypatch.setattr(genos, 'from_env', lambda role: (SimpleNamespace(root='http://synthetic.invalid'), 'synthetic-model'))
    configured, transport = svc._genos_v5_environment_binding()
    assert configured['bounded_source_selection_enabled'] is True
    assert configured['final_review_enabled'] is False
    assert transport.binding['trust_zone'] == 'internal'


def test_genos_v6_environment_preserves_unified_budget(svc, monkeypatch):
    from types import SimpleNamespace
    from semantic_runtime import genos
    monkeypatch.setenv('GENOS_LLM_URL', 'http://synthetic.invalid')
    monkeypatch.setenv('GENOS_LLM_KEY', 'synthetic-contract-token')
    monkeypatch.setattr(genos, 'from_env', lambda role: (SimpleNamespace(root='http://synthetic.invalid'), 'synthetic-model'))
    pinned = json.loads((ROOT / '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
    configured, transport = svc._genos_v5_environment_binding(pinned)
    assert configured['profile_id'] == 'unified-legal-agent-v6'
    assert configured['max_model_attempts'] == 40
    assert configured['model_binding'] == transport.binding
    assert transport.binding['model'] == 'synthetic-model'
    assert pinned['model_binding'] is None
    assert configured['bounded_source_selection_enabled'] is True


def test_genos_input_byte_limit_uses_operator_setting(svc, monkeypatch):
    from types import SimpleNamespace
    from semantic_runtime import genos
    monkeypatch.setenv('GENOS_LLM_URL', 'http://synthetic.invalid')
    monkeypatch.setenv('GENOS_LLM_KEY', 'synthetic-contract-token')
    monkeypatch.setenv('GENOS_LLM_MAX_INPUT_BYTES', '131072')
    monkeypatch.setattr(genos, 'from_env', lambda role: (SimpleNamespace(root='http://synthetic.invalid'), 'synthetic-model'))
    configured, transport = svc._genos_v5_environment_binding()
    assert transport.binding['max_input_bytes'] == 131072
    for invalid in ('0','-1','abc'):
        monkeypatch.setenv('GENOS_LLM_MAX_INPUT_BYTES', invalid)
        with pytest.raises(ValueError, match='GENOS_LLM_MAX_INPUT_BYTES'):
            svc._genos_v5_environment_binding()
