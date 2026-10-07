"""Ordinary no-model smoke through the real active-release service entrypoint."""
import importlib, json, sys
from pathlib import Path
R=Path(__file__).resolve().parents[3];sys.path.insert(0,str(R));sys.dont_write_bytecode=True
import service
from fastapi.testclient import TestClient
app=service.application()
pointer=json.loads((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
assert pointer['release_id']=='shortcut-integrated-v6-20261005-r1'
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
    report={'status':'passed','pointer':pointer,'health':health,'pipeline_profile_verified':profile,'search_status':search.status_code,'model_calls':0,'durable_ingress':{k:payload[k] for k in ['intake_id','investigation_id']},'unauthenticated_memory_denied':denied.status_code,'service_binding':service._BINDING}
path=R/'04_EXPERIMENTS/ADR/ADR-0654-shortcut-boundary-separated-main/artifacts/main-smoke.json'
path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
