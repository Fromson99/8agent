"""Ordinary no-model smoke through the real active-release service entrypoint."""
import importlib, json, sys
from pathlib import Path
R=Path(__file__).resolve().parents[3];sys.path.insert(0,str(R));sys.dont_write_bytecode=True
import os,asyncio
os.environ["AD_WORKER_ENABLED"]="0"
import service
from fastapi.testclient import TestClient
app=service.application()
pointer=json.loads((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
assert pointer['release_id']=='sql-ad-mode-v6-20261006-r1'
module=importlib.import_module(app.state.pipeline.__class__.__module__.rsplit('.',1)[0]+'.stage_runner')
profile=module.StageRunner(app.state.pipeline).verify_profile()
with TestClient(app) as api:
    response=api.get('/health');assert response.status_code==200
    health=response.json();assert health['rag_mode']=='legal-agent-unified-v6'
    assert health['llm_model']=='qwen/qwen3.8-27b'
    search=api.get('/v1/rag/search',params={'q':'상법 제4조','doc_id':'7bbe815ff43b6635','limit':10});assert search.status_code==200,search.text
    # A normal model-free request still passes the real durable ingress.
    result=api.post('/v1/rag/ask',json={'question':'공개 배선 검사: 상법 제4조','document_ids':['7bbe815ff43b6635'],'use_llm':False})
    assert result.status_code==200,result.text
    payload=result.json();assert payload.get('intake_id') and payload.get('investigation_id')
    denied=api.post('/v1/rag/memory/query',json={'query_kind':'investigation','investigation_id':payload['investigation_id'],'session_id':'untrusted','request_id':'untrusted'})
    assert denied.status_code in (400,401,403,409,422),denied.text
    report={'status':'passed','pointer':pointer,'health':health,'pipeline_profile_verified':profile,'search_status':search.status_code,'model_calls':0,'durable_ingress':{k:payload[k] for k in ['intake_id','investigation_id']},'unauthenticated_memory_denied':denied.status_code,'service_binding':health['release']}
path=R/'04_EXPERIMENTS/ADR/ADR-0657-sql-ad-mode-control/artifacts/main-smoke.json'
path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))

responses=[]
for i,q in enumerate(['[AD모드 시작]','도움말','현재 상태','위키 목록','[AD모드 종료]']):
 value=asyncio.run(service.service({}, {'API_TYPE':'AD_PROBE','question':q,'ad_session_id':'main-ad-verification-20261006','request_id':'verify-'+str(i)}))
 assert value['body']['response_schema']=='ad-mode-v1' and value['body']['answer_status']=='administration',value
 responses.append(value)
assert not responses[-1]['body']['ad_mode']
(R/'04_EXPERIMENTS/ADR/ADR-0657-sql-ad-mode-control/artifacts/active-ad-transcript.json').write_text(json.dumps(responses,ensure_ascii=False,indent=2)+'\n')
print('Active AD entry/status/list/exit passed without management leakage')
