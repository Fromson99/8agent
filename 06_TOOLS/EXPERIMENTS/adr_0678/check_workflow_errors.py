"""Synthetic HTTP consumer check on the immutable candidate workflow."""
from pathlib import Path
import importlib.util,asyncio,io,json,urllib.error,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0678-investigation-contract-completion'
b=json.loads((A/'artifacts/design/bindings.json').read_text());p=R/b['stage']/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'
spec=importlib.util.spec_from_file_location('frozen_completion_workflow',p);w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
class Display:
 def __init__(self,*args):self.transport={};self.blocks=[];self.finished=[]
 async def finish(self,text):self.finished.append(text)
w._ChatProgress=Display;w._post_code_serving=lambda _:{}
checks=[]
for code,status,expected in [('SOURCE_INVESTIGATION_INCOMPLETE',422,'incomplete'),('MODEL_UPSTREAM_UNAVAILABLE',503,'unavailable')]:
 async def fail(*args):
  body=json.dumps({'code':code,'detail':'synthetic preserved diagnostic'}).encode()
  raise urllib.error.HTTPError('https://fixture.invalid',status,'fixture',{},io.BytesIO(body))
 w._stream_code_serving=fail
 result=asyncio.run(w._run_once({'question':'모의 질문','session_id':'s','request_id':code}))
 assert result['answer_status']==expected and result['http_status']==status,result
 if expected=='unavailable':assert '일시적으로' in result['text']
 if expected=='incomplete':assert '조사를 완료하지 못했습니다' in result['text']
 checks.append({'case':code,'status':result['answer_status'],'passed':True})
(A/'artifacts/contracts/workflow-http.json').write_text(json.dumps({'workflow_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'synthetic_only':True,'model_calls':0,'checks':checks},ensure_ascii=False,indent=2)+'\n')
print('Two immutable-workflow HTTP error paths passed without network or model calls')
