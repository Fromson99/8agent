"""Default routing and historical ADR compatibility; no paid/model calls."""
import base64,json
from pathlib import Path
import httpx,pytest
from lawrag.research.experiment_client import ExperimentClient,QwenExperimentClient,GeminiExperimentClient,ExperimentCallError
from scripts.adr_structure import scaffold_adr,validate_adr
ROOT=next(p for p in Path(__file__).resolve().parents if (p/'00_SYSTEM/WORKSPACE.json').is_file())
MODEL='qwen/qwen3.5-122b-a10b'
SCHEMA={'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False}
def setup(tmp_path,monkeypatch):
    (tmp_path/'00_SYSTEM').mkdir()
    (tmp_path/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json').write_text((ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json').read_text())
    monkeypatch.setenv('OPEN_ROUTER','qwen-test-secret')
def reply():
    return {'model':MODEL,'provider':'AtlasCloud','choices':[{'finish_reason':'stop','message':{'content':'{"ok":true}'}}],
            'usage':{'prompt_tokens':10,'completion_tokens':3,'total_tokens':13}}
def test_default_text_and_vlm_one_physical_send_no_key(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch);seen=[]
    def handler(req):seen.append(json.loads(req.content));return httpx.Response(200,json=reply())
    c=ExperimentClient(tmp_path,tmp_path/'out',transport=httpx.MockTransport(handler),max_calls=2)
    assert isinstance(c,QwenExperimentClient)
    assert c.generate('test',{'public':True},SCHEMA)=={'ok':True}
    uri='data:image/png;base64,'+base64.b64encode(b'fixture').decode()
    assert c.generate('test','public',SCHEMA,images=[uri])=={'ok':True}
    assert c.calls==2 and seen[1]['messages'][1]['content'][1]['image_url']['url']==uri
    assert all(p['provider']['quantizations']==['fp8'] and p['reasoning']=={'enabled':False} for p in seen)
    assert all('qwen-test-secret' not in p.read_text() for p in (tmp_path/'out').rglob('*.json'))
    with pytest.raises(ExperimentCallError):c.generate('test','public',SCHEMA)
    with pytest.raises(ValueError,match='no longer'):GeminiExperimentClient(tmp_path,tmp_path/'old')
def test_default_scaffold_all_roles_and_historical_manifest(tmp_path):
    p=scaffold_adr(tmp_path,9000,'qwen-default','Qwen','audit',[])
    m=json.loads((p/'실험/manifest.json').read_text())
    assert m['llm_policy']['policy_version']=='qwen-experiments-v1'
    assert all(c['model']==MODEL for c in m['llm_policy']['llm_calls'])
    assert validate_adr(p)==[]
    m['llm_policy']['llm_calls'][1]['model']='gemini-3.1-flash-lite'
    (p/'실험/manifest.json').write_text(json.dumps(m))
    assert any('All new experiment roles' in e for e in validate_adr(p))
    m['llm_policy']['policy_version']='gemini-experiments-v1'
    (p/'실험/manifest.json').write_text(json.dumps(m))
    assert any('require qwen-experiments-v1' in e for e in validate_adr(p))
def test_default_rejects_routing_drift(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch);p=tmp_path/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json';m=json.loads(p.read_text())
    m['provider_routing']['quantizations']=['fp4'];p.write_text(json.dumps(m))
    with pytest.raises(ValueError,match='FP8'):ExperimentClient(tmp_path,tmp_path/'out')
