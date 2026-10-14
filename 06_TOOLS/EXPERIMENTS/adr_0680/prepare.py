"""Reserve-owned successor, preserve rejected parent and isolate every edit."""
from pathlib import Path
import json,hashlib,shutil,subprocess,copy
R=Path(__file__).resolve().parents[3];P=R/'04_EXPERIMENTS/ADR/ADR-0679-investigation-completion-qualification';A=R/'04_EXPERIMENTS/ADR/ADR-0680-investigation-main-consumer-integration';D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(p.read_text())
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert not (D/'design.json').exists()
pm=read(P/'실험/manifest.json');assert pm['reservation']['status']=='completed'
m=read(A/'실험/manifest.json');plan=read(P/'artifacts/design/design.json')
plan.update(status='CRITERIA_FROZEN_BEFORE_IMPLEMENTATION',scope='Inherit completed ADR0679 judgment code; three-way integrate latest working JSON/SSE consumers; native chat uses the shared typed completion status; preserve working changes and audit exact final package.',hypothesis='Sharing workflow completion status in the latest native chat adapter preserves partial/incomplete/unavailable outcomes across JSON and SSE while retaining the verified investigation, citation, access and budget contracts.')
plan['acceptance']={'all_applicable_contracts_pass':True,'critical_integrity_failures':0,'all_16_primary_and_12_regression_attempted':True,'minimum_primary_supported_responses':13,'minimum_regression_supported_responses':9,'semantic_correctness_absolute_gate':False,'no_improvement_claim_without_paired_measurement':True,'primary_unseen_article_groups':True,'identical_verified_code_for_main':True}
plan['evaluation_selection']='Freeze 16 new public article-root questions, two each actor/timing/classification/structure/formula/authority/definition/scope; exclude previous ADR0674..0679 golden and actually presented roots. Freeze 12 observed regressions including original failures and new NG11/NG13 defects; no primary outputs before code and all source/rubric/runner files freeze.'
plan['prospective_followup']='Any changed candidate after real outputs requires a new ADR. Qualified identical code may integrate into verified current MAIN using prior explicit user authorization.'
put(D/'design.json',plan);put(D/'baseline-binding.json',read(P/'artifacts/design/baseline-binding.json'))
for key in ('design','dataset','llm_policy','runs','retrieval_accounting'):m[key]=copy.deepcopy(pm[key])
m['design'].pop('release_rebase',None);m['design']['code_isolation'].update(candidates=[])
m['design'].update(hypothesis=plan['hypothesis'],primary_metric='Supported primary response completion and zero critical integrity failures; semantics separately',success_criteria='All required contracts pass, all 16 unseen primary and 12 observed regression requests attempted once, at least 13/16 primary and 9/12 regression supported responses, zero critical integrity failures, identical qualified serving code.',failure_criteria='Any required contract failure or source/access/hash/state/publication integrity defect, or unmet response threshold rejects; semantic detail errors recorded separately.',criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'integrated','role':'candidate','derived_from':['ADR-0679-experiment-v1/integrated'],'changes':plan['scope'],'controls':'Same active generation/public145/model policy; new primary groups, observed regressions separate; parent results are lineage only.'}]
m['lineage']['hypothesis_delta']=plan['hypothesis'];m['in_sample']=False;m['decision_eligible']=True
m['runs'][0].update(status='planned',sha256=None,artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)),purpose='holdout',selection_rule=plan['evaluation_selection'])
m['results']={'status':'not_started','by_arm':{}}
m['dataset'].update(name='16 unseen public article groups plus 12 observed regressions',version='20261007-completion-qualification-v1',frozen_source=str((D/'dataset.json').relative_to(R)),sha256=None)
for k in ('corpus_total','before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity'):m['retrieval_accounting'][k]=None
m['retrieval_accounting']['stage_ledger'].update(artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json.gz').relative_to(R)),sha256='PENDING')
put(A/'실험/manifest.json',m)
cm=read(R/'02_BACKEND/lawrag/research/candidates/adr_0679/integrated/candidate.json');present=[f['target_path'] for f in cm['files'] if (R/f['target_path']).is_file()]
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A.relative_to(R)),'--candidate-id','integrated','--experiment-id',m['experiment_id'],'--arm-id','integrated','--run-id','run-001']
for path in present:cmd+=['--source',path]
subprocess.run(cmd,cwd=R,check=True)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0680/integrated';S=C/'snapshot';revision={f['snapshot_path']:f for f in cm['revisions'][-1]['files']}
base=read(R/read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')['manifest_path'])
merge=[]
for f in cm['files']:
 target=f['target_path'];p=S/target;p.parent.mkdir(parents=True,exist_ok=True)
 parent=R/revision[f['snapshot_path']]['frozen_path'];working=R/target
 bh=base['files'].get(target);ph=sha(parent);wh=sha(working) if working.is_file() else None
 pin=target=='00_SYSTEM/PIPELINE.json' or target.startswith('02_BACKEND/ENGINES/')
 # Non-serving inherited tests and audit client use parent; pins are rebuilt later.
 if bh is not None and wh!=bh and not pin:
  assert ph in (bh,wh), 'Manual three-way conflict: '+target
  chosen=working
 else:chosen=parent
 shutil.copy2(chosen,p)
 merge.append({'path':target,'active':bh,'parent':ph,'working':wh,'selected':sha(p),'strategy':'working' if chosen==working else 'parent'})
 if target not in present:
  subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str((C/'candidate.json').relative_to(R)),'--target',target,'--upstream-state','absent'],cwd=R,check=True,stdout=subprocess.DEVNULL)
assert {x['path'] for x in merge if x['strategy']=='working'}=={'main.py','08_DEPLOYMENT/GENOS/stream_app.py','02_BACKEND/semantic_runtime/chat_adapter.py'}
put(D/'three-way-merge.json',merge)
put(D/'inheritance.json',{'parent_manifest_sha256':sha(P/'실험/manifest.json'),'parent_candidate_sha256':sha(R/'02_BACKEND/lawrag/research/candidates/adr_0679/integrated/candidate.json'),'parent_revision':cm['revisions'][-1]['revision_id'],'inherited_serving_files':len(cm['files']),'active_pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'working_product_unchanged':True,'working_changes_preserved':True,'merge_receipt_sha256':sha(D/'three-way-merge.json')})
print('Inherited',len(cm['files']),'files; criteria frozen, product MAIN unchanged')
