from pathlib import Path
import json,sys,hashlib,time,traceback
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0696-structured-decision-wire-repair';C=R/'02_BACKEND/lawrag/research/candidates/adr_0696/repaired'
cm=json.loads((C/'candidate.json').read_text());code=C/'revisions'/cm['revisions'][-1]['revision_id']/'snapshot'
sys.path.insert(0,str(code/'02_BACKEND'));sys.dont_write_bytecode=True
active=json.loads((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text());release=json.loads((R/active['manifest_path']).read_text());generation=R/release['data_path'];out=A/'artifacts/preflight';out.mkdir(exist_ok=True)
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
from semantic_runtime.stage_runner import StageRunner
from semantic_runtime.legal_agent.unified_runtime import open_cases
transport=LocalGemmaTransport(code,R)
profile=json.loads((code/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text());profile['model_binding']=transport.binding
start=time.monotonic();result={'model_calls':0,'code_root':str(code.relative_to(R)),'generation':str(generation.relative_to(R))}
try:
 app=create_app(out,generation,contracts_root=code,workspace_root=R,provider=object(),implementation='legal-agent-unified-v6',legal_agent_profile=profile,legal_agent_transport=transport,runtime_root=out/'runtime',memory_identity=lambda _:None)
 StageRunner(app.state.pipeline).verify_profile()
 cases=open_cases(app.state.pipeline,out/'runtime',{}, {'user_id':'preflight','team_id':'public-laws','document_ids':list(transport.public_scope)})
 try:result.update(status='READY',binding=cases.executor.binding)
 finally:cases.close();app.state.pipeline.store.close()
except Exception as e:
 result.update(status='FAILED',error_type=type(e).__name__,error=str(e));(out/'error.txt').write_text(traceback.format_exc())
result['seconds']=time.monotonic()-start
(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
