from pathlib import Path
import json,hashlib,subprocess,sys
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent
A=R/'04_EXPERIMENTS/ADR/ADR-0936-durable-research-review-patch';D=A/'artifacts/design';D.mkdir(exist_ok=True)
P=R/'04_EXPERIMENTS/ADR/ADR-0935-lossless-review-wire';PD=P/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
parent=read(P/'실험/manifest.json');assert parent['reservation']['status']=='completed'
base=read(PD/'baseline.json');assert read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer']
put(D/'baseline.json',base);cases=read(PD/'cases.json');put(D/'cases.json',cases)
binding=read(PD/'fixed-binding.json');put(D/'baseline-binding.json',binding)
put(D/'historical-baseline.json',{'experiment_arm':'ADR-0935-experiment-v1/fixed','manifest':str((P/'실험/manifest.json').relative_to(R)),'manifest_sha256':sha(P/'실험/manifest.json'),'results':str((P/'artifacts/run-001/fixed').relative_to(R)),'reused_not_reexecuted':True,'independent_rp_control':'04_EXPERIMENTS/ADR/ADR-0931-general-research-evidence-update/artifacts/design/rp_only-binding.json'})
criteria=read(PD/'criteria.json');criteria.update(
 hypothesis='Preserve explicit unresolved research needs independently of optional next_tasks. Compile bounded fallback searches only from a model-declared missing target, retain pending plans until an explicit grounded resolution, and rotate broad-search sides within the existing acquisition cap. Use canonical judgment names in read-only history and accept closed flat or nested side patches with audited lossless assembly; no semantic defaults, question-specific rules, native selector changes or RP fix changes.',
 required=['Every nonempty model-declared missing target has a durable need receipt and either a matching task or an explicit attempted/blocked/budget reason.', 'Empty next_tasks alone never cancels an unresolved need or pending task; explicit source-backed cleared missing resolves it with history.', 'Different broad queries do not collide in task identity, same exact read can be coalesced across fields; no reset of attempts/deadline.', 'Prioritize witnessed necessary targets before broad search; among broad tasks rotate sides already investigated, preserving legacy order when the policy is off.', 'Read-only and submitted judgment names agree; closed flat and nested patches normalize without changing judgment/side/text/citations.', 'Conflicting aliases, duplicate field-side patches, unknown keys/IDs, opposite-side citations and stale bindings remain rejected.', 'No additional repair owner or retry budget. Original malformed output remains recorded.', 'Source accounting and host-derived actual citation links retained; all prior grounded findings and omitted plans preserved.', 'Independent RP patch and native source selector remain byte-identical to completed parent; MAIN89 and working product unchanged.', 'Same four public topic questions execute once each, with exact source/consumer/scope/omission review against historical0935 and independentRP record.'],
 controls='Completed ADR0935/fixed rev002 historical baseline; same native selector, data, model, requests and budgets. Change only workflow review projection, durable research planning and version pins. No fresh randomized control.',
 selection='Four fixed sequential requests: PF, RP, provision, leverage. One each, no adaptive rerun.',
 failure_owner='Existing workflow adapter owns one schema correction; native investigation owns its existing correction. New host normalizations are fixed pure representation rules followed by all existing source/scope/state checks. Fallback research uses existing two-acquisition budget and existing duplicate receipts; uncertainty remains visible and is not a new blocking gate.',
 limits={'workers':1,'rss_gib':6,'as_gib':8,'min_available_gib':4,'min_disk_gib':10,'max_new_calls':160,'wall_seconds_per_request':1800})
put(D/'criteria.json',criteria);put(D/'offline-audit-only.json',read(PD/'offline-audit-only.json'))
put(D/'schedule.json',[{'arm':'fixed','case_id':c} for c in ['pf-downgrade','rp-bond-scope','provision-comparison','leverage']])
names=read(PD/'serving-files.json');put(D/'serving-files.json',names);put(D/'working-before.json',{n:sha(R/n) for n in names})
put(D/'working-drift.json',read(PD/'working-drift.json'))
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Source-accounted updates and known core evidence retention',success_criteria=criteria['required'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-0935-experiment-v1/fixed'],'changes':'Reuse completed parent observations, no new calls','controls':criteria['controls']},{'id':'fixed','role':'candidate','derived_from':['baseline'],'changes':criteria['hypothesis'],'controls':criteria['controls']}]
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
C=R/'02_BACKEND/lawrag/research/candidates/adr_0936/fixed/snapshot';S=R/binding['code_root']
for n in names:
 assert sha(S/n)==binding['serving_files'][n]
 (C/n).write_bytes((S/n).read_bytes())
rp=R/read(R/'04_EXPERIMENTS/ADR/ADR-0931-general-research-evidence-update/artifacts/design/rp_only-binding.json')['code_root']
(C/'02_BACKEND/semantic_runtime/legal_agent/source_investigation.py').write_bytes((rp/'02_BACKEND/semantic_runtime/legal_agent/source_investigation.py').read_bytes())
print('Parent0935 bound, durable-needs and review-patch design fixed, isolated candidate prepared.')
