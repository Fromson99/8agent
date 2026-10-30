from common import *
import sys,jsonschema,importlib.util,time,copy
f=read(DES/'freeze.json');C=ROOT/f['code_root']
for n,h in f['files'].items():assert sha(C/n)==h,n
for n,h in {**f['inputs'],**f['scripts']}.items():assert sha(ROOT/n)==h,n
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']
assert sha(ART/'technical.log')==f['technical_log_sha256'] and f['technical_passed']==25
sys.path[:0]=[str(C/'02_BACKEND')]
from semantic_runtime.legal_agent.local_gemma import provider_request
from semantic_runtime.legal_agent.navigation_input import NavigationReferences
spec=importlib.util.spec_from_file_location('frozen_experiment_client',C/'02_BACKEND/lawrag/research/experiment_client.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
if '--check-only' in sys.argv:print('Frozen route/client/data passed; newmodel0');raise SystemExit(0)
RUN.mkdir(exist_ok=False)
client=mod.ExperimentClient(ROOT,RUN/'raw',max_calls=5,max_repairs=0,provider_policy=DES/'provider-policy.json');rows=[]
for repeat in (1,2):
 for source in read(DES/'probe-inputs.json'):
  body=read(ROOT/source['body']);assert sha(ROOT/source['body'])==source['body_sha256']
  canonical=read(ROOT/source['canonical']);assert sha(ROOT/source['canonical'])==source['canonical_sha256']
  body.pop('provider',None);body.pop('reasoning',None);body['model']='qwen/qwen3.8-27b'
  name=source['case_id']+'-r'+str(repeat);out=RUN/name;out.mkdir();before=client.calls;usage_before=len(client.usage);start=time.monotonic()
  row={'case_id':source['case_id'],'repeat':repeat,'status':'started','pass':False,'raw_action_pass':False,'declared_goal_pass':False}
  put(out/'dispatch.json',row);print('QWEN',name,client.proxy['allowed_upstream_providers'],flush=True)
  fatal=False
  try:
   raw=client.chat_completions(provider_request(body),phase=name,timeout_seconds=180)
   value=json.loads(raw['body_json']['choices'][0]['message']['content']);put(out/'wire-output.json',value)
   jsonschema.validate(value,body['response_format']['json_schema']['schema']);native=NavigationReferences(canonical['view']).restore(value);jsonschema.validate(native,canonical['schema']);put(out/'output.json',native)
   expected=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1171-source-goal-execution-model-probe/artifacts/evaluation-only/probe-targets.json')[source['case_id']]
   for goal in native.get('source_targets',[]):
    did=canonical['actions'].get(goal['lookup_target'],{}).get('identity',{}).get('document_id')
    row['declared_goal_pass']|=did==expected['document_id'] and goal['coordinate'].replace(' ','')==expected['coordinate'] and goal['coordinate_scope']=='body'
   action=native.get('action',native);choice=action.get('choice');row['choice']=choice
   if choice=='LOCATE':
    identity=canonical['actions'].get(action['target'],{}).get('identity',{});fil=action.get('structure_filter',{})
    row['raw_action_pass']=identity.get('document_id')==expected['document_id'] and fil.get('coordinate','').replace(' ','')==expected['coordinate'] and fil.get('coordinate_scope','body')=='body'
   if choice=='CATALOG_SEARCH':row['raw_action_pass']=any(expected['name'] in q and expected['coordinate'] in q.replace(' ','') for q in action.get('queries',[]))
   if choice=='READ':
    for item in action['selections']:
     cand=next((r for r in canonical['view'].get('read_candidates',[]) if r['target']==item['target']),{})
     row['raw_action_pass']|=cand.get('document_id')==expected['document_id'] and any(p.get('coordinate')==expected['coordinate'] and p.get('coordinate_scope')=='body' for p in cand.get('path',[]))
   row.update(status='complete',**{'pass':row['raw_action_pass'] or row['declared_goal_pass']})
  except (jsonschema.ValidationError,json.JSONDecodeError,mod.ExperimentFormatError) as e:row.update(status='invalid_output',error_type=type(e).__name__,error=str(e)[:800])
  except Exception as e:row.update(status='transport_or_contract_failure',error_type=type(e).__name__,error=str(e),unknown=getattr(e,'unknown',False));fatal=True
  row.update(model_calls=client.calls-before,seconds=time.monotonic()-start,usage=client.usage[usage_before:]);put(out/'result.json',row);rows.append(row);put(RUN/'progress.json',{'cases':rows,'physical_calls':client.calls,'fatal':fatal});print('RESULT',row['status'],row['pass'],round(row['seconds'],2),flush=True)
  if fatal:break
 if fatal:break
put(RUN/'selection.json',{'completed':len(rows),'valid_schema':sum(r['status']=='complete' for r in rows),'exact_target_passed':sum(r['pass'] for r in rows),'full_run_allowed':len(rows)==4 and all(r['pass'] for r in rows),'new_model_calls':client.calls,'provider_switches':client.provider_switches,'usage':client.usage,'quality_certified':False,'MAIN112_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']})
print('DONE',len(rows),'responses',client.calls,'calls','passes',sum(r['pass'] for r in rows),flush=True)
