from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
P=ROOT/'04_EXPERIMENTS/ADR/ADR-1354-ontology-final-repair-qwen-repeat/artifacts'
DES.mkdir(exist_ok=False)
f=read(P/'design/candidate.json')
files=list(f['selected_files'])
before={n:sha(ROOT/n) for n in files}
put(DES/'working-before.json',before)
put(DES/'candidate-parent.json',f)
for n in ('baseline','source-scope','originals','originals-origin','records','provider-policy'):
    put(DES/(n+'.json'),read(P/'design'/(n+'.json')))
shutil.copytree(P/'transport',ART/'transport')
products=['02_BACKEND/semantic_runtime/ontology_work/'+n for n in ('wiki_workspace.py','domain_workflow.py','wiki_projection.py')]
assert all(before[n]==f['selected_files'][n] for n in products)
criteria={'hypothesis':'Workspace proposal and projection review can correct known failures with a durable maximum of four repairs; exact literal choices and per-field errors keep the resulting knowledge attributable.',
 'success':['First plus at most four repairs per workspace stage, stop on pass, no new call after unknown, deadline, stale data or exhausted retries. Historical jobs keep their original limit.',
 'Actual charter draft can be reopened and compiled for the original purpose. Check source grounding of 433(1) and both distinct 434 thresholds and denominators; no extra administrative statements or legal auto-approval.'],
 'failure':['Rejected proposals remain stored; no new legal approval, publication, truncated statement set, or validator bypass. Count compile and content completeness separately.'],
 'scope':'One public charter build, no 365 usage cells. Parent ADR1354 failed at exact node text. Fixed original records, all selected. MAIN separate.',
 'limits':{'attempts_per_stage':5,'physical_client_ceiling_with_one_confirmed_429_switch':21,'parallel_workers':1,'model':'qwen/qwen3.8-27b','reasoning':'none','provider_policy':'Parasail FP8; known 429 one switch','stop_unknown':True}}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json')
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Reopenable, source-grounded charter bundle accepted by compiler',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms'][0].update(changes='Completed1354/repaired exact workspace and failed graph',controls='Reference only')
m['design']['arms'][1].update(changes='Four workspace repairs, bounded exact statement choice and specific validation feedback',controls='Same public originals, archived judgment, all selected statements, model and provider policy')
m['dataset'].update(name='Actual archived charter judgment and legal source snapshot',version='1354-frozen',frozen_source=str((DES/'records.json').relative_to(ROOT)),sha256=sha(DES/'records.json'),legal_version_checked=True,reference_version_checked=True)
m['runs'][0].update(arm_ids=['repaired'],selection_rule='Fresh build once. Validation may request up to four additional proposals per stage. Stop on unknown.',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=m['llm_policy']['llm_calls'][:1]
for x in (m['retrieval_accounting'],m['retrieval_accounting']['stage_ledger']):x['not_applicable_reason']='Fixed original authoring input; no answer/retrieval search experiment.'
put(ADR/'실험/manifest.json',m)
can=ac.snapshot(ADR,'repaired',files,experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'])
for n in files:
    if sha(can/'snapshot'/n)!=f['selected_files'][n]:
        shutil.copyfile(ROOT/f['code_root']/n,can/'snapshot'/n)
assert all(sha(can/'snapshot'/n)==f['selected_files'][n] for n in files)
put(DES/'candidate-path.json',{'candidate':str(can.relative_to(ROOT)),'files':files,'product_files':products})
print(can/'snapshot')
