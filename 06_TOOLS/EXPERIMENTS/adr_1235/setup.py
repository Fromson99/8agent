from pathlib import Path
import json,hashlib,sys
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1235-gold-ontology-transport-live';D=A/'artifacts/design';O=A/'artifacts/run-001';P=R/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12';D.mkdir(parents=True);O.mkdir()
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
B=R/'04_EXPERIMENTS/ADR/ADR-1234-gold-ontology-reference-repair';F=R/read(B/'artifacts/design/candidate.json')['snapshot'];m=read(A/'실험/manifest.json')
criteria=read(B/'artifacts/design/criteria.json');criteria['hypothesis']='Preserve known HTTP429 as native TransportError so the existing sole gateway switch owns provider retry; unchanged repaired Gold ontology can complete ordinary ASSESS.';criteria['sample']='One known public article369 question once, no replay; same repaired Gold ON/DB with explicit latest DTLS mapping';criteria['success'][0]='Transport failure classification and existing native switch contracts pass';criteria['failures']='Keep failure; one pre-authorized gateway Parasail-to-NearAI switch only on known429; unknown terminates; no repeat after this run'
put(D/'criteria.json',criteria)
for name in ('cases.json','authorization.json','before.json'):put(D/name,read(B/'artifacts/design'/name))
auth=read(D/'authorization.json');auth['dispatches']='One new complete question after correcting the test transport; 40 physical max, one known429 provider switch, UNKNOWN ends run';put(D/'authorization.json',auth)
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Actual Gold ordinary ASSESS to saved final answer',success_criteria=criteria['success'],failure_criteria=['Any required gate false'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((D/'criteria.json').relative_to(R)),'sha256':sha(D/'criteria.json')});m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design']['arms'][0].update(changes='Completed1234 failure kept, not rerun',controls='Historical');m['design']['arms'][1].update(changes='Test transport preserves rejection status/acceptance instead of returning HTTP429 as success',controls='Identical deployed connector2patches/ON/DB/mapping and question; one existing switch policy');m['runs'][0].update(arm_ids=['live'],selection_rule=criteria['sample'],artifact_path=str((O/'result.json').relative_to(R)));m['dataset'].update(name='Public Gold article369 functional test',version='20261030-3',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'));m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}];reason='Transport fix only; no ranking or recall change; exact source/ontology/answer chain audited.';m['retrieval_accounting'].update(changed=False,corpus_total=1,not_applicable_reason=reason);m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason;put(A/'실험/manifest.json',m)
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
base='08_DEPLOYMENT/LOCAL/gold_connection_engine_r12';targets=[base+'/'+x for x in ('connect.py','ontology_settings.json','runtime_patch_binding.json','runtime_patches/navigation_input.py','runtime_patches/ontology_assessment.py')];S=ac.snapshot(A,'live',targets,experiment_id=m['experiment_id'],arm_id='live',run_ids=['run-001']);SP=S/'snapshot';source=(F/'06_TOOLS/EXPERIMENTS/adr_1234/live.py').read_text().replace('adr_1234','adr_1235').replace('ADR-1234-gold-ontology-reference-repair','ADR-1235-gold-ontology-transport-live').replace('gold-ontology-repaired-1234','gold-ontology-transport-1235')
helper='''def preserve_provider_failure(exc):
 from semantic_runtime.legal_agent.errors import TransportError,ContractError
 from lawrag.research.experiment_client import ExperimentProviderError
 response=getattr(exc,'response',None)
 if not isinstance(response,dict) or type(response.get('status_code')) is not int:
  raise TransportError('Experiment adapter has no complete response',retryable=False,unknown=True) from exc
 status=response['status_code']
 if not 200<=status<300:
  response={**response,'acceptance':'KNOWN_REJECTED' if status==429 else 'UNKNOWN' if status>=500 else 'ACCEPTED'}
  raise TransportError('Experiment provider rejected request',response=response,retryable=status==429,unknown=status>=500) from exc
 if isinstance(exc,ExperimentProviderError):raise ContractError('Experiment adapter rejected response policy') from exc
 # A complete HTTP response with a format failure is still validated by the
 # native structured-content/schema boundary. It is never a transport retry.
 return response

'''
source=source.replace('def main():',helper+'def main():');old="   if getattr(exc,'response',None) is not None:return exc.response\n   raise TransportError(str(exc),retryable=False,unknown=True) from exc";assert old in source;source=source.replace(old,'   return preserve_provider_failure(exc)')
entry='06_TOOLS/EXPERIMENTS/adr_1235/live.py';(SP/entry).parent.mkdir(parents=True);(SP/entry).write_text(source);ac.register_file(S,entry,upstream_state='absent');ac.freeze(S);assert not ac.validate(S);rev=read(S/'candidate.json')['revisions'][-1];RF=S/'revisions'/rev['revision_id']/'snapshot';put(D/'candidate.json',{'root':str(S.relative_to(R)),'snapshot':str(RF.relative_to(R)),'entry':str((RF/entry).relative_to(R)),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']});print('Frozen',rev['revision_id'])
