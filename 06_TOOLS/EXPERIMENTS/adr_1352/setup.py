from common import *
import shutil
DES.mkdir(exist_ok=False)
P=ROOT/'04_EXPERIMENTS/ADR/ADR-1350-ontology-proposal-record-view/artifacts'
f=read(P/'design/candidate-repaired.json');before={n:sha(ROOT/n) for n in f['selected_files']};assert before==f['selected_files']
put(DES/'working-before.json',before);put(DES/'baseline.json',read(P/'design/baseline.json'))
criteria={'hypothesis':'Model-owned finite content selection prevents fabricated administrative statements; one original review shared by all acquisition targets and exact purpose-claim joins remove duplicate linkage errors without changing legal dispositions.',
 'success':['Model selects CONTENT/CONTROL/UNCERTAIN for every literal raw segment and offered original; exact selected content only is expanded to statements, no free metadata assertions'
 ,'One model-owned review per unique original is shared across targets; covered-purpose claims join explicit basis and issue only; unchanged canonical validators reject unsupported decisions','Full immutable raw revision/work hash remains separately bound and rechecked before/after generation','Legacy typed edit and canonical apply/compiler validators remain; max32 compile unchanged, no truncation or automatic publication','One fixed Qwen build and two independent365 ON requests after frozen technical checks; all outcomes retained; stop remaining cells on UNKNOWN'],
 'failure':['No content/key filtering inside user payload, no invented or corrected legal assertions','No model replay after UNKNOWN and no adaptive repeated build','No MAIN, source DB or publication changes'],
 'limits':{'new_build_calls':9,'365_cells':2,'per_cell_calls':40,'heavy_workers':1,'rss_GiB':5,'available_start_GiB':5,'available_stop_GiB':3,'swap_growth_MiB':128},
 'build':'Same fixed archived charter judgment and originals; existing proposal/apply/normalize/analyze/compile path once; limit checks remain unchanged.'}
put(DES/'criteria.json',criteria);cases=[{'id':'authoring-content','scope':'Finite original content selection and one fixed build'},{'id':'scope-review-365','scope':'Original review and purpose claim joins; two independent live365 ON requests'}];put(DES/'cases.json',cases)
m=read(ADR/'실험/manifest.json');m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Compatible wire with unchanged server validation and actual build',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')});m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design']['arms'][0].update(changes='Completed1350 with64 statements including58 administrative items;1348 failed365 ON final reviews',controls='No repeated original failed request')
m['design']['arms'][1].update(changes='Finite literal material selection and unique original review projection; purpose claim join; canonical checks retained',controls='Same528 except proposal/review projection and pins; same public data/Qwen/policies; no MAIN change')
m['dataset'].update(name='Authoring input projection contract and exact archived charter judgment',version='20261104-r1',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'))
m['runs'][0].update(arm_ids=['repaired'],selection_rule='Synthetic contract checks then one frozen Qwen build; no adaptive repeat',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
for v in (m['retrieval_accounting'],m['retrieval_accounting']['stage_ledger']):v['not_applicable_reason']='No retrieval candidate change: exact archived authoring record with fixed originals, no answer retrieval'
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
can=ac.snapshot(ADR,'repaired',list(before),experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'])
put(DES/'candidate-path.json',{'candidate':str(can.relative_to(ROOT)),'files':list(before),'product_files':['02_BACKEND/semantic_runtime/ontology_work/wiki_workspace.py','02_BACKEND/semantic_runtime/ontology_work/wiki_contracts.py','02_BACKEND/semantic_runtime/legal_agent/need_continuity.py','02_BACKEND/semantic_runtime/legal_agent/judgment_changes.py','02_BACKEND/semantic_runtime/legal_agent/completion_execution.py']})
LIVE=ROOT/'04_EXPERIMENTS/ADR/ADR-1348-ontology-repair-qwen-build-use/artifacts'
for name in ('source-scope.json','records.json','originals.json','originals-origin.json','authorization.json','provider-policy.json'):
 shutil.copyfile(LIVE/'design'/name,DES/name)
shutil.copytree(LIVE/'transport',ART/'transport')
print(can/'snapshot')
