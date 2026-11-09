"""Freeze the ADR-1459 candidate (MAIN178 + 3 search fixes), the hybrid Oracle-vector environment and all
51 financial CM questions before any model call. Reference answers go only to the grading-only file."""
from common import *
import shutil,csv
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
P1459=ROOT/'04_EXPERIMENTS/ADR/ADR-1459-main178-oracle-vector-cm9-qwen/artifacts/design'
DES.mkdir(exist_ok=False)
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert ptr['generation']==178 and ptr['release_id']=='unread-labels-20261108-r1'
rel=read(ROOT/ptr['manifest_path']);files=rel['files'];assert len(files)==544
prior_candidate=read(P1459/'candidate-selected.json');S=ROOT/prior_candidate['code_root']
staged={n:sha(S/n) for n in files};assert staged==prior_candidate['candidate_files'],'ADR-1459 candidate snapshot changed'
changed=sorted(n for n in files if staged[n]!=files[n])
put(DES/'baseline.json',{'pointer':ptr,'release':rel,'candidate_source':{'adr':'ADR-1459','code_root':prior_candidate['code_root'],'pin':prior_candidate['pin']},'staged_changed_files':changed,
 'regression':read(P1459/'baseline.json')['regression']})
qpath=ROOT/'01_DATA/review/cm_core_e2e_v3.json';rpath=ROOT/'01_DATA/GOLDEN/registry-v3-execution-scope.json';apath=ROOT/'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json'
auth=read(apath);assert any(f['path']=='01_DATA/review/cm_core_e2e_v3.json' and f['sha256']==sha(qpath) for f in auth['files'])
questions=read(qpath)['cases'];ORDER=[q['id'] for q in questions];assert len(ORDER)==51
registry={c['id']:c for c in read(rpath)['cases'] if c['collection']=='cm'}
assert all(registry[i]['stage']=='ready' and 'local_execution_allowed' in registry[i]['tags'] and 'financial' in registry[i]['tags'] for i in ORDER)
prior={r['case_id']:r for r in csv.DictReader((ROOT/'04_EXPERIMENTS/ADR/ADR-1424-main161-cm51-financial-qwen/artifacts/CM51_결과.csv').open(encoding='utf-8-sig'))}
assert set(prior)==set(ORDER)
gold=read(P1459/'oracle-gold.json');granted=gold['granted_documents']
cases=[{'id':q['id'],'arms':['candidate'],'document_ids':granted,'steps':[{'number':1,'question':q['question'],'mode':'외규'}]} for q in questions]
assert all(c['steps'][0]['question']==registry[c['id']]['question'] for c in cases)
grades=[{'id':i,'reference_answer':registry[i]['reference_answer'],'as_of':registry[i]['as_of'],'facets':registry[i]['facets'],
 'main161':{k:prior[i][k] for k in ('grade','failure_type','required_acquired','required_total','reason')},
 'targets':[{k:t.get(k) for k in ('law','article','coordinate_key','coordinate_scope','role','evidence_role_v3','doc_id','source_text_sha256','node')} for t in registry[i]['targets']]} for i in ORDER]
criteria={'authorization':'지금 우리 다른 cm들도 돌려볼래? 전체 골든셋 기반 정답률 측정해봐',
 'scope':'Same candidate as ADR-1459 (MAIN178 + guided_answer/guided_navigation/connection_scope search fixes), same hybrid environment: candidate service.py in explicit-generation mode on the selected generation (dataset d4d1d8b4…, same bytes as local Oracle Gold DOC_*), isolated local SQLite runtime, GENOS_RAG_INITIAL_SEARCH=vector with candidates from Oracle Gold bge-m3 items (all 98 required articles of the 51 questions lie in the Gold vector documents) embedded by a local verified bge-m3 endpoint. All 51 financial CM questions once each, 외규 mode, scope = public grant ∩ financial team. Reference answers grading-only. No MAIN change.',
 'required':['Candidate code bytes unchanged during the run; every loaded semantic_runtime module from the candidate tree',
  'Primary: answer accuracy against the registered reference answer on the current stored original, graded PASS/PARTIAL/FAIL per question by direct comparison, with the same failure types as ADR-1424 (NOT_READ, WRONG_BASIS, MISREAD, INCOMPLETE, PROCESSING_ERROR, …); compared with ADR-1424 (MAIN161, 18/5/28)',
  'Secondary: registered required articles acquired and cited per question (law name + article on the current generation)',
  'Source spans/ACL/wire integrity, duplicate request adds 0 calls, budget respected'],
 'grading_rule':'PASS = the answer states the reference answer’s operative rule(s) from the right article(s) without a material error; a correct answer that also asks an optional follow-up still passes. PARTIAL = right article and part of the rule, or the right rule with a material omission/qualification, or the right conclusion withheld as a question while the rule is stated. FAIL = required article not read, wrong basis, misread, processing error or no answer. Same rule as ADR-1424/1458.',
 'limits':{'physical_total':500,'per_request':40,'per_physical_seconds':180,'reported_cost_usd':4,'time_box_minutes':150,'ram_floor_gib':3,'swap_free_floor_gib':1,'worker_swap_growth_mib':128,'global_swap_growth_mib':512,'workers':1},
 'stop':'UNKNOWN ends that request without retry; independent next question allowed. Three consecutive UNKNOWN cases, runner/resource failure, total budget or the 150-minute time box (checked before each next question) stop the batch. No other tests or model work in this session while the batch runs.',
 'quality_certified':False,'in_sample':True,'order':ORDER,
 'prior_observation':'ADR-1424 (MAIN161, SQLite keyword): PASS 18 / PARTIAL 5 / FAIL 28. ADR-1458 (MAIN177, 9 of them): 8 failed questions → PASS1 PARTIAL1 FAIL6. ADR-1459 (this candidate, same 9): PASS4 PARTIAL1 FAIL3 + control PASS. These 9 are in-sample for the candidate’s design; the other 42 were not used to design the fixes.'}
put(DES/'criteria.json',criteria);put(DES/'grading-only.json',grades);put(DES/'live-cases.json',cases)
put(DES/'question-source.json',{'path':str(qpath.relative_to(ROOT)),'sha256':sha(qpath),'registry_path':str(rpath.relative_to(ROOT)),'registry_sha256':sha(rpath),'question_policy':'Local experiments use the financial cm51; risk_cm105 not selected. Question strings authorized for the external experiment model by CM_EXPORT_AUTHORIZATION_20261024.'})
put(DES/'provider-policy.json',read(S/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'))
put(DES/'authorization.json',{'request':criteria['authorization'],'question_authorization_path':str(apath.relative_to(ROOT)),'question_authorization_sha256':sha(apath),'documents':granted,'scope':'Registered CM question strings only; reference answers and coordinates are never sent'})
for name in ('oracle-gold.json','embed-validate.json','embed-profile-files.json'):shutil.copyfile(P1459/name,DES/name)
dev=read(P1459/'deviation.json');dev.update(recorded_before_first_model_call=True,model_calls_so_far=0,inherited_from='ADR-1459 design/deviation.json',runner='06_TOOLS/EXPERIMENTS/adr_1461/live_hybrid.py')
put(DES/'deviation.json',dev)
transport=ART/'transport';shutil.copytree(ROOT/'04_EXPERIMENTS/ADR/ADR-1459-main178-oracle-vector-cm9-qwen/artifacts/transport',transport)
pins=read(transport/'transport-pins.json');assert all(sha(transport/n)==h for n,h in pins['files'].items())
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['scope'],primary_metric='Per-question PASS/PARTIAL/FAIL against the registered reference answer, compared with ADR-1424 (MAIN161)',success_criteria=criteria['required'],failure_criteria=[criteria['stop'],'Any source/ACL/wire mismatch or action substitution'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['retrieval_stage_plan']['stages_by_arm']={}
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':[],'changes':'Reference only: ADR-1424 MAIN161 SQLite keyword outcomes for the same 51 questions; not executed here','controls':'Same question strings and reference grading rule'},
 {'id':'candidate','role':'candidate','derived_from':['baseline'],'changes':'ADR-1459 candidate MAIN178+3, vector initial search with Oracle Gold bge-m3 items (hybrid)','controls':'Same default profile, same dataset version, independent requests'}]
m['dataset'].update(name='financial CM 51 (cm-field-core-e2e-v3)',version='cm-field-core-e2e-v3',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'),legal_version_checked=True,reference_version_checked=False)
m['runs'][0].update(arm_ids=['candidate'],selection_rule=criteria['stop'],artifact_path=str((ART/'review-input.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['in_sample']=True
can=ac.snapshot(ADR,'candidate',list(files),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
for n in files:
 if sha(can/'snapshot'/n)!=staged[n]:shutil.copyfile(S/n,can/'snapshot'/n)
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1];snapshot=can/'revisions'/rev['revision_id']/'snapshot'
assert all(sha(snapshot/n)==staged[n] for n in files)
desc={'code_root':str(snapshot.relative_to(ROOT)),'candidate_files':staged,'base_release_files':files,'changed_from_main178':changed,'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
put(DES/'candidate-selected.json',desc)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,production_paths_modified_before_decision=False,runtime_import_allowed=False,production_registry_registered=False,main_wiring_unchanged=True,
 candidates=[dict(desc['pin'],candidate_id='candidate',experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'],runner_path=str(Path(__file__).with_name('live_hybrid.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).with_name('live_hybrid.py')))])
ra=m['retrieval_accounting'];ra['not_applicable_reason']='No stage ledger; per-question vector candidates and acquired/presented article roots are in artifacts/source-wire-audit.json and review-input.json.'
if isinstance(ra.get('stage_ledger'),dict):ra['stage_ledger']['not_applicable_reason']=ra['not_applicable_reason']
put(ADR/'실험/manifest.json',m)
put(ART/'preparation-issues.json',[])
paths=[*Path(__file__).parent.glob('*.py'),*(DES/x for x in ('criteria.json','live-cases.json','authorization.json','provider-policy.json','candidate-selected.json','grading-only.json','oracle-gold.json','embed-validate.json','embed-profile-files.json','deviation.json'))]
put(DES/'freeze-live.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'selected_pointer':ptr,'source_manifest_sha256':rel['data_manifest_sha256'],'model_calls_before_freeze':0})
print('Frozen ADR-1459 candidate (',len(changed),'changed), 51 CM questions, budget 500/$4/150min; model0')
