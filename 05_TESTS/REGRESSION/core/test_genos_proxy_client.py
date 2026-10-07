"""ADR-0463 GenOS proxy (Qwen3.5-122B-A10B FP8 via OpenRouter): product-only, FP8-only, thinking off."""
import hashlib, json
from pathlib import Path
import httpx, pytest
from lawrag.research.experiment_client import (
    OpenRouterProxyClient, ExperimentCallError, ExperimentFormatError,
    ExperimentTransportError, load_proxy_policy,
)
from lawrag.research.openrouter_legal_adapter import OpenRouterSingleSendAdapter
from semantic_runtime.legal_agent.errors import ProposalError, TransportError
from scripts.adr_structure import scaffold_adr, validate_adr

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'00_SYSTEM/WORKSPACE.json').is_file())
MODEL = 'qwen/qwen3.5-122b-a10b'
SCHEMA = {'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False}

def setup(tmp_path, monkeypatch, change=None):
    (tmp_path/'00_SYSTEM').mkdir()
    policy = json.loads((ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json').read_text())
    if change: change(policy['genos_proxy'])
    (tmp_path/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json').write_text(json.dumps(policy))
    monkeypatch.setenv('OPEN_ROUTER', 'unit-test-secret')

def reply(value, **over):
    raw = {'model':MODEL,'provider':'AtlasCloud',
           'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(value)}}],
           'usage':{'prompt_tokens':10,'completion_tokens':3,'total_tokens':13,'cost':0.00001,
                    'completion_tokens_details':{'reasoning_tokens':0}}}
    raw.update(over); return raw

def test_payload_pins_fp8_no_fallback_no_thinking_and_hides_key(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch); seen = []
    def handler(req):
        seen.append(json.loads(req.content)); assert req.headers['Authorization'] == 'Bearer unit-test-secret'
        return httpx.Response(200, json=reply({'ok':True}))
    client = OpenRouterProxyClient(tmp_path, tmp_path/'out', transport=httpx.MockTransport(handler), max_calls=1)
    assert client.generate('sys', {'q':'public'}, SCHEMA) == {'ok':True}
    body = seen[0]
    assert body['model'] == MODEL and body['temperature'] == 0
    assert body['provider']['quantizations'] == ['fp8'] and body['provider']['allow_fallbacks'] is False
    assert body['reasoning'] == {'enabled':False}
    assert body['response_format']['json_schema']['strict'] is True
    assert client.usage[-1]['upstream_provider'] == 'AtlasCloud'
    assert all('unit-test-secret' not in p.read_text() for p in (tmp_path/'out').rglob('*.json'))
    with pytest.raises(ExperimentCallError, match='budget'): client.generate('sys', 'x', SCHEMA)

@pytest.mark.parametrize('over', [
    {'provider':'DeepInfra'},                                   # fp4 provider must never answer
    {'model':'qwen/qwen3.5-27b'},
    {'choices':[{'finish_reason':'length','message':{'content':'{}'}}]},
    {'usage':{'prompt_tokens':1,'completion_tokens':9,'completion_tokens_details':{'reasoning_tokens':5}}},
    {'choices':[{'finish_reason':'stop','message':{'content':'{"ok":true}','reasoning':'thinking...'}}]},
])
def test_rejects_other_provider_model_truncation_or_thinking(tmp_path, monkeypatch, over):
    setup(tmp_path, monkeypatch)
    client = OpenRouterProxyClient(tmp_path, tmp_path/'out',
                                   transport=httpx.MockTransport(lambda req: httpx.Response(200, json=reply({'ok':True}, **over))))
    with pytest.raises(ExperimentCallError): client.generate('sys', 'x', SCHEMA)
    assert (tmp_path/'out/call-001-generate/response.json').exists()

@pytest.mark.parametrize('change', [
    lambda p: p['provider_routing'].update(quantizations=['bf16']),
    lambda p: p['provider_routing'].update(allow_fallbacks=True),
    lambda p: p.update(allowed_classes=['product','offline_evaluator']),
    lambda p: p.update(reasoning={'enabled':True}),
    lambda p: p.update(endpoint='https://evil.example'),
])
def test_policy_tampering_is_refused(tmp_path, monkeypatch, change):
    setup(tmp_path, monkeypatch, change)
    with pytest.raises(ValueError): load_proxy_policy(tmp_path)

def _override_adr(tmp_path, judge_model):
    path = scaffold_adr(tmp_path, 484, 'proxy-check', 'proxy', 'probe', [])
    manifest = json.loads((path/'실험/manifest.json').read_text())
    manifest['in_sample'] = True; manifest['decision_eligible'] = False
    auth = {'source':'user_message','text':'승인: FP8 고정','scope':'unit test','fallback_allowed':False}
    configs = {'qwen':{'model':MODEL,'thinking_level':'off'},'judge':{'model':judge_model,'thinking_level':'minimal'}}
    design = path/'artifacts/frozen-design.json'
    design.write_text(json.dumps({'scope_authorization':auth,'configs':configs}))
    manifest['llm_policy']['llm_calls'] = [
        {'role':'compose','class':'product','model':MODEL,'thinking_level':'off','arm_id':'qwen','repeats':1},
        {'role':'judge','class':'offline_evaluator','model':judge_model,'thinking_level':'minimal','arm_id':'judge','repeats':1}]
    manifest['llm_policy']['experiment_override'] = {
        'schema_version':'user-authorized-experiment-models-v1','main_wiring':'unchanged','authorization':auth,
        'allowed_models':sorted({MODEL, judge_model}),
        'frozen_design_path':str(design.relative_to(ROOT)) if design.is_relative_to(ROOT) else str(design),
        'frozen_design_sha256':hashlib.sha256(design.read_bytes()).hexdigest()}
    (path/'실험/manifest.json').write_text(json.dumps(manifest, ensure_ascii=False))
    return validate_adr(path)

def test_validator_accepts_proxy_for_product_and_refuses_it_as_judge(tmp_path):
    ok = _override_adr(tmp_path/'a', 'gemini-3.1-flash-lite')
    assert not [e for e in ok if 'override' in e or 'All new experiment roles' in e], ok
    bad = _override_adr(tmp_path/'b', MODEL)
    assert any('product-only' in e for e in bad), bad

def test_v2_puts_schema_in_prompt_and_repairs_once(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch); seen = []
    answers = [reply({'wrong':1}), reply({'ok':True})]
    def handler(req):
        seen.append(json.loads(req.content)); return httpx.Response(200, json=answers[len(seen)-1])
    client = OpenRouterProxyClient(tmp_path, tmp_path/'out', transport=httpx.MockTransport(handler),
                                   schema_in_prompt=True, max_repairs=1)
    assert client.generate('sys', 'x', SCHEMA, phase='case') == {'ok':True}
    assert '[출력 형식]' in seen[0]['messages'][0]['content'] and '"required": ["ok"]' in seen[0]['messages'][0]['content']
    assert seen[1]['messages'][-2]['role'] == 'assistant' and '출력 형식을 어겼다' in seen[1]['messages'][-1]['content']
    assert (tmp_path/'out/call-002-case-repair/output.json').exists()

def test_v2_repair_failure_and_v1_has_no_repair(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    bad = httpx.MockTransport(lambda req: httpx.Response(200, json=reply({'wrong':1})))
    v2 = OpenRouterProxyClient(tmp_path, tmp_path/'v2', transport=bad, schema_in_prompt=True, max_repairs=1)
    with pytest.raises(ExperimentCallError, match='Repair failed'): v2.generate('sys', 'x', SCHEMA)
    assert v2.calls == 2
    v1 = OpenRouterProxyClient(tmp_path, tmp_path/'v1', transport=bad)
    with pytest.raises(ExperimentCallError, match='schema'): v1.generate('sys', 'x', SCHEMA)
    assert v1.calls == 1
    with pytest.raises(ValueError): OpenRouterProxyClient(tmp_path, tmp_path/'v3', max_repairs=2)

def gateway_body():
    return {'model':MODEL,'max_tokens':777,'temperature':0,'stream':False,
            'chat_template_kwargs':{'enable_thinking':False},
            'messages':[{'role':'system','content':'exact-system'},
                        {'role':'user','content':'exact-user'},
                        {'role':'user','content':'exact-repair'}],
            'response_format':{'type':'json_schema','json_schema':{
                'name':'InvestigateDecision','strict':True,'schema':SCHEMA}}}

def test_single_send_adapter_preserves_messages_and_generation_settings(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch);seen=[]
    def handler(req):
        seen.append(json.loads(req.content));return httpx.Response(200,json=reply({'ok':True}))
    client=OpenRouterProxyClient(tmp_path,tmp_path/'out',transport=httpx.MockTransport(handler),max_calls=2,
                                 schema_in_prompt=True,max_repairs=1)
    adapter=OpenRouterSingleSendAdapter(client)
    body=gateway_body();raw=adapter.send_once(body=body,ticket={'attempt_id':'M-001','remaining_seconds':9})
    sent=seen[0]
    for key in ('messages','max_tokens','temperature','stream','chat_template_kwargs','response_format'):
        assert sent[key] == body[key]
    assert raw['body_json']['choices'][0]['message']['content'] == '{"ok": true}'
    assert adapter.physical_calls == client.calls == 1
    assert not (tmp_path/'out/call-002-product-M-001-repair').exists()

def test_single_send_adapter_separates_format_and_network_failures(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    truncated=httpx.MockTransport(lambda req:httpx.Response(200,json=reply({'ok':True},choices=[{
        'finish_reason':'length','message':{'content':'{"ok":'}}])))
    format_client=OpenRouterProxyClient(tmp_path,tmp_path/'format',transport=truncated)
    with pytest.raises(ProposalError,match='format'):
        OpenRouterSingleSendAdapter(format_client).send_once(
            body=gateway_body(),ticket={'attempt_id':'M-format','remaining_seconds':9})
    assert format_client.calls == 1

    def disconnected(req):
        raise httpx.ConnectError('offline',request=req)
    network_client=OpenRouterProxyClient(tmp_path,tmp_path/'network',transport=httpx.MockTransport(disconnected))
    with pytest.raises(TransportError) as caught:
        OpenRouterSingleSendAdapter(network_client).send_once(
            body=gateway_body(),ticket={'attempt_id':'M-network','remaining_seconds':9})
    assert caught.value.retryable and caught.value.unknown and network_client.calls == 1

def test_raw_chat_client_uses_typed_format_and_transport_errors(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    blocked=OpenRouterProxyClient(tmp_path,tmp_path/'blocked',transport=httpx.MockTransport(
        lambda req:httpx.Response(200,json=reply({'ok':True},choices=[]))))
    with pytest.raises(ExperimentFormatError):
        blocked.chat_completions(gateway_body())
    broken=OpenRouterProxyClient(tmp_path,tmp_path/'broken',transport=httpx.MockTransport(
        lambda req:(_ for _ in ()).throw(httpx.ConnectError('offline',request=req))))
    with pytest.raises(ExperimentTransportError):
        broken.chat_completions(gateway_body())
