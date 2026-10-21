"""Read actual registered DOCX through the same API, without model transmission."""
from pathlib import Path
import os,sys,json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0785-risk-team-compare-workflow'
C=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]).resolve()
sys.dont_write_bytecode=True
sys.path[:0]=[str(C/'02_BACKEND'),str(C)]
os.environ['LAWRAG_WORKSPACE_ROOT']=str(R)
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.workflow_tiers_policy import DEFAULT_PROFILE
from semantic_runtime.team_scope import select_documents
from fastapi.testclient import TestClient
binding=json.loads((Path(sys.argv[3]) if len(sys.argv)>3 else A/'artifacts/data-binding.json').read_text());generation=R/binding['generation_path']
class NoModel:
 binding={'provider':'fixture','model':'synthetic-no-call','adapter_version':'fixture-v1',
   'endpoint_identity':'no-network','trust_zone':'internal','max_input_bytes':500000}
 def validate_model(self):return {'verified':True,'synthetic':True,'model_calls':0}
 def send_once(self,**kwargs):raise AssertionError('A metadata-only probe must never call a model')
# This is an explicitly synthetic disabled transport, not a claim of a live GENOS model.
transport=NoModel();holder={}
def principal(_):return {'user_id':'local-probe','team_id':'risk_team',
 'document_ids':select_documents(holder['app'].state.pipeline.store,'risk_team')}
app=create_app(R,generation,contracts_root=C,workspace_root=R,provider=object(),implementation='legal-agent-tools-v5',
 runtime_root=out.parent/'document-probe-runtime',legal_agent_profile={**DEFAULT_PROFILE,'model_binding':transport.binding},
 legal_agent_transport=transport,memory_identity=principal);holder['app']=app
with TestClient(app) as client:
 response=client.post('/v1/rag/ask',json={'question':'대사: 유동성','session_id':'docx-probe','request_id':'docx-no-model-v1',
   'use_llm':False,'document_ids':[binding['new_document_id']]})
 assert response.status_code==200,response.text
 result=response.json();cards=result['assembly']['term_agent']['source_bundle']['sources']
 assert result['status']=='partial' and result['usage']['model_reserved']==0,result
 assert any('제15조' in c['excerpt'] or '제15조' in c['coordinate_label'] for c in cards)
 assert all(c['source_artifact_hash']==binding['source_sha256'] for c in cards)
 assert result['report']['rows']==[]
 receipt={'api':'POST /v1/rag/ask','status':result['status'],'model_calls':0,'synthetic_transport_disabled':True,
  'code_root':str(C),'generation_id':binding['generation_id'],'document_id':binding['new_document_id'],
  'source_artifact_sha256':binding['source_sha256'],'run_id':result['run_id'],'usage':result['usage'],
  'evidence_ids':result['evidence_refs'],'source_locations':[c['coordinate_label'] for c in cards],
  'article15_found':True,'legal_judgment_executed':False,
  'response_sha256':hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
  'limits':['Current document validity unknown','Single-document exact-source connection check; no retrieval-quality claim',
            'Missing external sources are a selected-scope registration gap, never legal absence']}
 out.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:receipt[k] for k in ['status','model_calls','article15_found','source_locations']},ensure_ascii=False))
