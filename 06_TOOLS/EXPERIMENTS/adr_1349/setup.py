from common import *
import shutil
DES.mkdir(exist_ok=False)
P=ROOT/'04_EXPERIMENTS/ADR/ADR-1347-ontology-authoring-review-repair/artifacts'
f=read(P/'design/candidate-repaired.json');before={n:sha(ROOT/n) for n in f['selected_files']};assert before==f['selected_files']
put(DES/'working-before.json',before);put(DES/'baseline.json',read(P/'design/baseline.json'))
criteria={'hypothesis':'Existing shared GENOS grammar adapter prevents uniqueItems provider refusal while original schema still rejects duplicates.',
 'success':['Actual authoring wire omits unsupported uniqueItems at schema locations only','Original proposal schema and local duplicate rejection remain unchanged; one repair and no unknown replay','Provider receives one new frozen build after contracts pass; all outcomes retained, no automatic legal approval'],
 'failure':['Do not erase local validation or semantic branches','No retries after UNKNOWN; no adaptive repeated live build','1348 frozen code and working tree remain unchanged until1348 finishes'],
 'limits':{'new_build_calls':9,'heavy_workers':1,'rss_GiB':5,'available_start_GiB':5,'available_stop_GiB':3,'swap_growth_MiB':128},
 'build':'Same archived charter judgment and originals as1348; exact full proposal/apply/compile, one repair per product phase; no manual content fixes.'}
put(DES/'criteria.json',criteria);cases=[{'id':'wire-grammar','scope':'Provider compatibility and original validation'},{'id':'authoring-live','scope':'One frozen real Qwen build after checks'}];put(DES/'cases.json',cases)
m=read(ADR/'실험/manifest.json');m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Compatible wire with unchanged server validation and actual build',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')});m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design']['arms'][0].update(changes='Completed1347 authoring transport; known1348 refusal',controls='No repeated original failed request')
m['design']['arms'][1].update(changes='Use existing model_contract.structured_request; preserve canonical validation',controls='Same528 except authoring_model and engine pins; no MAIN change')
m['dataset'].update(name='Authoring grammar contract and exact archived charter judgment',version='20261104-r1',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'))
m['runs'][0].update(arm_ids=['repaired'],selection_rule='Synthetic contract checks then one frozen Qwen build; no adaptive repeat',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
for v in (m['retrieval_accounting'],m['retrieval_accounting']['stage_ledger']):v['not_applicable_reason']='No retrieval candidate change: exact archived authoring record with fixed originals, no answer retrieval'
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
can=ac.snapshot(ADR,'repaired',list(before),experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'])
put(DES/'candidate-path.json',{'candidate':str(can.relative_to(ROOT)),'files':list(before),'product_files':['02_BACKEND/semantic_runtime/ontology_work/authoring_model.py']})
LIVE=ROOT/'04_EXPERIMENTS/ADR/ADR-1348-ontology-repair-qwen-build-use/artifacts'
for name in ('source-scope.json','records.json','originals.json','originals-origin.json','authorization.json','provider-policy.json'):
 shutil.copyfile(LIVE/'design'/name,DES/name)
shutil.copytree(LIVE/'transport',ART/'transport')
print(can/'snapshot')
