from pathlib import Path
import json,hashlib,subprocess,itertools,shutil,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0829-comparison-main-qualification';D=A/'artifacts/design';D.mkdir(exist_ok=True)
P=R/'02_BACKEND/lawrag/research/candidates/adr_0828/connected';pc=json.loads((P/'candidate.json').read_text());old=P/'revisions/rev-001/snapshot';C=R/'02_BACKEND/lawrag/research/candidates/adr_0829/connected'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
cases=[]
for a,b,c,wrong in itertools.product(('CONFIRMED','PARTIAL','MISSING','CONFLICT'),('CONFIRMED','PARTIAL','MISSING','CONFLICT'),('MATCH','DIFFERENT','UNKNOWN'),(False,True)):
 cases.append({'case_id':'field-'+str(len(cases)+1).zfill(3),'family':'fields','internal':a,'external':b,'comparison':c,'wrong_side':wrong})
for n,side,prior in itertools.product((1,4,23,97),('internal','external'),(False,True)):
 cases.append({'case_id':'packet-'+str(len(cases)+1).zfill(3),'family':'packets','irrelevant':n,'side':side,'historical':prior})
for op,locator,anchor in itertools.product(('read_node','locate_provision','lookup_definition','follow_reference','search_structure','search_subtree','search_text'),('same','opposite','none'),('valid','missing')):
 cases.append({'case_id':'task-'+str(len(cases)+1).zfill(3),'family':'tasks','operation':op,'locator':locator,'anchor':anchor})
for invalid_side,fault,good_status,field in itertools.product(('internal','external'),('wrong_side','unread_quote','missing_prose','scope','comparison'),('CONFIRMED','PARTIAL'),('authority','denominator')):
 cases.append({'case_id':'partial-'+str(len(cases)+1).zfill(3),'family':'partial','invalid_side':invalid_side,'fault':fault,'good_status':good_status,'field':field})
for old_status,parent,owner,fingerprint,call_status in itertools.product(('RUNNING','FAILED'),(False,True),(False,True),(False,True),('PREPARED','COMPLETE','FAILED','absent')):
 cases.append({'case_id':'resume-'+str(len(cases)+1).zfill(3),'family':'resume','old_status':old_status,'parent':parent,'owner':owner,'fingerprint':fingerprint,'call_status':call_status})
for side,status,historical,reviewed,context_count in itertools.product(('internal','external'),('completed','partial','failed'),(False,True),(False,True),(0,7)):
 cases.append({'case_id':'publication-'+str(len(cases)+1).zfill(3),'family':'publication','side':side,'status':status,'historical':historical,'reviewed':reviewed,'context_count':context_count})
put(D/'cases.json',cases)
criteria={'hypothesis':'Unchanged completed ADR0828 rev001 satisfies the exhaustively declared mechanical field/provenance/task/packet contract space versus completed826; release rebase separately binds MAIN76; not legal accuracy.',
 'success':['all306 prospective cases pass','no new failures in214 existing regressions relative to baseline','all58 development API/source tests pass on exact frozen code','candidate13 actual service checks and baseline12 pass','each matrix under60s/2GiB; service under180s/12GiB; regression/API under600s/12GiB','no product code edits after freeze','known827read-only source replay retains6exact adopted spans without model calls or journal mutation'],
 'known_baseline_failures':['test_native_v8_source_ids_publication_repair_reentry_reuse with direct_note=True (six parameter combinations)'],
 'failures':['cross-side proof accepted','evidence/exception loss','unsatisfied field presented complete','hash or ACL failure bypass','budget reset'],
 'novelty':'Finite technical census declared now; no selection/subsampling/result-based fixture revisions. Development API tests are retained regressions, not holdout.',
 'model_calls':0,'quality_certified':False,'case_count':len(cases),'regression_files':['05_TESTS/CONTRACTS/test_source_span_norm.py','05_TESTS/CONTRACTS/test_navigation_delivery_recovery.py','05_TESTS/CONTRACTS/test_law_grouped_navigation.py','06_TOOLS/EXPERIMENTS/adr_0811/test_handoff_boundaries.py','06_TOOLS/EXPERIMENTS/adr_0811/test_comparison_boundaries.py','05_TESTS/CONTRACTS/test_successful_core_routes.py']}
assert len(cases)==306
put(D/'criteria.json',criteria)
for name in ('baseline.json','data-binding.json'):shutil.copy2(R/'04_EXPERIMENTS/ADR/ADR-0818-comparison-research-tasks/artifacts/design'/name,D/name)
base=json.loads((D/'baseline.json').read_text());prior=json.loads((R/'04_EXPERIMENTS/ADR/ADR-0826-comparison-resume-qualification/artifacts/design/verification-binding.json').read_text())
base['selected_release_manifest']=base['manifest']
base['manifest']={**base['manifest'],'code_root':prior['code_root'],'files':prior['serving_files'],'release_id':'technical-control-ADR0826-rev001'}
base['control_description']='Exact completed ADR0826 rev001, workflow1.4.1; actual selected MAIN76 stays separately recorded'
put(D/'baseline.json',base)
# Standard snapshot binds current upstream, then imports only the exact completed parent's files.
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','connected','--experiment-id','ADR-0829-experiment-v1','--arm-id','connected','--run-id','run-001']
for x in pc['files']:
 if (R/x['target_path']).exists():cmd+=['--source',x['target_path']]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
for x in pc['files']:
 n=x['target_path'];p=C/'snapshot'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old/n,p)
 if not (R/n).exists():subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',n,'--upstream-state','absent'],check=True,stdout=subprocess.DEVNULL)
sys.path.insert(0,str(R/'06_TOOLS/GENERATIONS/20260904-code-v19/COMMANDS'));import adr_candidate
adr_candidate.refresh(C)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True,stdout=subprocess.DEVNULL)
cm=json.loads((C/'candidate.json').read_text());rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
assert all(sha(code/x['target_path'])==sha(old/x['target_path']) for x in pc['files'])
put(D/'working-before.json',{x['target_path']:x['upstream_sha256'] for x in cm['files']})
put(D/'verification-binding.json',{'code_root':str(code.relative_to(R)),'serving_files':{x['target_path']:sha(code/x['target_path']) for x in cm['files']},'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']})
m=json.loads((A/'실험/manifest.json').read_text());m.update(in_sample=False,decision_eligible=True)
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design']['code_isolation']['reason']=None
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='finite software contract census pass count and no new regressions',success_criteria=criteria['success'],failure_criteria=criteria['failures'],criteria_frozen_before_run=True)
for arm in m['design']['arms']:arm['controls']=['same immutable source/profile/code binding','synthetic proposals only;no external network calls'];arm['changes']='Exact completed ADR0826 rev001 control' if arm['id']=='baseline' else 'Exact completed0828 rev001342 serving files;unchanged'
m['runs'][0]['artifact_path']=str((A/'artifacts/run-001/result.json').relative_to(R))
m['runs'][0].update(selection_rule='All306 enumerated software states,58 retained development contracts,214 shared regressions and actual service consumers',status='planned')
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['dataset'].update(name='comparison-task-finite-contract-census',version='20261016-v1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'),legal_version_checked=False,reference_version_checked=False)
# This census consumes supplied immutable originals, no search/retrieval quality is measured.
reason='New census is validator and fixed-original projection only; no source retrieval executes in these306cases. Actual source/API checks are separately retained regression/connection checks, not retrieval effectiveness evaluation.'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(A/'실험/manifest.json',m)
print('Prepared306 cases and identical342 file candidate')
