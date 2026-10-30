from common import *
import sys,time,copy,jsonschema
f=read(DES/'freeze.json');C=ROOT/f['code_root'];sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT/'02_BACKEND')]
from semantic_runtime.legal_agent.local_gemma import provider_request
from semantic_runtime.legal_agent.navigation_input import NavigationReferences
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
from lawrag.research.experiment_client import ExperimentClient,OpenRouterProxyClient,ExperimentTransportError,ExperimentProviderError,ExperimentFormatError
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']
for n,h in f['files'].items():assert sha(C/n)==h,n
for n,h in f['inputs'].items():assert sha(ROOT/n)==h,n
for n,h in f['scripts'].items():assert sha(ROOT/n)==h,n
check=read(ART/('check-'+f['candidate_revision']['revision_id']+'.json'));assert check['failed']==0 and not check['import_leaks']
inputs=read(DES/'probe-inputs.json');criteria=read(DES/'criteria.json');models=criteria['comparison']['models']
if '--check-only' in sys.argv:
 print('Probe inputs/code checked; no model calls');raise SystemExit(0)
# Evaluation locators are opened only after each product call has returned.
base=ART/'model-probe';base.mkdir(exist_ok=True);rows=[];unavailable=set()
for repeat in range(2):
 for i,source in enumerate(inputs):
  for model in (models if (repeat+i)%2==0 else list(reversed(models))):
   out=base/('qwen38' if model==models[0] else 'genos122')/source['case_id']/str(repeat+1)
   if (out/'result.json').exists():
    prior=read(out/'result.json')
    if prior['status']!='provider_failure':raise RuntimeError('Completed successful/semantic cell cannot be rerun')
    response=read(next((out/'raw').glob('call-*/response.json')))
    if response.get('error',{}).get('code')!=429 or prior.get('unknown'):raise RuntimeError('Prior unsafe provider outcome stops experiment')
    prior=dict(prior,model_calls=len(list((out/'raw').glob('call-*'))),seconds=None,usage=[],unavailable=True)
    rows.append(prior);unavailable.add(model);continue
   if model in unavailable:
    row={'model':model,'case_id':source['case_id'],'repeat':repeat+1,'status':'not_run_provider_unavailable','pass':False,'raw_action_pass':False,'declared_goal_pass':False,'model_calls':0,'seconds':None,'usage':[]}
    rows.append(row);put(out/'result.json',row);continue
   if (out/'dispatch.json').exists():raise RuntimeError('Previously dispatched cell with unknown outcome; no replay')
   body=read(ROOT/source['body']);assert sha(ROOT/source['body'])==source['body_sha256']
   canonical=read(ROOT/source['canonical']);assert sha(ROOT/source['canonical'])==source['canonical_sha256']
   body['model']=model;body.pop('provider',None);body.pop('reasoning',None)
   client=(ExperimentClient if model==models[0] else OpenRouterProxyClient)(ROOT,out/'raw',max_calls=1,max_repairs=0)
   row={'model':model,'case_id':source['case_id'],'repeat':repeat+1,'status':'started','pass':False,'raw_action_pass':False,'declared_goal_pass':False}
   put(out/'dispatch.json',row);print('PROBE',model,source['case_id'],repeat+1,flush=True)
   started=time.monotonic()
   try:
    raw=client.chat_completions(provider_request(body),phase='saved-next-action',timeout_seconds=180)
    value=json.loads(raw['body_json']['choices'][0]['message']['content']);jsonschema.validate(value,body['response_format']['json_schema']['schema'])
    native=NavigationReferences(canonical['view']).restore(value);jsonschema.validate(native,canonical['schema']);put(out/'output.json',native)
    expected=read(ART/'evaluation-only/probe-targets.json')[source['case_id']]
    for target in native.get('source_targets',[]):
     actual=canonical['actions'].get(target['lookup_target'],{}).get('identity',{}).get('document_id')
     if actual==expected['document_id'] and target['coordinate'].replace(' ','')==expected['coordinate'] and target['coordinate_scope']=='body':row['declared_goal_pass']=True
    action=native.get('action',native);choice=action.get('choice');row['choice']=choice
    if choice=='LOCATE':
     actual=canonical['actions'].get(action.get('target'),{}).get('identity',{}).get('document_id');fil=action.get('structure_filter',{})
     row['raw_action_pass']=actual==expected['document_id'] and fil.get('coordinate','').replace(' ','')==expected['coordinate'] and fil.get('coordinate_scope','body')=='body'
    if choice=='CATALOG_SEARCH':row['raw_action_pass']=any(expected['name'] in q and expected['coordinate'] in q.replace(' ','') for q in action.get('queries',[]))
    if choice=='READ':
     for item in action.get('selections',[]):
      candidate=next((r for r in canonical['view'].get('read_candidates',[]) if r['target']==item['target']),{})
      row['raw_action_pass']|=candidate.get('document_id')==expected['document_id'] and any(p.get('coordinate')==expected['coordinate'] and p.get('coordinate_scope')=='body' for p in candidate.get('path',[]))
    row.update(status='complete',**{'pass':row['declared_goal_pass'] or row['raw_action_pass']})
   except (ExperimentTransportError,ExperimentProviderError) as e:
    row.update(status='provider_failure',error_type=type(e).__name__,error=str(e),unknown=getattr(e,'unknown',False),seconds=time.monotonic()-started,model_calls=client.calls,usage=client.usage);put(out/'result.json',row);rows.append(row);put(base/'results.json',rows)
    if (getattr(e,'response',None) or {}).get('status_code')==429 and not row['unknown']:
     unavailable.add(model);continue
    raise
   except (ExperimentFormatError,jsonschema.ValidationError,json.JSONDecodeError) as e:row.update(status='invalid_output',error_type=type(e).__name__,error=str(e)[:1200])
   row.update(seconds=time.monotonic()-started,model_calls=client.calls,usage=client.usage)
   put(out/'result.json',row);rows.append(row);put(base/'results.json',rows);print('RESULT',row['status'],row['pass'],round(row['seconds'],2),flush=True)
summary={model:{'passed':sum(r['pass'] for r in rows if r['model']==model),'raw_action_passed':sum(r['raw_action_pass'] for r in rows if r['model']==model),'seconds':sum(r['seconds'] or 0 for r in rows if r['model']==model),'total':sum(r['model']==model for r in rows),'available':model not in unavailable} for model in models}
eligible=[m for m,s in summary.items() if s['passed']==4 and s['total']==4 and s['available']]
winner=min(eligible,key=lambda m:summary[m]['seconds']) if eligible else None
put(base/'selection.json',{'models':summary,'selected_model':winner,'full_run_allowed':bool(winner),'rule':criteria['comparison']['pass'],'new_model_calls':sum(r['model_calls'] for r in rows),'quality_certified':False})
print(json.dumps(summary), 'SELECTED',winner,flush=True)
