"""Explicit frozen law-first app, public-only audited model calls, isolated runtime."""
from pathlib import Path
import hashlib,importlib.util,json,os,shutil,sys,time,traceback
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0673-investigation-chain-cm-six'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def put(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
b=json.loads((ADR/'artifacts/design/bindings.json').read_text())
for p,h in b['files'].items():assert sha(ROOT/p)==h,p
candidate=ROOT/b['candidate'];assert sha(candidate/'candidate.json')==b['candidate_manifest_sha256']
cm=json.loads((candidate/'candidate.json').read_text());rev=next(r for r in cm['revisions'] if r['revision_id']==b['revision_id'])
for row in rev['files']:assert sha(ROOT/row['frozen_path'])==row['snapshot_sha256']
code=candidate/'revisions'/rev['revision_id']/'snapshot'
setup='--setup-only' in sys.argv
case_id=sys.argv[sys.argv.index('--case')+1] if '--case' in sys.argv else 'accounting-manager'
dataset=json.loads((ADR/'artifacts/design/dataset.json').read_text())
case=next(c for c in dataset['cases'] if c['case_id']==case_id)
directory=ADR/'artifacts'/('setup-check' if setup else 'run-001')/case_id;directory.mkdir(parents=True,exist_ok=False)
source=ROOT/b['source_generation'];generation=directory/'generation-shadow'
# Readers use mode=ro; copies of writable cache manifests prevent source mutation.
def copy_file(src,dst):
    if '/cache/' in str(src) or Path(src).suffix=='.json':return shutil.copy2(src,dst)
    os.link(src,dst);return dst
shutil.copytree(source,generation,copy_function=copy_file)
sys.path.insert(0,str(code/'02_BACKEND'));sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('probe_experiment_client',ROOT/'02_BACKEND/lawrag/research/experiment_client.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport, provider_request
from semantic_runtime.legal_agent.errors import ContractError
from fastapi.testclient import TestClient
client=audit.ExperimentClient(ROOT,directory/'provider',max_calls=40,max_output_tokens=6400,max_repairs=0)
class Transport(LocalGemmaTransport):
    def send_once(self,*,body,ticket):
        print('MODEL_START',client.calls+1,flush=True)
        result=client.chat_completions(provider_request(body),phase='product-'+str(client.calls+1),timeout_seconds=ticket['remaining_seconds'])
        raw=result['body_json']
        if raw.get('provider')!='Parasail' or raw.get('model')!=self.binding['model']:raise ContractError('provider binding')
        print('MODEL_DONE',client.calls,client.usage[-1]['seconds'],flush=True)
        return result
transport=Transport(code,ROOT)
profile=json.loads((code/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
profile['model_binding']=transport.binding
principal={'user_id':'adr0673-'+case_id,'team_id':'public-laws','authenticated':True,'document_ids':list(transport.public_scope)}
body={'question':case['question'],'document_ids':list(transport.public_scope),'public_question':True,
      'use_llm':True,'session_id':'adr0673-'+case_id,'request_id':'adr0673-run001-'+case_id}
put(directory/'profile.json',profile);put(directory/'request.json',body)
start=time.monotonic();row={'case_id':case_id,'question':case['question'],'code_root':str(code),'source_generation':str(source),'model':client.model,'field_execution':False,
    'active_pointer_before':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')}
try:
    app=create_app(directory,generation,contracts_root=code,workspace_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',
        legal_agent_profile=profile,legal_agent_transport=transport,runtime_root=directory/'runtime',memory_identity=lambda _:principal)
    from semantic_runtime.stage_runner import StageRunner
    StageRunner(app.state.pipeline).verify_profile()
    with TestClient(app) as api:
        ready=time.monotonic();row['app_setup_seconds']=ready-start
        if setup:
            row.update(http_status=200,setup_only=True)
        else:
            print('ASK_START',flush=True)
            response=api.post('/v1/rag/ask',json=body)
            row.update(http_status=response.status_code,output=response.json(),request_seconds=time.monotonic()-ready)
except Exception as exc:
    row.update(http_status=500,error_type=type(exc).__name__,error=str(exc))
    (directory/'error.txt').write_text(traceback.format_exc())
finally:
    row.update(total_seconds=time.monotonic()-start,model_calls=client.calls,usage=client.usage,
        active_pointer_after=sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'))
    put(directory/'result.json',row)
    print('RESULT',json.dumps({k:v for k,v in row.items() if k not in ('output','usage')},ensure_ascii=False),flush=True)
