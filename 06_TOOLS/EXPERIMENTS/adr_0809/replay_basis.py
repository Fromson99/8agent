"""One fixed recorded packet through the new model contract, no retrieval/evaluator."""
from pathlib import Path
import sys,json,hashlib,importlib.util,time,traceback
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0809-system-mechanics-qualification';D=A/'artifacts/design';O=A/'artifacts/replay';O.mkdir(exist_ok=False)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');assert all(sha(R/n)==h for n,h in f['files'].items());C=R/f['code_root'];sys.dont_write_bytecode=True;sys.path[:0]=[str(C/'02_BACKEND'),str(R/'02_BACKEND')]
from workflow.adapters.projection import prepare
from workflow.risk_team_compare_workflow.contracts import BASIS
from workflow.risk_team_compare_workflow.basis import validate as validate_basis
from semantic_runtime.legal_agent.local_gemma import provider_request
from semantic_runtime.legal_agent.model_contract import structured_request,structured_content
from jsonschema import validate
spec=importlib.util.spec_from_file_location('candidate_client',C/'02_BACKEND/lawrag/research/experiment_client.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
criteria=read(D/'criteria.json')['replay'];p=R/criteria['request'];assert sha(p)==criteria['sha256'];archived=read(p);data=json.loads(archived['messages'][1]['content'])['view']
# Restore the exact already-presented quote strings, not a guessed larger source.
for s in data['sources']:
    options=s.pop('citation_options');s['spans']=[{'text':v['text']} for v in options];s['text']='\n'.join(v['text'] for v in options)
sources=data['sources'];view,schema,expand,receipt=prepare('BASIS',data,BASIS)
body=provider_request(structured_request(model='qwen/qwen3.8-27b',max_tokens=criteria['max_output_tokens'],schema_name='WorkflowBasisReplay',schema=schema,
    messages=[archived['messages'][0],{'role':'user','content':json.dumps({'view':view},ensure_ascii=False)}]))
put(O/'binding.json',{'code_root':f['code_root'],'archive_request':criteria,'projection':receipt,'source_count':len(sources),'in_sample':True,'complete_workflow':False,'source_text_rule':'Exact archived presented quote options; no original text inferred','payload_sha256':hashlib.sha256(json.dumps(body,sort_keys=True,ensure_ascii=False).encode()).hexdigest()})
client=mod.ExperimentClient(R,O/'raw',max_calls=1,max_output_tokens=6400,max_repairs=0);start=time.monotonic();result={'status':'complete','canonical_valid':False,'quality_certified':False,'retrieval_executed':False,'whole_workflow_executed':False}
try:
    raw=client.chat_completions(body,phase='workflow-basis-recorded-mechanics',timeout_seconds=180)
    assert raw['body_json']['model']=='qwen/qwen3.8-27b' and raw['body_json']['provider']=='Parasail'
    proposal=json.loads(structured_content(raw['body_json'],require_complete=True));validate(proposal,schema)
    canonical=expand(proposal);validate(canonical,BASIS);validate_basis(canonical,sources,data['scope']['issues'],data.get('as_of'))
    put(O/'canonical-result.json',canonical);result.update(canonical_valid=True,pairs=len(canonical['pairs']),gaps=len(canonical['gaps']))
except Exception as exc:
    result.update(error_type=type(exc).__name__,error=str(exc)[:4000]);traceback.print_exc()
finally:
    result.update(model_calls=client.calls,elapsed_seconds=time.monotonic()-start,usage=client.usage);put(O/'result.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='usage'},ensure_ascii=False))
