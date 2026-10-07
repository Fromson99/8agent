import json,copy,base64
from pathlib import Path
import httpx,pytest,jsonschema
from lawrag.research.experiment_client import GeminiExperimentClient,ExperimentCallError,load_policy,_schema_for_api,MODEL
from scripts.adr_structure import scaffold_adr,validate_adr,HAIKU_MODEL
ROOT=next(p for p in Path(__file__).resolve().parents if (p/'00_SYSTEM/WORKSPACE.json').is_file())

def setup(tmp_path,monkeypatch):
 (tmp_path/'00_SYSTEM').mkdir();(tmp_path/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json').write_text((ROOT/'04_EXPERIMENTS/ADR/ADR-0486-qwen-default-experiment-policy/artifacts/previous-policy.json').read_text())
 monkeypatch.setenv('GEMINI_API_KEY','unit-test-secret')

def good(value):
 return {'modelVersion':MODEL,'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(value)}]}}],'usageMetadata':{'promptTokenCount':10,'candidatesTokenCount':3,'totalTokenCount':13}}

SCHEMA={'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False}
def test_generate_text_and_inline_image_records_without_key(tmp_path,monkeypatch):
 setup(tmp_path,monkeypatch);requests=[]
 def handler(req):
  requests.append(req);assert req.headers['x-goog-api-key']=='unit-test-secret';assert 'key=' not in str(req.url)
  return httpx.Response(200,json=good({'ok':True}))
 client=GeminiExperimentClient(tmp_path,tmp_path/'out',transport=httpx.MockTransport(handler),max_calls=2)
 assert client.generate('test',{'input':'public'},SCHEMA)=={'ok':True}
 uri='data:image/png;base64,'+base64.b64encode(b'fake test-only bytes').decode()
 assert client.generate('test','image',SCHEMA,images=[uri])=={'ok':True}
 assert json.loads(requests[1].content)['contents'][0]['parts'][1]['inlineData']['mimeType']=='image/png'
 assert client.usage[-1]['total_tokens']==13
 assert all('unit-test-secret' not in p.read_text() for p in (tmp_path/'out').rglob('*.json'))
 with pytest.raises(ExperimentCallError,match='budget'):client.generate('test','x',SCHEMA)
 assert len(requests)==2

@pytest.mark.parametrize('change',[{'provider':'anthropic'},{'model':'gemini-flash-latest'},{'endpoint':'https://evil.example'},{'fallback_allowed':True}])
def test_no_provider_alias_or_endpoint_fallback(tmp_path,monkeypatch,change):
 setup(tmp_path,monkeypatch);p=tmp_path/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json';d=json.loads(p.read_text());d.update(change);p.write_text(json.dumps(d))
 with pytest.raises(ValueError):GeminiExperimentClient(tmp_path,tmp_path/'out')

@pytest.mark.parametrize('raw',[good({'ok':'wrong'}),{**good({'ok':True}),'modelVersion':'other'}, {**good({'ok':True}),'candidates':[{'finishReason':'MAX_TOKENS','content':{'parts':[{'text':'{}'}]}}]}])
def test_reject_invalid_truncated_or_wrong_model(tmp_path,monkeypatch,raw):
 setup(tmp_path,monkeypatch);client=GeminiExperimentClient(tmp_path,tmp_path/'out',transport=httpx.MockTransport(lambda req:httpx.Response(200,json=raw)))
 with pytest.raises((ExperimentCallError,jsonschema.ValidationError)):client.generate('x','x',SCHEMA)
 assert (tmp_path/'out/call-001-generate/response.json').exists()

def test_http_error_has_no_fallback(tmp_path,monkeypatch):
 setup(tmp_path,monkeypatch);seen=[]
 def handler(req):seen.append(req);return httpx.Response(429,json={'error':{'message':'quota'}})
 c=GeminiExperimentClient(tmp_path,tmp_path/'out',transport=httpx.MockTransport(handler))
 with pytest.raises(ExperimentCallError,match='429'):c.generate('x','x',SCHEMA)
 assert len(seen)==1

def test_schema_projection_preserves_property_names_and_local_constraints():
 s={'type':'object','properties':{'pattern':{'type':'string','minLength':5},'items':{'type':'array','uniqueItems':True,'items':{'type':'integer'}}}}
 original=copy.deepcopy(s);out=_schema_for_api(s)
 assert 'pattern' in out['properties'] and 'minLength' not in out['properties']['pattern']
 assert s==original
 with pytest.raises(jsonschema.ValidationError):jsonschema.validate({'pattern':'x','items':[1,1]},s)

def test_historical_scaffold_is_gemini_for_every_role(tmp_path):
 p=scaffold_adr(tmp_path,484,'gemini-new','Gemini','audit',[])
 m=json.loads((p/'실험/manifest.json').read_text());assert m['llm_policy']['provider']=='gemini'
 assert all(x['model']==MODEL for x in m['llm_policy']['llm_calls']);assert validate_adr(p)==[]
 m['llm_policy']['llm_calls'][0]['model']=HAIKU_MODEL;(p/'실험/manifest.json').write_text(json.dumps(m))
 assert any('All new experiment roles' in x for x in validate_adr(p))

def test_new_scaffold_rejects_legacy_policy_and_judge(tmp_path):
 p=scaffold_adr(tmp_path,9001,'gemini-old','Gemini','audit',[])
 m=json.loads((p/'실험/manifest.json').read_text());m['llm_policy']['policy_version']='role-separated-v1';(p/'실험/manifest.json').write_text(json.dumps(m))
 assert any('requires a versioned experiment policy' in x for x in validate_adr(p))
 with pytest.raises(ValueError):scaffold_adr(tmp_path,9002,'wrong-judge','Gemini','audit',[],judge_model=HAIKU_MODEL)
