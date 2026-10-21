from pathlib import Path
import json,hashlib,subprocess,sys
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent
A=R/'04_EXPERIMENTS/ADR/ADR-0932-packet-evidence-update';D=A/'artifacts/design';D.mkdir(exist_ok=True)
P=R/'04_EXPERIMENTS/ADR/ADR-0931-general-research-evidence-update';PD=P/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
parent=read(P/'실험/manifest.json');assert parent['reservation']['status']=='completed'
base=read(PD/'baseline.json');assert read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer']
put(D/'baseline.json',base);cases=read(PD/'cases.json');put(D/'cases.json',cases)
binding=read(PD/'generalized-binding.json');put(D/'baseline-binding.json',binding)
put(D/'historical-baseline.json',{'experiment_arm':'ADR-0931-experiment-v1/generalized','manifest':str((P/'실험/manifest.json').relative_to(R)),'manifest_sha256':sha(P/'실험/manifest.json'),'results':str((P/'artifacts/run-001/generalized').relative_to(R)),'reused_not_reexecuted':True,'independent_rp_control':str((PD/'rp_only-binding.json').relative_to(R))})
criteria=read(PD/'criteria.json');criteria.update(hypothesis='Preserve existing native source decisions while accounting for each new original, updating every later packet incrementally and showing prior decisions only as read-only history; preserve failed-new-original receipts.',
 required=['Independent RP fix and MAIN89 retained; no question/article-specific behavior.','Every initial/follow-up new original receives a disposition bound to actual changed-field citations when USED.','Later initial packets update only changed fields/sides; previous findings survive packet boundaries.','Prior state is read-only model context, separate from minimal submission shape; malformed responses stay rejected.','Failed update preserves unresolved receipt and exact newly delivered originals; no new retries, silent success or budget reset.','Same four known questions audited against reused completed parent and independent RP-only record; all previously supported core sources and missing statements manually reviewed.','Normal/failure/duplicate/resume/source/ACL/hash checks plus actual pinned service entry.'],
 controls='Completed ADR0931 generalized rev004 parent, same data/model/profile; restore source_investigation.py exactly to RP-only. Parent observations reused, not freshly paired. One fixed request per same known question.',
 selection='Four prospective fixed requests, PF then RP then provision then leverage; no adaptive rerun. Historical baseline is completed0931/generalized.',
 failure_owner='Existing workflow adapter owns one schema correction, native source output_contract its correction; no extra retries. New-source failure receipts persist before partial termination. Prospectively bounded Linux wall-clock alarm caps each physical external call at180s; unknown provider outcome is not retried.',
 limits={'workers':1,'rss_gib':6,'as_gib':8,'min_available_gib':4,'min_disk_gib':10,'max_new_calls':160,'wall_seconds_per_request':1800})
put(D/'criteria.json',criteria);put(D/'offline-audit-only.json',read(PD/'offline-audit-only.json'))
put(D/'schedule.json',[{'arm':'fixed','case_id':c} for c in ['pf-downgrade','rp-bond-scope','provision-comparison','leverage']])
names=read(PD/'serving-files.json');put(D/'serving-files.json',names);put(D/'working-before.json',{n:sha(R/n) for n in names})
put(D/'working-drift.json',read(PD/'working-drift.json'))
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Source-accounted updates and known core evidence retention',success_criteria=criteria['required'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-0931-experiment-v1/generalized'],'changes':'Reuse completed parent observations, no new calls','controls':criteria['controls']},{'id':'fixed','role':'candidate','derived_from':['baseline'],'changes':criteria['hypothesis'],'controls':criteria['controls']}]
m['runs'][0].update(arm_ids=['fixed'],selection_rule=criteria['selection'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='same-known-cm-three-plus-leverage',version='20261019-r1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
m['llm_policy']['llm_calls']=[{'role':'workflow_and_native_rag','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0,'max_calls':160}]
stages=[{'stage_id':'acquired','kind':'source','parent_stage_ids':[]},{'stage_id':'returned','kind':'select','parent_stage_ids':['acquired']},{'stage_id':'cited','kind':'present','parent_stage_ids':['returned']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','fixed')}
m['retrieval_accounting'].update(changed=True,not_applicable_reason='Exact read/return/presentation identities; approved legal gold unavailable.')
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','fixed','--experiment-id',m['experiment_id'],'--arm-id','fixed','--run-id','run-001']
for n in names:cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0932/fixed/snapshot';S=R/binding['code_root']
for n in names:
 assert sha(S/n)==binding['serving_files'][n]
 (C/n).write_bytes((S/n).read_bytes())
rp=R/read(PD/'rp_only-binding.json')['code_root']
(C/'02_BACKEND/semantic_runtime/legal_agent/source_investigation.py').write_bytes((rp/'02_BACKEND/semantic_runtime/legal_agent/source_investigation.py').read_bytes())
print('Reserved parent bound, design fixed, isolated candidate prepared; native source policy restored.')
