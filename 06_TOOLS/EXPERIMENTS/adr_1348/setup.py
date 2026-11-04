from common import *
import shutil
DES.mkdir(exist_ok=False)
PREV=ROOT/'04_EXPERIMENTS/ADR/ADR-1345-ontology-explicit-source-paired-use/artifacts'
BUILD=ROOT/'04_EXPERIMENTS/ADR/ADR-1343-qwen-ontology-build-and-use/artifacts'
FIX=ROOT/'04_EXPERIMENTS/ADR/ADR-1347-ontology-authoring-review-repair/artifacts'
for name in ('baseline.json','live-cases.json','source-scope.json','provider-policy.json','ontology-365-context.json','ontology-369-context.json','package-origin.json'):
 shutil.copyfile(PREV/'design'/name,DES/name)
for name in ('records.json','originals.json','originals-origin.json'):
 shutil.copyfile(BUILD/'design'/name,DES/name)
shutil.copytree(PREV/'transport',ART/'transport')
put(DES/'authorization.json',{'user_request':'수정할꺼 수정해봐 체크리스트 만들어서; 이전 Qwen 구축 및 사용 성능 확인 요청 유지',
 'public_document_ids':read(DES/'source-scope.json')['public'],'isolated_test_only':True,'main_and_production_publication_changes':0})
f=read(FIX/'design/candidate-repaired.json');assert all(sha(ROOT/n)==h for n,h in f['selected_files'].items())
criteria={'hypothesis':'Typed source-grounded authoring and exact history acquisition repair known construction and ontology ON failures.',
 'build_success':['One fixed archived charter judgment yields source-grounded STATEMENTs with exact handles/provenance and correct legal content','Existing normalize/analyze/project compiler passes; no hand correction or publication on incomplete review'],
 'use_success':['All four final answers are complete and correct against current originals','Approved corresponding package reaches each actual ON model input, source/ACL/wire errors0, duplicates add0 calls','At least10% aggregate latency/calls/tokens reduction among fully completed correct pairs'],
 'failure':['Build failure remains; existing approved365/369 use is separate from new construction','Source-only/CLARIFY/technical failures do not count as faster completed answers','Stop new sends after UNKNOWN; no adaptive reruns; same question each arm once; no causal/generalized claim from n2'],
 'order':['build once','ontology-365 baseline','ontology-365 ontology-on','ontology-369 ontology-on','ontology-369 baseline'],
 'limits':{'build_calls':9,'usage_per_cell':40,'usage_total':160,'heavy_workers':1,'rss_GiB':5,'start_available_GiB':5,'stop_available_GiB':3,'swap_growth_MiB':128},
 'fixed':'Exact completed1347 working528. Qwen3.8 FP8 reasoning none; same immutable public SQLite source and approved packages; default review ON; uncapped output. MAIN142 remains separate.',
 'grading':'Codex source comparison and mechanical exact audit; no judge model. Development/in-sample cases, no legal certification.'}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Completed source-correct authoring and paired use',success_criteria=criteria['build_success']+criteria['use_success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms'][0].update(changes='Ontology OFF on repaired1347 code',controls='Same528 model source review state defaults')
m['design']['arms'][1].update(changes='Ontology ON with exact existing approved365/369 package; separate authoring check',controls='Same528 model source review state defaults')
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','ontology-on')}
m['dataset'].update(name='Same archived judgment and paired explicit365/369 public questions',version='20261104-repair-r1',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'))
m['runs'][0].update(arm_ids=['baseline','ontology-on'],selection_rule='One build and four fixed paired cells, alternate order, stop UNKNOWN, no adaptive retry',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['retrieval_accounting']['stage_ledger'].update(mode='measured',not_applicable_reason=None)
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
can=ac.snapshot(ADR,'working1347',list(f['selected_files']),experiment_id=m['experiment_id'],arm_id='ontology-on',run_ids=['run-001'])
ac.freeze(can);assert not ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1]
put(DES/'candidate.json',{'code_root':str((can/'revisions'/rev['revision_id']/'snapshot').relative_to(ROOT)),
 'selected_files':f['selected_files'],'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}})
print('Frozen completed1347 working528; MAIN142 unchanged; build and four paired cells planned')
