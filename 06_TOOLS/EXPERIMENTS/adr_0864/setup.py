from pathlib import Path
import json,hashlib,subprocess,sys,shutil
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0864-nested-host-assembly-qualification';D=A/'artifacts/design';D.mkdir(exist_ok=True)
P=R/'04_EXPERIMENTS/ADR/ADR-0863-exact-host-assembly-qualification';C=R/'02_BACKEND/lawrag/research/candidates/adr_0864/qualified'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
criteria=read(P/'artifacts/design/criteria.json');criteria['hypothesis']='Distributing bounded nested anyOf intersections preserves exact constraints and restores only schema-implied values.';criteria['success']=['All parent/branch, nested anyOf, branch cap, and pattern/type/constant finite states pass','All385+existing consumer regressions and actual source service pass','Recorded fulltext outputs replay without schema relaxation','Same integrated code and pins selected by MAIN service'];criteria['evaluation']='Prospective finite contract census after0863; nested intersection product change. Legacy adaptive fixtures receive required ADOPT status and use the whole pinned candidate instead of an obsolete partial packager. Test runner now enters pytest only in __main__, so a multiprocessing spawn child cannot recursively rerun the suite. One heavy process only; actual runtime and full test completion required. No legal quality claim.'
criteria['resource_policy']={'max_parallel_heavy_workers':1,'rss_ceiling_gib':8,'address_space_ceiling_gib':9,'min_available_gib':2,'min_physical_disk_gib':10,'guard_path':'06_TOOLS/EXPERIMENTS/resource_guard.py','guard_sha256':sha(R/'06_TOOLS/EXPERIMENTS/resource_guard.py'),'baseline_interruption':'0857/0858 results incomplete; preserve charged and unknown calls, do not reset prior budgets'}
put(D/'criteria.json',criteria)
f=read(P/'artifacts/design/freeze.json');S=R/f['code_root'];cm=read(R/f['candidate']['manifest_path'])
baseline=read(P/'artifacts/design/baseline.json');assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==baseline['pointer_sha256']
put(D/'baseline.json',baseline);put(D/'working-before.json',{x['target_path']:sha(R/x['target_path']) for x in cm['files']});put(D/'data-binding.json',read(P/'artifacts/design/data-binding.json'))
cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','qualified','--experiment-id','ADR-0864-experiment-v1','--arm-id','qualified','--run-id','run-001']
for x in cm['files']:cmd+=['--source',x['target_path']]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
for x in cm['files']:shutil.copyfile(S/x['target_path'],C/'snapshot'/x['target_path'])
put(D/'parent-bytes.json',{x['target_path']:sha(S/x['target_path']) for x in cm['files']})
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['lineage']['hypothesis_delta']='Repair nested anyOf host reconstruction with bounded branch expansion; qualify exact bytes sequentially.';m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Finite software contract and consumer integrity with bounded resources',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['llm_policy']['llm_calls']=[];m['dataset'].update(name='host-assembly-finite-contract-census',version='20261018-serial-v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'))
for arm in m['design']['arms']:arm.update(changes='0863 exact intersection plus bounded nested anyOf distribution' if arm['id']=='qualified' else 'Completed0863 rejection record',controls=['same data/model/pins','no model calls','resource guard and single heavy worker'])
m['runs'][0].update(arm_ids=['qualified'],selection_rule=criteria['evaluation'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
why='Finite software contracts; no model judgment/retrieval quality comparison.';m['retrieval_accounting']['not_applicable_reason']=why;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=why;put(A/'실험/manifest.json',m)
print('Serial qualification frozen design, shared immutable data, small code-only snapshot')
