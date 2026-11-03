from pathlib import Path
import json,shutil,hashlib,sys
ROOT=Path('/home/jin/8-AGENT');OLD=ROOT/'04_EXPERIMENTS/ADR/ADR-1296-local-ontology-ab-derived-grant';ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1298-local-ontology-ab-native-grant';ART=ADR/'artifacts';DES=ART/'design';T=Path(__file__).parent
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert read(OLD/'실험/manifest.json')['reservation']['status']=='completed'
for name in ('common.py','live.py','freeze.py','run_all.py','pinned_imports.py','resource_guard.py','authorization.py'):
 s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1296'/name).read_text().replace('ADR-1296-local-ontology-ab-derived-grant','ADR-1298-local-ontology-ab-native-grant').replace('adr_1296','adr_1298').replace('adr1296','adr1298').replace('ADR1296','ADR1298')
 if name=='authorization.py':s=s.replace("body.get('use_llm') is not True","body.get('public_question') is not True").replace("'use_llm':True","'public_question':True").replace("('use_llm',False)","('public_question',False)")
 if name=='live.py':
  s=s.replace("preflight='--preflight' in sys.argv","preflight='--preflight' in sys.argv;replay='--grant-replay' in sys.argv;replay_sends=[]")
  s=s.replace("('preflight' if preflight else 'live')","('replay' if replay else 'preflight' if preflight else 'live')")
  s=s.replace('if not preflight:\n','if not (preflight or replay):\n',1)
  s=s.replace("effective=derive(body,state,case['question'],allowed,'adr1298-'+base.name)","""# Product maps the public session to an authenticated internal case.
  linked=host.shortcut.investigation(host.active_case,principal,'adr1298-'+base.name)
  assert linked['id']==host.active_case
  effective=derive(body,state,case['question'],allowed,host.active_case)""")
  s=s.replace("if preflight:raise RuntimeError('PREFLIGHT_EXTERNAL_SEND_FORBIDDEN')", """if replay:
   replay_sends.append({'number':len(replay_sends)+1,'stage':active[-1] if active else None})
   put(base/'replay-sends.json',replay_sends)
   if len(replay_sends)==1:
    original=ROOT/'04_EXPERIMENTS/ADR/ADR-1294-local-ontology-ab-memory-map/artifacts/live/ontology-365-baseline/raw/call-001/response.json.gz'
    with gzip.open(original,'rt') as f:raw=json.load(f)
    put(base/'replayed-response.json',{'path':str(original.relative_to(ROOT)),'sha256':sha(original),'physical_calls':0})
    return {'status_code':200,'body_json':raw}
   put(base/'replay-boundary.json',{'second_gateway_authorization_passed':True,'derivations':len(derivations),'physical_calls':0})
   raise errors.ContractError('REPLAY_BOUNDARY_REACHED_NO_PHYSICAL_SEND')
  if preflight:raise RuntimeError('PREFLIGHT_EXTERNAL_SEND_FORBIDDEN')""")
  s=s.replace("put(base/'result.json',result);print('LIVE_RESULT'", """if replay:
   result.update(replay_only=True,second_gateway_authorization_passed=(base/'replay-boundary.json').exists(),physical_calls=0)
   assert result['second_gateway_authorization_passed'] and len(derivations)>=1 and len(replay_sends)==2
  put(base/'result.json',result);print('LIVE_RESULT'""")
 (T/name).write_text(s)
DES.mkdir(exist_ok=False)
for name in ('baseline.json','scoring-only-originals.json','comparison-source.json','root-files.json','ontology-on.json','ontology-off.json','cases.json'):
 shutil.copyfile(OLD/'artifacts/design'/name,DES/name)
criteria=read(OLD/'artifacts/design/criteria.json');criteria['design']['harness_correction']='Verify ShortcutRepository.investigation binds internal case to original public session and principal; validate original question/initial ID/public_question plus internal case; preserve all typed task/facts. Replay preserved entry response through nativeAPI and require second gateway authorization before any physical live call.';put(DES/'criteria.json',criteria)
auth=read(OLD/'artifacts/design/authorization.json');auth['derived_context']=criteria['design']['harness_correction'];put(DES/'authorization.json',auth)
m=read(ADR/'실험/manifest.json');before=read(OLD/'artifacts/preregistered-manifest-before-final-accounting.json')
for k in ('design','llm_policy','dataset','retrieval_accounting'):m[k]=before[k]
m['lineage']['hypothesis_delta']='Same two ON/OFF pairs on MAIN133; native internal case authorization verified by preserved-response replay before live calls; product unchanged.'
m['design']['code_isolation']['candidates']=[];m['design']['arms'][0]['derived_from']=['ADR-1296-experiment-v1/ontology-on']
m['design']['criteria_freeze_evidence']={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')}
m['dataset'].update(frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),version='20261103-native-grant-v1')
m['runs'][0].update(arm_ids=['baseline','ontology-on'],artifact_path=str((ART/'run-001/result.json').relative_to(ROOT)),selection_rule='Same2publicquestions;365OFFthenON,369ONthenOFF;oneattemptpercell;stoponunknown/resource/5xx; nativegrantreplayrequired')
put(ADR/'실험/manifest.json',m)
b=read(DES/'baseline.json');code=ROOT/b['release']['code_root'];files=b['release']['files'];assert all(sha(code/n)==h for n,h in files.items())
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
paths=[str((code/n).relative_to(ROOT)) for n in files]+['02_BACKEND/lawrag/research/experiment_client.py','02_BACKEND/lawrag/research/openrouter_legal_adapter.py','02_BACKEND/lawrag/core/request_deadline.py']
candidate=ac.snapshot(ADR,'selected-main133',paths,experiment_id=m['experiment_id'],arm_id='ontology-on',run_ids=['run-001']);ac.freeze(candidate);assert not ac.validate(candidate)
cm=read(candidate/'candidate.json');rev=cm['revisions'][-1];snap=candidate/'revisions'/rev['revision_id']/'snapshot'
put(DES/'candidate.json',{'code_root':str((snap/b['release']['code_root']).relative_to(ROOT)),'snapshot_root':str(snap.relative_to(ROOT)),'pin':{'manifest_path':str((candidate/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(candidate/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']},'selected_files':files})
for folder in ('transport','gold-connector'):shutil.copytree(OLD/'artifacts'/folder,ART/folder)
print('PREPARED1298 identical513productfiles; nativecasegrant; replayrequired')
