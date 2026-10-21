from pathlib import Path
import json,hashlib,subprocess,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0876-original-coverage-scope-probe';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert pointer['generation']==84
release=read(R/pointer['manifest_path']);assert all(sha(R/n)==h for n,h in release['files'].items())
put(D/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release':release})
put(D/'data-binding.json',{'path':release['data_path'],'manifest_sha256':release['data_manifest_sha256']})
cm=read(R/'02_BACKEND/lawrag/research/candidates/adr_0874/qualified/candidate.json')
put(D/'working-before.json',{x['target_path']:sha(R/x['target_path']) for x in cm['files']})
criteria={'hypothesis':'Preserve already acquired original context through field selection, keep the requested issue in final comparison, and distinguish unread candidates from missing originals without forced semantic approval.',
 'success':['Exact same-source/side/document context survives final comparison with citations validated against the expanded pair','Issue-specific field observations and current originals reach final comparison','Partial-item proviso evaluated on its actual attachment rather than the entire article','Unread read handles and actual received originals are separately visible; partial/PENDING remains legal without repair loops','Existing MAIN84 acquisition caps, duplicate/resume, ACL/hash and compressed output contracts retained'],
 'failure':['Foreign or cross-issue evidence silently adopted','Unknown originals or model conclusions converted to verified facts','Model uncertainty rejected or extra retry loop introduced','Existing latest working code lost'],
 'failure_owner':'Native navigation owns investigation and bounded PENDING; workflow owns original-context assembly and issue focus; model owns scope/applicability. No new retry owner.',
 'limits':{'max_distinct_acquisition_attempts':2,'max_model_attempts':40,'wall_seconds':1800,'heavy_workers':1,'rss_gib':8,'address_space_gib':9},
 'evaluation':'Known committee and withdrawal end-to-end probe, current selected data unchanged; metadata/RAW coverage audit recorded separately. New independent finite contract qualification before MAIN.',
 'resource_policy':'Read-only shared generation; compact code snapshots; gzip raw provider records after audit. One model workflow at a time.',
 'data_change':'No implicit addition of RAW originals outside selected scope. Missing selected-data targets are explicit, not treated as search failure or proof of legal absence.'}
put(D/'criteria.json',criteria)
cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','scoped','--experiment-id','ADR-0876-experiment-v1','--arm-id','scoped','--run-id','run-001']
for x in cm['files']:cmd+=['--source',x['target_path']]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
m=read(A/'실험/manifest.json');m.update(in_sample=True,decision_eligible=False);m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Original delivery, issue focus, applicability observations and bounded navigation',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
for arm in m['design']['arms']:arm.update(changes='MAIN84 completed actual observation' if arm['id']=='baseline' else 'Exact original-context closure, issue focus, proviso-scope guidance, unread inventory',controls=['Same MAIN84 data/code except reviewed deltas','Actual model via ExperimentClient, no fallback','Physical budgets unchanged'])
m['runs'][0].update(arm_ids=['scoped'],selection_rule=criteria['evaluation'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}];m['dataset'].update(name='original-coverage-known-cases',version='20261018-r1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'))
why='Known-case workflow probe; no approved legal gold. Native/parent/final original sets audited.';m['retrieval_accounting']['not_applicable_reason']=why;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=why;put(A/'실험/manifest.json',m)
print('MAIN84 isolated; prospective criteria saved; data and acquisition cap preserved')
