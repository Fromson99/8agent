from common import *
import shutil,urllib.request,datetime
parent=ROOT/'04_EXPERIMENTS/ADR/ADR-1398-lifecycle-alternate-providers/artifacts'
criteria=read(DES/'criteria.json');cases=read(parent/'design/live-cases.json')
for c in cases:c['arms']=['repaired']
put(DES/'live-cases.json',cases)
for n in ('source-scope','prefix'):put(DES/(n+'.json'),read(parent/'design'/(n+'.json')))
url='https://openrouter.ai/api/v1/models/qwen/qwen3.8-27b/endpoints'
with urllib.request.urlopen(url,timeout=30) as response:endpoints=json.load(response)
put(ART/'provider-endpoints.json',endpoints);put(ART/'provider-endpoints-receipt.json',{'url':url,'fetched_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'llm_calls':0})
for cid in ('reka','deepinfra'):
 p=read(parent/'design'/('provider-'+cid+'.json'))
 assert any(e.get('tag')==p['providers'][0]['tag'] and e.get('status')==0 for e in endpoints['data']['endpoints'])
 p['authorization'].update(text=criteria['authorization'],session_id=read(ADR/'실험/manifest.json')['reservation']['session_id'])
 p['metadata']={'path':str((ART/'provider-endpoints.json').relative_to(ROOT)),'sha256':sha(ART/'provider-endpoints.json')}
 put(DES/('provider-'+cid+'.json'),p)
auth=read(parent/'design/authorization.json');auth.update(user_request=criteria['authorization'],cases_sha256=sha(DES/'live-cases.json'));put(DES/'authorization.json',auth)
shutil.copytree(parent/'transport',ART/'transport')
m=read(ADR/'실험/manifest.json')
for a in m['design']['arms']:a.update(changes='Historical1398 only' if a['id']=='baseline' else 'Two modules: preview, independent intent fields, mechanical intent/action constraints, one original repair and applied-state guard',controls='Same1398 original/source/profile/data/provider and fixed successful5-response prefix; no MAIN changes')
m['runs'][0].update(arm_ids=['repaired'],selection_rule='REKA then DeepInfra independent sessions, one each; fixed historical first5 responses, T3 onward actual. Unknown quarantines only that provider. No same-provider retry.',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['dataset'].update(name='Actual1398 followup/newtopic/condition failures with repaired current-state contracts',version='ADR1400-r1',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'))
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','repaired')};m['retrieval_accounting']['stage_ledger'].update(mode='measured',not_applicable_reason=None);put(ADR/'실험/manifest.json',m)
paths=[*Path(__file__).parent.glob('*.py'),*[p for p in (ART/'transport').rglob('*') if p.is_file()],*DES.glob('*.json')]
put(DES/'freeze-public.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths if p.name!='freeze-public.json'},'before_model_calls':True})
print('Provider inputs, native runner and fixed-prefix contract frozen; no model calls.')
