"""One exact public reference-menu replay against the frozen candidate schema."""
from pathlib import Path
import hashlib,importlib.util,json,sys,time
from jsonschema import validate
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0670-public-provider-schema-adapter'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
b=json.loads((ADR/'artifacts/design/bindings.json').read_text())
for p,h in b['files'].items():assert sha(ROOT/p)==h,p
c=ROOT/b['candidate'];assert sha(c/'candidate.json')==b['candidate_manifest_sha256']
cm=json.loads((c/'candidate.json').read_text());rev=next(r for r in cm['revisions'] if r['revision_id']==b['revision_id'])
for r in rev['files']:assert sha(ROOT/r['frozen_path'])==r['snapshot_sha256']
code=c/'revisions'/rev['revision_id']/'snapshot';sys.path.insert(0,str(code/'02_BACKEND'));sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('audit_experiment_client',ROOT/'02_BACKEND/lawrag/research/experiment_client.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
from semantic_runtime.legal_agent import unit_relations as rel
from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport, provider_request
transport=LocalGemmaTransport(code,ROOT)
data=json.loads((ADR/'artifacts/design/replay-data.json').read_text())
case=json.loads((ADR/'artifacts/design/dataset.json').read_text())['cases'][0]
assert data['question']==case['compiled_task']
for g in data['groups']:
 assert g['target']['document_id'] in transport.public_scope
 assert g['anchor']['document_id'] in transport.public_scope
 for x in g['connections']:assert x['witness_document_id'] in transport.public_scope
body=json.loads((ADR/'artifacts/design/replay-request.json').read_text())
offered=json.loads((ADR/'artifacts/design/offered.json').read_text())
shape=rel.schema(offered);body['response_format']['json_schema']['schema']=shape
body=provider_request(body)
out=ADR/'artifacts/run-001/reference-menu-v6';out.mkdir(parents=True,exist_ok=False)
put(out/'validation-schema.json',shape);put(out/'request.json',body)
client=audit.ExperimentClient(ROOT,out/'provider',max_calls=1,max_output_tokens=6400,max_repairs=0)
start=time.monotonic();r={'case_id':'reference-menu-v6','question':case['question'],'compiled_task':data['question'],'scope':'reference menu only, no READ or full API rerun',
 'active_pointer_before':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'field_execution':False,'revision_id':rev['revision_id']}
try:
 result=client.chat_completions(body,phase='reference-replay',timeout_seconds=180)
 raw=result['body_json'];assert raw.get('model')==client.model and raw.get('provider')=='Parasail'
 value=json.loads(raw['choices'][0]['message']['content']);validate(value,shape);rel.validate(value,offered)
 # The actual menu includes obligations for all links, including omitted witnesses.
 for d in value['decisions']:
  group=next(g for g in data['groups'] if g['id']==d['id'])
  for obligation in group['reading_obligations']:
   if obligation['already_read']:continue
   if d['action']=='SKIP':
    assert obligation['obligation']!='REQUIRED'
    assert obligation['obligation']!='CHECK_APPLICABILITY' or d['applicability']=='DOES_NOT_APPLY'
   if d['action']=='FOLLOW':assert set(d['scopes']) & set(obligation['covering_scopes'])
 put(out/'decision.json',value)
 r.update(http_status=200,status='complete',decision_count=len(value['decisions']),all_reasons_present=all(d['reason'].strip() for d in value['decisions']),schema_repairs=0)
except Exception as exc:
 r.update(http_status=502,status='failed',error_type=type(exc).__name__,error=str(exc))
finally:
 r.update(seconds=time.monotonic()-start,model_calls=client.calls,usage=client.usage,active_pointer_after=sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'))
 put(out/'result.json',r);print(json.dumps(r,ensure_ascii=False),flush=True)
