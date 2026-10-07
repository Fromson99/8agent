"""Offline contract checks for the two scoped Gemma integration changes."""
import json,hashlib,sys,tempfile
from copy import deepcopy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from run_probe import pin,ADR,ROOT
import httpx,jsonschema

def main():
 d=pin('gemma')
 from lawrag.research.experiment_client import ExperimentClient,ExperimentProviderError
 from semantic_runtime.legal_agent.source_bundle import validate_export_authorization
 from semantic_runtime.legal_agent.errors import ContractError
 model='google/gemma-4-31b-it';g=d['export_authorization']
 b={'export_authorization':g,'generation_id':g['generation_id'],'store_sha256':g['source_store_sha256'],'source_export_allowed':g['source_manifest_export_allowed'],'scope':{'document_version_ids':g['scope_document_ids']},'model':{'model':model,'endpoint_identity':hashlib.sha256(g['destination'].encode()).hexdigest()}}
 validate_export_authorization(b);passed=1
 for field,value in [('model','wrong'),('destination','https://wrong.invalid'),('private_documents_allowed',True),('policy_sha256','0'*64),('scope_document_ids',[]),('experiment_policy_path','00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')]:
  bad=deepcopy(b);bad['export_authorization'][field]=value
  try:validate_export_authorization(bad)
  except ContractError:passed+=1
  else:raise AssertionError(field)
 def mock(request):
  data=json.loads(request.content);assert data['model']==model and data['reasoning']=={'enabled':False} and data['provider']['only']==['deepinfra/fp8'] and data['provider']['quantizations']==['fp8'] and data['provider']['allow_fallbacks'] is False
  return httpx.Response(200,json={'model':model,'provider':'DeepInfra','choices':[{'finish_reason':'stop','message':{'content':'{"ok":true}'}}],'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2,'completion_tokens_details':{'reasoning_tokens':0}}})
 with tempfile.TemporaryDirectory() as temp:
  c=ExperimentClient(ROOT,Path(temp),scoped_policy=ADR/'artifacts/gemma-policy.json',transport=httpx.MockTransport(mock));c.chat_completions({'model':model,'messages':[{'role':'user','content':'offline fixture'}]});assert c.calls==1;passed+=1
  try:c.chat_completions({'model':'wrong','messages':[{'role':'user','content':'fixture'}]})
  except ValueError:assert c.calls==1;passed+=1
  else:raise AssertionError('model mismatch accepted')
 with tempfile.TemporaryDirectory() as temp:
  seen=[]
  def capture(req):seen.append(json.loads(req.content));return mock(req)
  c=ExperimentClient(ROOT,Path(temp),scoped_policy=ADR/'artifacts/gemma-policy.json',transport=httpx.MockTransport(capture))
  schema={'type':'array','uniqueItems':True,'items':{'type':'string'}}
  original={'model':model,'messages':[{'role':'user','content':'original prompt unchanged'}],'response_format':{'type':'json_schema','json_schema':{'name':'test','strict':True,'schema':schema}}}
  c.chat_completions(original)
  assert original['response_format']['json_schema']['schema']['uniqueItems'] is True
  assert 'uniqueItems' not in seen[0]['response_format']['json_schema']['schema'] and seen[0]['messages']==original['messages']
  stored=json.loads(next(Path(temp).rglob('original-validation-schema.json')).read_text());assert stored==schema
  try:jsonschema.validate(['duplicate','duplicate'],stored)
  except jsonschema.ValidationError:passed+=1
  else:raise AssertionError('Full local uniqueness constraint lost')
 print(json.dumps({'passed':passed,'live_calls':0,'checks':'scoped grant accepted; stale/model/scope/destination/private/path rejected; exact FP8 one-send and no fallback'}))
if __name__=='__main__':main()
