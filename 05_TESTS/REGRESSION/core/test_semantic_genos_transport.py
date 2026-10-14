"""Shared GENOS endpoint, retry, and safe-error contract."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import httpx


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from semantic_runtime import genos  # noqa: E402


class Response:
    def __init__(self, status: int, value=None):
        self.status_code = status
        self._value = value

    def json(self):
        if isinstance(self._value, Exception):
            raise self._value
        return self._value


class Session:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        value = self.responses.pop(0)
        if isinstance(value, httpx.RequestError):
            raise value
        return value


def test_endpoint_defaults_to_branch_gateway_and_keeps_direct_v1():
    target = genos.endpoint(
        "https://genos.example/",
        serving_id="226",
        token="secret",
        user_id="worker-1",
    )
    assert target.root == "https://genos.example/api/gateway/rep/serving/226"
    assert target.url("/chat/completions").endswith("/226/chat/completions")
    assert target.headers["Authorization"] == "Bearer secret"
    assert target.headers["x-genos-user-id"] == "worker-1"

    direct = genos.endpoint("https://genos.example/api/gateway/rep/serving/226/v1/models")
    assert direct.root == target.root + "/v1"

    unversioned = genos.endpoint(
        "https://genos.example", serving_id="226", api_prefix="none"
    )
    assert unversioned.url("/chat/completions").endswith(
        "/api/gateway/rep/serving/226/chat/completions"
    )


def test_llm_connect_timeout_is_sixty_seconds_and_configurable():
    settings = {'GENOS_BASE_URL': 'https://genos.example', 'GENOS_LLM_SERVING_ID': '123'}
    assert genos.from_env('llm', environ=settings)[0].connect_timeout == 60.0
    settings['GENOS_LLM_CONNECT_TIMEOUT'] = '90'
    assert genos.from_env('llm', environ=settings)[0].connect_timeout == 90.0
    for value in ('0', '-1', 'nan', 'inf'):
        with pytest.raises(ValueError, match='CONNECT_TIMEOUT'):
            genos.from_env('llm', environ={**settings, 'GENOS_LLM_CONNECT_TIMEOUT': value})


@pytest.mark.parametrize('remaining, expected', [(1800, 60), (10, 10)])
def test_agent_transport_uses_connection_setting_inside_total_deadline(monkeypatch, remaining, expected):
    import asyncio
    import hashlib
    from semantic_runtime.legal_agent.transport import GenosTransport
    target = genos.from_env('llm', environ={'GENOS_BASE_URL': 'https://genos.example', 'GENOS_LLM_SERVING_ID': '123'})[0]
    binding = {'provider': 'genos', 'trust_zone': 'internal', 'adapter_version': 'genos-single-send-v1',
               'endpoint_identity': hashlib.sha256(target.root.encode()).hexdigest(), 'model': 'fixture'}
    configured = []
    import io
    from contextlib import contextmanager
    import semantic_runtime.legal_agent.transport as module
    from semantic_runtime.stdlib_http import Response
    class Raw(io.BytesIO):
        code = 200
        headers = {'content-type': 'application/json'}
    @contextmanager
    def opened(*args, **kwargs):
        configured.append(kwargs['timeout'])
        with Raw(json.dumps({'data': [{'id': 'fixture'}]}).encode()) as raw:
            yield Response(raw, kwargs['timeout'], kwargs['deadline'])
    monkeypatch.setattr(module, 'open_response', opened)
    transport = GenosTransport(target, binding)
    asyncio.run(transport._request('POST', '/chat/completions', {}, remaining))
    assert configured[-1].connect == expected
    assert configured[-1].read == remaining
    transport.validate_model()
    assert configured[-1].read == 120
    assert configured[-1].connect == 60


@pytest.mark.parametrize(
    "value",
    ["", "ftp://genos.example", "https://user:pw@genos.example/v1", "https://x/v1?q=1"],
)
def test_endpoint_rejects_unsafe_or_incomplete_urls(value):
    with pytest.raises(ValueError):
        genos.endpoint(value)


def test_transient_status_retries_then_returns_json(monkeypatch):
    monkeypatch.setattr(genos.time, "sleep", lambda _seconds: None)
    session = Session(Response(503), Response(200, {"ok": True}))
    target = genos.endpoint("https://genos.example/v1", max_retries=2)
    assert genos.request_json(target, "/models", session=session) == {"ok": True}
    assert len(session.calls) == 2


def test_non_retryable_4xx_fails_once_without_body_or_token(monkeypatch):
    monkeypatch.setattr(genos.time, "sleep", lambda _seconds: None)
    session = Session(Response(401, {"token": "leak-me"}), Response(200, {}))
    target = genos.endpoint("https://genos.example/v1", token="secret", max_retries=3)
    with pytest.raises(genos.ServingError) as caught:
        genos.request_json(target, "/models", session=session)
    assert len(session.calls) == 1
    assert "401" in str(caught.value)
    assert "secret" not in str(caught.value)
    assert "leak-me" not in str(caught.value)


def test_invalid_json_is_classified():
    session = Session(Response(200, json.JSONDecodeError("bad", "x", 0)))
    target = genos.endpoint("https://genos.example/v1", max_retries=1)
    with pytest.raises(genos.ServingError, match="invalid JSON"):
        genos.request_json(target, "/models", session=session)


def test_owned_session_uses_urllib_without_disabling_tls(monkeypatch):
    session = Session(Response(200, {"data": []}))
    session.trust_env = False
    closed = []
    session.close = lambda: closed.append(True)
    options = []
    def client(**kwargs):
        options.append(kwargs)
        return session
    from semantic_runtime import stdlib_http
    monkeypatch.setattr(stdlib_http, "Client", client)
    target = genos.endpoint("http://genos.example:32154", serving_id="226", token="dummy")
    assert genos.request_json(target, "/models") == {"data": []}
    assert options == [{}]
    method, url, kwargs = session.calls[0]
    assert method == "GET"
    assert url == "http://genos.example:32154/api/gateway/rep/serving/226/models"
    assert kwargs["headers"]["Authorization"] == "Bearer dummy"
    assert kwargs["follow_redirects"] is False
    assert "verify" not in kwargs  # TLS validation is not disabled.
    assert closed == [True]


def test_supplied_session_keeps_caller_environment_policy():
    session = Session(Response(200, {}))
    session.trust_env = False
    genos.request_json(genos.endpoint("http://genos.example"), "/models", session=session)
    assert session.trust_env is False


def test_injected_httpx_session_keeps_timeout_and_headers():
    requests = []
    def receive(request):
        requests.append(request)
        return httpx.Response(200, json={"data": []})
    target = genos.endpoint("https://fixture.invalid", token="synthetic", max_retries=1,
                            connect_timeout=7, read_timeout=13)
    with httpx.Client(transport=httpx.MockTransport(receive), trust_env=False) as session:
        assert genos.request_json(target, "/models", session=session) == {"data": []}
        assert not session.is_closed
    assert len(requests) == 1
    assert requests[0].extensions["timeout"]["connect"] == 7
    assert requests[0].extensions["timeout"]["read"] == 13
    assert requests[0].headers["Authorization"] == "Bearer synthetic"


def test_generic_environment_builds_llm_and_embedding_ignoring_old_profile(monkeypatch):
    monkeypatch.setenv("GENOS_BASE_URL", "https://genos.example")
    monkeypatch.setenv("GENOS_LLM_SERVING_ID", "226")
    monkeypatch.setenv("GENOS_LLM_KEY", "qwen-key")
    monkeypatch.setenv("GENOS_LLM_MODEL", "qwen-model")
    monkeypatch.setenv("GENOS_EMBED_SERVING_ID", "19")
    monkeypatch.setenv("GENOS_EMBED_KEY", "embed-key")
    monkeypatch.setenv("GENOS_LLM_PROFILE", "gemma")
    monkeypatch.setenv("GENOS_GEMMA_SERVING_ID", "999")
    monkeypatch.setenv("GENOS_GEMMA_KEY", "stale-key")
    monkeypatch.setenv("GENOS_GEMMA_MODEL", "stale-model")

    llm, llm_model = genos.from_env("llm")
    embed, _embed_model = genos.from_env("embed")
    assert llm.root.endswith("/serving/226") and llm_model == "qwen-model"
    assert llm.headers["Authorization"] == "Bearer qwen-key"
    assert embed.root.endswith("/serving/19")
    assert embed.headers["Authorization"] == "Bearer embed-key"


def test_brand_only_settings_do_not_silently_select_a_model():
    with pytest.raises(ValueError, match='GENOS_LLM serving ID'):
        genos.from_env('llm', environ={
            'GENOS_BASE_URL': 'https://genos.example', 'GENOS_LLM_PROFILE': 'qwen',
            'GENOS_QWEN_SERVING_ID': '123', 'GENOS_QWEN_KEY': 'obsolete'})


def test_gateway_ignores_legacy_prefix_without_changing_url_or_environment(monkeypatch):
    monkeypatch.delenv("GENOS_LLM_URL", raising=False)
    monkeypatch.delenv("GENOS_GATEWAY_API_PREFIX", raising=False)
    monkeypatch.setenv("GENOS_BASE_URL", "http://genos.example:12345")
    monkeypatch.setenv("GENOS_LLM_SERVING_ID", "226")
    monkeypatch.setenv("GENOS_LLM_KEY", "dummy")
    monkeypatch.setenv("GENOS_LLM_API_PREFIX", "/v1")
    target, _ = genos.from_env("llm")
    assert target.url("/models") == "http://genos.example:12345/api/gateway/rep/serving/226/models"
    assert genos.os.environ["GENOS_LLM_API_PREFIX"] == "/v1"
    monkeypatch.setenv("GENOS_GATEWAY_API_PREFIX", "/v1")
    assert genos.from_env("llm")[0].root.endswith("/226/v1")
    monkeypatch.setenv("GENOS_LLM_URL", "http://gpu.example:8000")
    assert genos.from_env("llm")[0].root == "http://gpu.example:8000/v1"


@pytest.mark.parametrize("kind", ["llm", "embed"])
def test_gateway_execute_posts_without_models_preflight(monkeypatch, kind):
    target = genos.endpoint("http://genos.example", serving_id="226", token="dummy")
    monkeypatch.setattr(genos, "from_env", lambda k: (target, ""))
    def no_discovery(*args):
        raise AssertionError("gateway generation must not preflight /models")
    monkeypatch.setattr(genos, "advertised_model", no_discovery)
    calls = []
    def request(t, path, payload):
        calls.append((path, payload))
        if kind == "llm":
            return {"choices": [{"message": {"content": "OK"}}]}
        return {"data": [{"embedding": [0.1, 0.2]}]}
    monkeypatch.setattr(genos, "request_json", request)
    out = genos.check(kind, execute=True)
    assert out["status"] == "PASS" and out["models"] == "NOT_RUN"
    assert calls[0][1]["model"] == "genos"
    if kind == "llm":
        assert calls[0][0] == "/chat/completions"
        assert calls[0][1]["chat_template_kwargs"] == {"enable_thinking": False}
    else:
        assert calls[0][0] == "/embeddings"


def test_network_error_keeps_cause_but_not_secrets_in_public_error():
    failure = httpx.ConnectError("private-detail dummy-secret")
    session = Session(failure)
    target = genos.endpoint("http://genos.example", max_retries=1)
    with pytest.raises(genos.ServingError) as caught:
        genos.request_json(target, "/models", session=session)
    assert caught.value.__cause__ is failure
    assert "ConnectError" in str(caught.value)
    assert "dummy-secret" not in str(caught.value)


def test_redirect_is_reported_without_json_parsing():
    session = Session(Response(302, ValueError("not JSON")))
    with pytest.raises(genos.ServingError, match="HTTP 302"):
        genos.request_json(genos.endpoint("http://genos.example"), "/models", session=session)


def test_vdb_uses_direct_weaviate_and_embedding_for_near_vector(monkeypatch):
    monkeypatch.setenv("GENOS_VDB_URL", "http://llmops-weaviate-service:8080")
    monkeypatch.setenv("GENOS_VDB_COLLECTION", "J06fc3cb_test")
    monkeypatch.setenv("GENOS_VDB_TOKEN", "vdb-secret")
    calls = []

    def fake_request(target, path, payload=None, **_kwargs):
        calls.append((target, path, payload))
        if path.startswith("/schema/"):
            return {"class": "J06fc3cb_test"}
        return {
            "data": {
                "Get": {
                    "J06fc3cb_test": [
                        {"_additional": {"id": "one", "distance": 0.1}}
                    ]
                }
            }
        }

    monkeypatch.setattr(genos, "request_json", fake_request)
    out = genos.check_vdb([0.25, -0.5, 0.75])
    assert out["status"] == "PASS"
    assert out["objects_returned"] == 1
    assert out["dimensions"] == 3
    assert calls[0][0].root == "http://llmops-weaviate-service:8080/v1"
    assert calls[0][0].headers["Authorization"] == "Bearer vdb-secret"
    assert "nearVector" in calls[1][2]["query"]
    assert "[0.25,-0.5,0.75]" in calls[1][2]["query"]
    assert "vdb-secret" not in str(out)


def test_vdb_rejects_resource_gateway_and_unsafe_collection(monkeypatch):
    monkeypatch.setenv(
        "GENOS_VDB_URL", "https://genos/api/gateway/rep/serving/535/v1"
    )
    monkeypatch.setenv("GENOS_VDB_COLLECTION", "GoodCollection")
    assert genos.check_vdb([1.0])["status"] == "FAIL"

    monkeypatch.setenv("GENOS_VDB_URL", "http://weaviate:8080")
    monkeypatch.setenv("GENOS_VDB_COLLECTION", "Bad){Delete{")
    assert genos.check_vdb([1.0])["status"] == "FAIL"


def test_diagnostics_combines_three_independent_results(monkeypatch):
    calls = []

    def fake_check(kind, *, execute=False, _vector_sink=None):
        calls.append((kind, execute))
        if _vector_sink is not None:
            _vector_sink.extend([0.1, 0.2])
        return {"component": kind, "status": "PASS"}

    monkeypatch.setattr(genos, "check", fake_check)
    monkeypatch.setattr(
        genos,
        "check_vdb",
        lambda vector: {"component": "vdb", "status": "PASS", "dimensions": len(vector)},
    )
    out = genos.diagnostics()
    assert out["ok"] is True
    assert calls == [("llm", True), ("embed", True)]
    assert [row["component"] for row in out["checks"]] == ["llm", "embed", "vdb"]
    assert "0.1" not in str(out)
