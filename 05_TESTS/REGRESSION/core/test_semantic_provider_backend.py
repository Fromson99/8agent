"""Semantic service provider selection and GENOS model binding contracts."""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "02_BACKEND"))


@pytest.fixture()
def svc(monkeypatch):
    for name in (
        "SEMANTIC_LLM_BACKEND",
        "SEMANTIC_LLM_ENDPOINT",
        "GENOS_BASE_URL",
        "GENOS_LLM_SERVING_ID",
        "GENOS_LLM_KEY",
        "GENOS_LLM_URL",
        "GENOS_LLM_MODEL",
        "GENOS_GATEWAY_API_PREFIX",
    ):
        monkeypatch.delenv(name, raising=False)
    sys.modules.pop("service", None)
    return importlib.import_module("service")


def test_service_selects_anthropic_or_genos_provider(svc, monkeypatch, tmp_path):
    anthropic = svc._provider(ROOT, tmp_path, {"export_allowed": True})
    assert anthropic.backend == "anthropic"
    assert anthropic.model == "claude-haiku-4-5-20251001"

    monkeypatch.setenv("SEMANTIC_LLM_BACKEND", "genos")
    monkeypatch.setenv("GENOS_BASE_URL", "https://genos.example")
    monkeypatch.setenv("GENOS_LLM_SERVING_ID", "226")
    monkeypatch.setenv("GENOS_LLM_KEY", "secret")
    genos = svc._provider(ROOT, tmp_path, {"export_allowed": False})
    assert genos.backend == "genos"
    assert genos.trust_zone == "internal"
    assert genos.model is None


def test_service_rejects_unknown_backend(svc, monkeypatch, tmp_path):
    monkeypatch.setenv("SEMANTIC_LLM_BACKEND", "openai-compatible")
    with pytest.raises(ValueError, match="anthropic or genos"):
        svc._provider(ROOT, tmp_path, {"export_allowed": True})


def test_service_direct_generic_url_needs_no_serving_id(svc, monkeypatch, tmp_path):
    monkeypatch.setenv('SEMANTIC_LLM_BACKEND', 'genos')
    monkeypatch.setenv('GENOS_LLM_URL', 'https://internal.invalid/v1')
    monkeypatch.setenv('GENOS_LLM_KEY', 'test-key')
    assert svc._provider(ROOT, tmp_path, {'export_allowed': False}).backend == 'genos'


def test_provider_uses_generic_file_settings_without_mutating_environment(svc, monkeypatch, tmp_path):
    from semantic_runtime import genos
    from semantic_runtime.provider import Haiku
    monkeypatch.setattr(genos, 'request_json', lambda *a: {'data': [{'id': 'internal-gemma'}]})
    p = Haiku(tmp_path, tmp_path/'provider', backend='genos', trust_zone='internal')
    target, model = p._resolve_genos({'GENOS_BASE_URL': 'https://internal.invalid',
        'GENOS_LLM_SERVING_ID': '456', 'GENOS_LLM_KEY': 'synthetic-key'})
    assert target.root.endswith('/serving/456') and model == 'internal-gemma'
    assert target.headers['Authorization'] == 'Bearer synthetic-key'
    assert 'GENOS_LLM_KEY' not in __import__('os').environ


def test_genos_discovers_and_records_actual_model(monkeypatch, tmp_path):
    from semantic_runtime import genos
    from semantic_runtime.provider import Haiku, obj, STR

    monkeypatch.setenv("GENOS_BASE_URL", "https://genos.example")
    monkeypatch.setenv("GENOS_LLM_SERVING_ID", "226")
    monkeypatch.setenv("GENOS_LLM_KEY", "qwen-key")
    calls = []

    def request(target, path, payload=None):
        calls.append((target, path, payload))
        if path == "/models":
            return {"data": [{"id": "actual-qwen-model"}]}
        return {
            "choices": [{"message": {"content": '{"answer":"ok"}'}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 1},
        }

    monkeypatch.setattr(genos, "request_json", request)
    provider = Haiku(
        ROOT,
        tmp_path / "provider",
        export_allowed=False,
        backend="genos",
        trust_zone="internal",
    )
    value, receipt_ref = provider.call(
        "answer", "return an answer", {"question": "q"}, obj({"answer": STR})
    )

    assert value == {"answer": "ok"}
    assert [call[1] for call in calls] == ["/models", "/chat/completions"]
    target = calls[0][0]
    assert target.root == (
        "https://genos.example/api/gateway/rep/serving/226"
    )
    assert target.headers["Authorization"] == "Bearer qwen-key"
    assert calls[1][2]["model"] == "actual-qwen-model"
    assert calls[1][2]["stream"] is False
    assert calls[1][2]["chat_template_kwargs"] == {"enable_thinking": False}
    receipt = json.loads(Path(receipt_ref["path"]).read_text())
    assert receipt["backend"] == "genos"
    assert receipt["model"] == "actual-qwen-model"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ({"content": '{"answer":"text"}'}, {"answer": "text"}),
        ({"content": {"answer": "object"}}, {"answer": "object"}),
        (
            {
                "content": None,
                "tool_calls": [
                    {"function": {"arguments": '{"answer":"tool"}'}}
                ],
            },
            {"answer": "tool"},
        ),
    ],
)
def test_genos_structured_response_variants(message, expected):
    from semantic_runtime.provider import _structured_genos_value

    assert _structured_genos_value({"choices": [{"message": message}]}) == expected


def test_genos_null_content_is_classified():
    from semantic_runtime.genos import ServingError
    from semantic_runtime.provider import _structured_genos_value

    raw = {
        "choices": [
            {
                "finish_reason": "length",
                "message": {"content": None, "reasoning_content": "hidden"},
            }
        ]
    }
    with pytest.raises(ServingError, match="empty content.*reasoning"):
        _structured_genos_value(raw)
