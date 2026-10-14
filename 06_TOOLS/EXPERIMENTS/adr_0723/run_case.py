"""One frozen full API request per process; all physical calls are audited."""
from pathlib import Path
import argparse, hashlib, json, os, sys, time, traceback
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0723-source-target-recovery-complete';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
parser=argparse.ArgumentParser();parser.add_argument('--arm',required=True,choices=['baseline','integrated']);parser.add_argument('--case',required=True);parser.add_argument('--setup-only',action='store_true');args=parser.parse_args()
f=read(D/'freeze.json')
for name,h in f['files'].items():assert sha(R/name)==h,name
bindings=read(D/'bindings.json')
code=R/bindings['codes'][args.arm]
out=A/'artifacts'/('setup-check' if args.setup_only else 'run-001')/args.arm/args.case
out.mkdir(parents=True,exist_ok=False)
assert not any(os.environ.get(k) for k in ('GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_STATE_DIR','LEGAL_AGENT_PROFILE','GENOS_RAG_MAX_MODEL_ATTEMPTS','GENOS_RAG_MAX_TOOL_ACTIONS','GENOS_RAG_WALL_SECONDS','GENOS_RAG_SEARCH_ROUNDS','GENOS_RAG_ASSESSMENT_REENTRY_LIMIT'))
sys.dont_write_bytecode=True;sys.path.insert(0,str(code/'02_BACKEND'))
import importlib.util
spec=importlib.util.spec_from_file_location('frozen_experiment_client',R/bindings['experiment_client']);audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
ExperimentClient=audit.ExperimentClient
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport,provider_request
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent.workflow_tiers_policy import profile as validate_profile
from semantic_runtime.stage_runner import StageRunner
from semantic_runtime.legal_agent.unified_runtime import open_cases
from fastapi.testclient import TestClient

client=ExperimentClient(R,out/'provider',max_calls=40,max_output_tokens=6400,max_repairs=0)
attempts=[]
class Transport(LocalGemmaTransport):
    def send_once(self,*,body,ticket):
        view=json.loads(body['messages'][1]['content'])['view'];phase=view.get('source_stage',view['phase'])
        attempt={'call':len(attempts)+1,'phase':phase};attempts.append(attempt);started=time.perf_counter()
        print('MODEL_START',args.arm,args.case,attempt['call'],phase,flush=True)
        try:
            result=client.chat_completions(provider_request(body),phase='product-'+str(attempt['call'])+'-'+phase,timeout_seconds=ticket['remaining_seconds'])
            raw=result['body_json']
            if raw.get('provider')!='Parasail' or raw.get('model')!=self.binding['model']:raise ContractError('provider binding')
            attempt['status']='completed';return result
        except BaseException as exc:
            attempt.update(status='failed',error_type=type(exc).__name__);raise
        finally:
            attempt['seconds']=time.perf_counter()-started
            put(out/'attempts.json',attempts)
            print('MODEL_DONE',attempt['call'],round(attempt['seconds'],3),attempt['status'],flush=True)

transport=Transport(code,R)
policy=read(code/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
policy.update(model_binding=transport.binding,max_output_tokens=transport.policy['max_output_tokens'])
policy=validate_profile(policy,require_model=True)
assert policy['max_output_tokens']==6400 and policy['max_model_attempts']==40
case=next(c for c in read(D/'dataset.json')['cases'] if c['case_id']==args.case)
principal={'user_id':'adr0723-probe','team_id':'public-laws','authenticated':True,'document_ids':list(transport.public_scope)}
body={'question':case['question'],'document_ids':list(transport.public_scope),'public_question':True,'use_llm':True,
      'session_id':'adr0723-'+args.arm+'-'+args.case,'request_id':'adr0723-run001-'+args.arm+'-'+args.case}
put(out/'request.json',body);put(out/'profile.json',policy)
start=time.perf_counter();ready=None
row={'case_id':args.case,'arm':args.arm,'field_execution':False,'code_root':str(code.relative_to(R)),
    'source_generation':bindings['source_generation'],'active_pointer_before':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
    'profiling_enabled':False,'profile_sha256':hashlib.sha256(json.dumps(policy,sort_keys=True,separators=(',',':')).encode()).hexdigest()}
try:
    app=create_app(out,R/bindings['source_generation'],contracts_root=code,workspace_root=R,provider=object(),
        implementation='legal-agent-unified-v6',legal_agent_profile=policy,legal_agent_transport=transport,
        runtime_root=out/'runtime',memory_identity=lambda _:principal)
    StageRunner(app.state.pipeline).verify_profile()
    cases=open_cases(app.state.pipeline,out/'binding-runtime',{},principal)
    try:row['expected_binding']=cases.executor.binding
    finally:cases.close()
    with TestClient(app) as api:
        ready=time.perf_counter();row['app_setup_seconds']=ready-start
        if args.setup_only:row.update(setup_only=True,http_status=200)
        else:
            print('ASK_START',args.arm,args.case,flush=True)
            response=api.post('/v1/rag/ask',json=body)
            row.update(http_status=response.status_code,output=response.json(),request_seconds=time.perf_counter()-ready)
except BaseException as exc:
    row.update(http_status=500,error_type=type(exc).__name__,error=str(exc))
    if ready is not None and not args.setup_only:row['request_seconds']=time.perf_counter()-ready
    (out/'error.txt').write_text(traceback.format_exc())
finally:
    row.update(total_seconds=time.perf_counter()-start,model_calls=client.calls,usage=client.usage,attempts=attempts,
               active_pointer_after=sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'))
    put(out/'result.json',row)
    print('RESULT',json.dumps({k:row.get(k) for k in ('arm','case_id','http_status','request_seconds','model_calls','error_type','error')},ensure_ascii=False),flush=True)
