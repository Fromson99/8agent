from pathlib import Path
import sys,json,hashlib,copy,shutil
R=Path(__file__).resolve().parents[3];sys.dont_write_bytecode=True;sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
D=R/'04_EXPERIMENTS/ADR/ADR-0964-scoped-main-integration';A=D/'artifacts';P=R/'04_EXPERIMENTS/ADR/ADR-0963-scoped-final-qualification';PA=P/'artifacts';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
pm=json.loads((P/'실험/manifest.json').read_text());parent=json.loads((R/pm['design']['code_isolation']['candidates'][0]['manifest_path']).read_text());paths=[r['target_path'] for r in parent['files']];seal=json.loads((PA/'stage.json').read_text());stage=A/'code';shutil.copytree(R/seal['code_root'],stage)
new='02_BACKEND/semantic_runtime/legal_agent/request_repair.py';shutil.copyfile(R/new,stage/new)
for p in (stage/'02_BACKEND/ENGINES').rglob('*.json'):
 v=json.loads(p.read_text())
 if 'files' in v:
  for n in v['files']:v['files'][n]=sha(stage/n)
  save(p,v)
p=stage/'00_SYSTEM/PIPELINE.json';v=json.loads(p.read_text())
def pins(v):
 if isinstance(v,dict):
  if v.get('manifest') and 'sha256' in v and (stage/v['manifest']).is_file():v['sha256']=sha(stage/v['manifest'])
  for x in v.values():pins(x)
 elif isinstance(v,list):
  for x in v:pins(x)
pins(v);save(p,v)
changed=[n for n,h in seal['files'].items() if sha(stage/n)!=h];assert all(n==new or n.startswith('02_BACKEND/ENGINES/') or n=='00_SYSTEM/PIPELINE.json' for n in changed)
# Final source receipt changes only; live command path and prompts remain byte-identical.
command_paths=['corrected_memory','memory_methods','request_entry','query_scope','output_contract']
assert all(sha(stage/f'02_BACKEND/semantic_runtime/legal_agent/{n}.py')==seal['files'][f'02_BACKEND/semantic_runtime/legal_agent/{n}.py'] for n in command_paths)
save(A/'integration-delta.json',{'changed':changed,'functional_file':new,'command_path_unchanged':command_paths,'reason':'Keep concurrent exact target lookup absence receipt; no model/prompt/search change from qualified parent.'})
seal['code_root']=str(stage.relative_to(R));seal['files']={n:sha(stage/n) for n in seal['files']};seal['working_baseline']={n:sha(R/n) if (R/n).is_file() else None for n in seal['files']};save(A/'stage.json',seal)
C=ac.snapshot(D,'integrated',[n for n in paths if (R/n).is_file()],experiment_id='ADR-0964-experiment-v1',arm_id='integrated',run_ids=['run-001'])
for n in paths:
 dst=C/'snapshot'/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(stage/n,dst)
 if not (R/n).exists():ac.register_file(C,n,upstream_state='absent')
ac.freeze(C);c=json.loads((C/'candidate.json').read_text());rev=c['revisions'][-1];b={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
for name,source in [('consumer.py','06_TOOLS/EXPERIMENTS/adr_0963/consumer.py'),('run_contracts.py','06_TOOLS/EXPERIMENTS/adr_0962/run_contracts.py'),('seal_release.py','06_TOOLS/EXPERIMENTS/adr_0962/seal_release.py')]:
 t=(R/source).read_text().replace('ADR-0963-scoped-final-qualification','ADR-0964-scoped-main-integration').replace('ADR-0962-scoped-clear-boundary','ADR-0964-scoped-main-integration').replace('scoped-multiturn-preview-0962','scoped-multiturn-preview-0964');(R/'06_TOOLS/EXPERIMENTS/adr_0964'/name).write_text(t)
m=json.loads((D/'실험/manifest.json').read_text());m.update(in_sample=False,decision_eligible=True);m['lineage']['hypothesis_delta']='Preserve late deterministic target-lookup receipt correction while retaining qualified command bytes; exact structural integration verification.';m['design']=copy.deepcopy(pm['design']);m['design'].pop('release_rebase',None);m['design']['hypothesis']='Latest exact target absence receipts can integrate without scoped-search/state/source regression.';m['design']['primary_metric']='All frozen structural/API tests and candidate/working/active service binding; parent five unseen command cases apply to byte-identical command path.';m['design']['success_criteria']='All frozen scope, API, source, memory, reference, output and latest gap receipt tests pass; actual data/service scoped read and complete417-file seal pass. Known-command path hashes identical to Accepted parent. No live semantic performance re-estimate. Active consumer failure rolls back.'
m['design']['arms'][0].update(derived_from=['ADR-0963-experiment-v1/qualified'],changes='Completed Accepted5/5 unseen command qualification; exact command-path hashes inherited');m['design']['arms'][1].update(id='integrated',changes='Only deterministic target absence receipt fix and derived engine pins')
runner=R/'06_TOOLS/EXPERIMENTS/adr_0964/run_contracts.py';m['design']['code_isolation']['candidates']=[{**b,'candidate_id':'integrated','arm_id':'integrated','experiment_id':m['experiment_id'],'run_ids':['run-001'],'runner_path':str(runner.relative_to(R)),'runner_sha256':sha(runner)}]
m['design']['test_bindings']={n:sha(R/n) for n in ['05_TESTS/CONTRACTS/test_multiturn_structured_scope.py','05_TESTS/CONTRACTS/test_scoped_multiturn_api.py','05_TESTS/CONTRACTS/test_unattempted_gap_finish.py','06_TOOLS/EXPERIMENTS/adr_0964/consumer.py']}
m['design']['inherited_qualification']={'path':str((PA/'result.json').relative_to(R)),'sha256':sha(PA/'result.json')};m['design'].pop('inherited_contract_result',None)
m['dataset']={**pm['dataset'],'name':'Exact deterministic integration contracts; parent unseen commands retained without rerun'};m['llm_policy']=copy.deepcopy(pm['llm_policy']);m['llm_policy']['llm_calls']=[];m['retrieval_accounting']=pm['retrieval_accounting'];m['runs'][0].update(purpose='audit',status='planned',selection_rule='Deterministic exact-code integration; no new model calls; critical source/ACL/hash/state regressions block promotion.',artifact_path=str((A/'result.json').relative_to(R)),sha256='PENDING');save(D/'실험/manifest.json',m)
save(A/'preview-auth.json',{'purpose':'integration_preview'});save(A/'preview-validation.json',{'structural_checks_passed':True})
print('Integrated candidate frozen; command path unchanged; latest receipt fix included')
