"""One frozen delivered-code run; public corpus only, no answer injected."""
from pathlib import Path
import hashlib, importlib.util, json, os, shutil, sqlite3, sys, time, traceback
ROOT=Path('/home/jin/8-AGENT')
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0659-internal-accounting-manager-stop-probe'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
bindings=json.loads((ADR/'artifacts/design/bindings.json').read_text())
for p,h in bindings['files'].items():assert sha(ROOT/p)==h,p
candidate=ROOT/bindings['candidate'];manifest=json.loads((candidate/'candidate.json').read_text());rev=manifest['revisions'][-1]
for row in rev['files']:assert sha(ROOT/row['frozen_path'])==row['snapshot_sha256']
code=candidate/'revisions'/rev['revision_id']/'snapshot'/bindings['snapshot_code_subdir']
directory=ADR/'artifacts/run-001';directory.mkdir(exist_ok=False)
source=ROOT/bindings['generation'];generation=directory/'generation-shadow'
# Immutable originals stay read-only; new compiler-derived caches are confined
# to this disposable local directory and never replace the selected generation.
shutil.copytree(source,generation,copy_function=os.link)
sys.path.insert(0,str(code/'02_BACKEND'));sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('audit_client',ROOT/'02_BACKEND/lawrag/research/experiment_client.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
ExperimentClient=audit.ExperimentClient
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
from semantic_runtime.legal_agent.errors import ContractError
from fastapi.testclient import TestClient
client=ExperimentClient(ROOT,directory/'provider',max_calls=40,max_output_tokens=6400,max_repairs=0)
class Transport(LocalGemmaTransport):
    def send_once(self,*,body,ticket):
        print('MODEL_START',client.calls+1,flush=True)
        result=client.chat_completions(body,phase='product-'+str(client.calls+1),timeout_seconds=ticket['remaining_seconds'])
        raw=result['body_json']
        if raw.get('provider')!='Parasail' or raw.get('model')!=self.binding['model']:raise ContractError('provider binding')
        print('MODEL_DONE',client.calls,client.usage[-1]['seconds'],flush=True)
        return result
transport=Transport(code,ROOT)
profile=json.loads((code/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
profile.update(model_binding=transport.binding,max_model_attempts=40,wall_seconds=900,max_output_tokens=6400)
principal={'user_id':'accounting-stop-probe','team_id':'public-laws','authenticated':True,'document_ids':list(transport.public_scope)}
body={'question':'내부 회계 관리자는 누가 지정하나요?','document_ids':list(transport.public_scope),'public_question':True,'use_llm':True,'session_id':'accounting-stop-probe','request_id':'adr0659-run001'}
put(directory/'profile.json',profile);put(directory/'request.json',body)
start=time.monotonic();row={'code_root':str(code),'source_generation':str(source),'model':client.model,'field_execution':False}
try:
    app=create_app(directory,generation,contracts_root=code,workspace_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',legal_agent_profile=profile,legal_agent_transport=transport,runtime_root=directory/'runtime',memory_identity=lambda _:principal)
    with TestClient(app) as api:
        ready=time.monotonic();row['app_setup_seconds']=ready-start
        print('ASK_START',flush=True)
        response=api.post('/v1/rag/ask',json=body)
        row.update(http_status=response.status_code,output=response.json(),request_seconds=time.monotonic()-ready)
except Exception as exc:
    row.update(http_status=500,error_type=type(exc).__name__,error=str(exc))
    (directory/'error.txt').write_text(traceback.format_exc())
finally:
    row.update(total_seconds=time.monotonic()-start,model_calls=client.calls,usage=client.usage)
    put(directory/'result.json',row)
    print('RESULT',json.dumps({k:v for k,v in row.items() if k not in ('output','usage')},ensure_ascii=False),flush=True)
