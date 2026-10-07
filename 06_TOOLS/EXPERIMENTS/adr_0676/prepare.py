"""Reserve-owned successor; inherit exact reviewed files without touching production."""
from pathlib import Path
import json,hashlib,shutil,subprocess,copy
R=Path(__file__).resolve().parents[3];P=R/'04_EXPERIMENTS/ADR/ADR-0675-investigation-control-binding-closure';A=R/'04_EXPERIMENTS/ADR/ADR-0676-investigation-reinspection-repair';D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(p.read_text())
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
pm=read(P/'실험/manifest.json');m=read(A/'실험/manifest.json')
for k in ['design','dataset','llm_policy','runs','retrieval_accounting']:m[k]=copy.deepcopy(pm[k])
m['design'].pop('release_rebase',None)
m['design'].update(hypothesis='Reinspection can retain DEFER without acquisition; a changed corrective action replaces coupled basis/target fields; broad statutory questions preserve conditional sub-scope requirements',primary_metric='Five observed failures execute with supported answers and no native state/range/legacy regression; in-sample probe, never a MAIN qualification',success_criteria='All frozen contracts pass and all five candidate requests execute with exact quotations and independently complete answers; no production changes',failure_criteria='Any contract failure or incomplete candidate answer rejects this probe',criteria_frozen_before_run=True)
m['design']['code_isolation'].update(candidates=[],reason=None)
m['runs'][0].update(status='planned',sha256=None,artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)),selection_rule='Exactly IC11 through IC15, observed failures from completed ADR0675; one run each arm, no replacement, built-in repair only')
m['results']={'status':'not_started','by_arm':{}}
m['dataset'].update(name='Five observed failure cases, in-sample repair probe',version='20261007-reinspection-probe-v1',frozen_source=str((D/'dataset.json').relative_to(R)))
m['retrieval_accounting']['stage_ledger'].update(artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),sha256='PENDING')
for k in ['corpus_total','before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity']:m['retrieval_accounting'][k]=None
put(A/'실험/manifest.json',m)
dataset=read(P/'artifacts/design/dataset.json');ids={'IC11','IC12','IC13','IC14','IC15'};dataset['cases']=[c for c in dataset['cases'] if c['case_id'] in ids];dataset['regression_cases']=[];dataset['selection']='Observed cases IC11..IC15; in-sample only, no promotion/generalization';put(D/'dataset.json',dataset)
gold=read(P/'artifacts/design/gold.json');gold['cases']=[c for c in gold['cases'] if c['case_id'] in ids];put(D/'gold.json',gold)
shutil.copy2(P/'artifacts/design/rubric.json',D/'rubric.json')
cm=read(R/'02_BACKEND/lawrag/research/candidates/adr_0675/integrated/candidate.json');rows=cm['files'];present=[f['target_path'] for f in rows if (R/f['target_path']).is_file()]
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A.relative_to(R)),'--candidate-id','integrated','--experiment-id',m['experiment_id'],'--arm-id','integrated','--run-id','run-001']
for path in present:cmd+=['--source',path]
subprocess.run(cmd,cwd=R,check=True)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0676/integrated';S=C/'snapshot';revision={f['snapshot_path']:f for f in cm['revisions'][-1]['files']}
for f in rows:
 p=S/f['target_path'];p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(R/revision[f['snapshot_path']]['frozen_path'],p)
 if f['target_path'] not in present:
  subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str((C/'candidate.json').relative_to(R)),'--target',f['target_path'],'--upstream-state','absent'],cwd=R,check=True,stdout=subprocess.DEVNULL)
for name in ['run_case.py','grade.py','grade_ready.py','run_pairs.py','run_contracts.py','prepare_runtimes.py','audit_package.py','prepare_stage.py','summarize.py']:
 s=(R/'06_TOOLS/EXPERIMENTS/adr_0675'/name).read_text().replace('adr_0675','adr_0676').replace('ADR-0675-investigation-control-binding-closure','ADR-0676-investigation-reinspection-repair').replace('adr0675','adr0676')
 if name=='run_contracts.py':s=s.replace("files += ['test_investigation_control_adr0674.py']", "files += ['test_investigation_control_adr0674.py','test_investigation_reinspection_adr0676.py','test_law_navigation_patch_repair_adr0664.py','test_law_navigation_one_repair_adr0663.py']")
 (R/'06_TOOLS/EXPERIMENTS/adr_0676'/name).write_text(s)
put(D/'integration.json',{'parent':m['lineage']['parents'][0],'inherited_reviewed_integration':read(P/'artifacts/design/working-integration.json'),'planned_changes':['Separate saved inspection from acquisition when checking DEFER','Full control-mode correction maintains action/target/query/basis coupling','Do not narrow broad question to a single read parent; inspect applicable conditional requirements'], 'production_unchanged':True})
print('Inherited',len(rows),'reviewed files; five probe cases; production unchanged')
