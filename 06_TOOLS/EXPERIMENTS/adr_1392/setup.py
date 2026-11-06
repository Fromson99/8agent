from common import *
import ast
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac

DES.mkdir(exist_ok=False)
origin=ROOT/'04_EXPERIMENTS/ADR/ADR-1388-bound-chat-review-repair/artifacts'
verified=read(origin/'design/candidate-repaired.json')
tested=ROOT/verified['code_root']
integration=read(origin/'working-integration.json')
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
assert pointer['generation']==145
release=read(ROOT/pointer['manifest_path'])
assert sha(ROOT/pointer['manifest_path'])==pointer['release_manifest_sha256']
files=release['files'];base=ROOT/release['code_root']
assert len(files)==528 and all(sha(base/n)==h for n,h in files.items())
assert all(sha(tested/n)==h for n,h in verified['selected_files'].items())
gold=ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
binding=read(gold/'binding.json');assert binding['engine_root']==release['code_root'] and binding['engine_files']==files
baseline={'pointer':pointer,'release':release,'gold_binding':binding,'gold_files':{str(p.relative_to(ROOT)):sha(p) for p in gold.iterdir() if p.is_file() and p.suffix in ('.json','.py','.yaml')}}
put(DES/'baseline.json',baseline)
criteria={'authorization':'이거 메인에 반영해봐','scope':'Apply the reviewed chat recovery feature only to selected local MAIN and align Gold engine binding. No remote deployment, email, data generation change or paid model calls.',
'required':['Verify all selected hashes; import three exact backend modules and only the reviewed UI function; rebuild native SQL catalogue and engine pins. Assert exact file delta and preservation of existing 639 executable plans.','Exercise the staged candidate and the prepared release through the failed-review API, verify scope and duplicate requests, test displayed command.','After activation verify fresh default service health and literal chat command, Gold connector import, exact release pointer/data/manifest and rollback record.'],
'rollback':pointer['manifest_path'],'quality_certified':False,'parent_verification':{'technical':str(origin.relative_to(ROOT)),'qwen':'ADR-1390-experiment-v1/repaired'}}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['scope'],primary_metric='Correct release hashes, tested API, and actual native service / Gold loader selection',success_criteria=criteria['required'],failure_criteria=['Block on unexpected code, failed required tests or stale active pointer. Roll back our own activation if selected probes fail.'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
for a in m['design']['arms']:a.update(changes='Unmodified current MAIN145' if a['id']=='baseline' else 'Rebased chat review feature only',controls='Same data generation, Gold mapping, runtime policy and user access checks.')
m['dataset'].update(name='Saved review feature contract plus local release verification',version='1392-r1',frozen_source=str((DES/'criteria.json').relative_to(ROOT)),sha256=sha(DES/'criteria.json'),legal_version_checked=True,reference_version_checked=True)
m['runs'][0].update(arm_ids=['integrated'],selection_rule='Staged and prepared service contracts followed by actual local MAIN and Gold entry checks',artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[]
for ob in (m['retrieval_accounting'],m['retrieval_accounting']['stage_ledger']):ob['not_applicable_reason']='Local release cutover verification, no new comparison of retrieval or external models'
put(ADR/'실험/manifest.json',m)
can=ac.snapshot(ADR,'integrated',list(files),experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001'])
C=can/'snapshot'
for n,h in files.items():
    if sha(C/n)!=h:shutil.copyfile(base/n,C/n)
assert all(sha(C/n)==h for n,h in files.items())

products=integration['product_files']
backend=[n for n in products if '/legal_agent/' in n]
assert len(backend)==3
for n in backend:
    assert files[n]==integration['previous_hashes'][n] and sha(tested/n)==integration['changed_hashes'][n]
    shutil.copyfile(tested/n,C/n)
wf='08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'
def function(source):
    return ast.get_source_segment(source,next(n for n in ast.parse(source).body if getattr(n,'name',None)=='_review_explanation_text'))
old=(origin/'working-before'/wf).read_text()
after=(tested/wf).read_text()
oldfn,newfn=function(old),function(after)
assert old.count(oldfn)==after.count(newfn)==1 and old.replace(oldfn,newfn)==after
active=(base/wf).read_text()
assert function(active)==oldfn and active.count(oldfn)==1
(C/wf).write_text(active.replace(oldfn,newfn))
assert (C/wf).read_text().replace(newfn,oldfn)==active
put(DES/'intent.json',{'products':backend+[wf],'changed_function':'_review_explanation_text','baseline_workflow':sha(base/wf),'tested_workflow':sha(tested/wf),'staged_workflow':sha(C/wf),'native':'02_BACKEND/semantic_runtime/oracle_query_plans.py','verified_source':verified['pin']})
put(DES/'candidate-path.json',{'candidate':str(can.relative_to(ROOT)),'files':list(files)})
