"""One predeclared identical-code rerun after upstream 429, no tuning."""
from pathlib import Path
import hashlib,json,subprocess,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0708-grounded-title-body-retest';D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
P=R/'04_EXPERIMENTS/ADR/ADR-0707-grounded-law-title-entry';F=json.loads((P/'artifacts/design/freeze.json').read_text());parent=R/F['codes']['title-entry']
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');case=next(c for c in read(P/'artifacts/design/dataset.json')['cases'] if c['case_id']=='body-content-001')
criteria={'scope':'Retry exactly one public body-content request with unchanged ADR0707 title-entry code/profile/data/model. No additional retries after this request in this ADR.',
 'success':['First entry produces search choice; FULLTEXT may execute without preceding structure query','Measure all physical attempts including failed provider attempts, exact tokens when available, source acquisition/presentation and final API time','No authority/scope/citation regression; preserve failure if upstream remains unavailable'],
 'limits':{'requests':1,'max_attempts':40,'wall_seconds':1800,'output_tokens':6400},
 'controls':'Identical parent product code bytes, same public65 corpus and fixed Qwen/Parasail; fresh process/runtime. No speed comparison to prior failed request; in-sample probe, no MAIN promotion.'}
put(D/'criteria.json',criteria);put(D/'dataset.json',{'cases':[case],'order':[['body-retest',case['case_id']]],'product_gold':False,'selection':'The only parent candidate question blocked before interpretation by two upstream429s; frozen retry1.'})
shutil.copyfile(P/'artifacts/design/baseline.json',D/'baseline.json')
m['design']['arms']=[a for a in m['design']['arms'] if a['id']=='body-retest'];m['design']['arms'][0].update(derived_from=['ADR-0707-experiment-v1/title-entry'],changes='No product changes; identical parent candidate execution',controls=criteria['controls'])
m['lineage']['hypothesis_delta']=criteria['scope'];m['design'].update(hypothesis='With upstream available, the existing optional search selection can start body search without extra routing calls',primary_metric='First search mode and final API completion with physical call ledger',success_criteria=criteria['success'],failure_criteria='Record HTTP failure or incorrect first search; no tuning or rerun',criteria_frozen_before_run=True,repeats=1)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
m['design']['retrieval_stage_plan']['stages_by_arm']={'body-retest':[{'stage_id':'catalogue','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'filter','parent_stage_ids':['catalogue']},{'stage_id':'presented','kind':'present','parent_stage_ids':['acquired']}]}
m['runs'][0].update(arm_ids=['body-retest'],selection_rule=criteria['scope'],artifact_path=str((A/'artifacts/run-001/summary.json').relative_to(R)))
m['dataset'].update(name='Public body-content identical-code retry',version='v1',frozen_source=str((D/'dataset.json').relative_to(R)),sha256=sha(D/'dataset.json'))
m['llm_policy']['llm_calls']=[x for x in m['llm_policy']['llm_calls'] if x['class']=='product']
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Identical retrieval code; measure new actual request separately')
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json.gz').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','body-retest','--experiment-id',m['experiment_id'],'--arm-id','body-retest','--run-id','run-001']
release=read(D/'baseline.json')['release']
for name in sorted(set(release['files'])|{'02_BACKEND/lawrag/research/experiment_client.py'}):cmd+=['--source',name]
subprocess.run(cmd,cwd=R,check=True)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0708/body-retest';S=C/'snapshot'
for p in parent.rglob('*'):
 if p.is_file() and '__pycache__' not in p.parts:
  q=S/p.relative_to(parent);q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q)
for name in ('request_entry.py','law_title_hints.py'):
 subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target','02_BACKEND/semantic_runtime/legal_agent/'+name,'--upstream-state','absent'],cwd=R,check=True)
runner=R/'06_TOOLS/EXPERIMENTS/adr_0708/run.py';source=(R/'06_TOOLS/EXPERIMENTS/adr_0707/run.py').read_text().replace('ADR-0707-grounded-law-title-entry','ADR-0708-grounded-title-body-retest').replace('adr0707','adr0708').replace("choices=['baseline','title-entry']","choices=['body-retest']")
runner.write_text(source)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],cwd=R,check=True)
cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
for p in code.rglob('*'):
 if p.is_file():assert sha(p)==sha(parent/p.relative_to(code)),str(p)
binding={'candidate_id':'body-retest','arm_id':'body-retest','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str(runner.relative_to(R)),'runner_sha256':sha(runner)}
m['design']['code_isolation']['candidates']=[binding];put(A/'실험/manifest.json',m)
paths=list(D.glob('*.json'))+[runner,Path(__file__),C/'candidate.json',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json']+[p for p in code.rglob('*') if p.is_file()]
put(D/'freeze.json',{'codes':{'body-retest':str(code.relative_to(R))},'source_generation':F['source_generation'],'candidate':binding,'parent_exact_product_code':str(parent.relative_to(R)),'all_product_files_identical':True,'files':{str(p.relative_to(R)):sha(p) for p in paths}})
print('FROZEN: one identical-code request, no model calls yet')
