"""Freeze the dual initial-search candidate (MAIN181 + vector and body-search lists shown separately), the same
SQLite-originals + Oracle-vector environment as ADR-1464 and all 51 financial CM questions before any model call.
Reference answers go only to the grading-only file."""
from common import *
import shutil,csv
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
P1459=ROOT/'04_EXPERIMENTS/ADR/ADR-1464-main179-definition-priority-cm51-qwen-r2/artifacts/design'
STAGE=ROOT/'09_ARTIFACTS/AUDITS/20261109-rerank-dual/release'
DES.mkdir(exist_ok=False)
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert ptr['generation']==181 and ptr['release_id']=='definition-priority-20261109-r1'
rel=read(ROOT/ptr['manifest_path']);files=rel['files'];assert len(files)==545
S=STAGE/'rerank-dual'
staged={n:sha(S/n) for n in files}
changed=sorted(n for n in files if staged[n]!=files[n])
reg=read(STAGE/'regression-compare.json');assert reg['status']=='PASSED' and not reg['new_failures']
put(DES/'baseline.json',{'pointer':ptr,'release':rel,'candidate_source':{'stage':str(S.relative_to(ROOT)),'main_release':read(STAGE/'main-release.json')},'staged_changed_files':changed,
 'regression':{'path':str((STAGE/'regression-compare.json').relative_to(ROOT)),'sha256':sha(STAGE/'regression-compare.json'),'new_failures':0,'fixed':len(reg['fixed'])},
 'oracle_scale_guard':str(Path('09_ARTIFACTS/AUDITS/20261109-rerank-dual/scale-guard-dual'))})
qpath=ROOT/'01_DATA/review/cm_core_e2e_v3.json';rpath=ROOT/'01_DATA/GOLDEN/registry-v3-execution-scope.json';apath=ROOT/'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json'
auth=read(apath);assert any(f['path']=='01_DATA/review/cm_core_e2e_v3.json' and f['sha256']==sha(qpath) for f in auth['files'])
questions=read(qpath)['cases'];ORDER=[q['id'] for q in questions];assert len(ORDER)==51
registry={c['id']:c for c in read(rpath)['cases'] if c['collection']=='cm'}
assert all(registry[i]['stage']=='ready' and 'local_execution_allowed' in registry[i]['tags'] and 'financial' in registry[i]['tags'] for i in ORDER)
prior={r['case_id']:r for r in csv.DictReader((ROOT/'04_EXPERIMENTS/ADR/ADR-1424-main161-cm51-financial-qwen/artifacts/CM51_결과.csv').open(encoding='utf-8-sig'))}
assert set(prior)==set(ORDER)
prior1461={r['case_id']:r for r in csv.DictReader((ROOT/'04_EXPERIMENTS/ADR/ADR-1464-main179-definition-priority-cm51-qwen-r2/artifacts/CM51_결과.csv').open(encoding='utf-8-sig'))}
assert set(prior1461)==set(ORDER)
prior1465={r['case_id']:r for r in csv.DictReader((ROOT/'04_EXPERIMENTS/ADR/ADR-1465-main181-hybrid-search-cm51-qwen/artifacts/CM51_결과.csv').open(encoding='utf-8-sig'))}
assert set(prior1465)==set(ORDER)
gold=read(P1459/'oracle-gold.json');granted=gold['granted_documents']
cases=[{'id':q['id'],'arms':['candidate'],'document_ids':granted,'steps':[{'number':1,'question':q['question'],'mode':'외규'}]} for q in questions]
assert all(c['steps'][0]['question']==registry[c['id']]['question'] for c in cases)
grades=[{'id':i,'reference_answer':registry[i]['reference_answer'],'as_of':registry[i]['as_of'],'facets':registry[i]['facets'],
 'main161':{k:prior[i][k] for k in ('grade','failure_type','required_acquired','required_total','reason')},
 'adr1464':{k:prior1461[i][k] for k in ('grade','failure_type','required_acquired','required_cited','required_total','reason')},
 'adr1465':{k:prior1465[i][k] for k in ('grade','failure_type','required_acquired','required_cited','required_total','reason')},
 'targets':[{k:t.get(k) for k in ('law','article','coordinate_key','coordinate_scope','role','evidence_role_v3','doc_id','source_text_sha256','node')} for t in registry[i]['targets']]} for i in ORDER]
criteria={'authorization':'우리 두개 실험 해보자 / 1. 하이브리드 llm리랭킹 해서 올리기 / 2.벡터 그리고 full text 각각 보여주기 조합하지 말고 둘다 진행후 실험 각각 — 2번',
 'scope':"Candidate = MAIN181 with the initial search giving two separate lists that are not combined by any score: the vector top-100 articles in vector order and the BM25 article order (best own-block match over the request scope, first 200 units, top 100). The first read menu shows them side by side in blocks of five (vector 1-5, body search 1-5, vector 6-10, ...), an article both found appears once, and every row carries found_by (e.g. '벡터 3위 · 본문 검색 1위'). The before-answer top reads take the top 5 of each list; the definition scope uses the same order. No extra model call. Same environment as ADR-1464: candidate service.py in explicit-generation mode on the selected generation (SQLite originals and body-search index, dataset d4d1d8b4…), isolated local SQLite runtime, vector candidates from Oracle Gold bge-m3 items embedded by a local verified bge-m3 endpoint. All 51 financial CM questions once each, 외규 mode, scope = public grant ∩ financial team. Reference answers grading-only. No MAIN change.",
 'required':['Candidate code bytes unchanged during the run; every loaded semantic_runtime module from the candidate tree',
  'Primary: answer accuracy against the registered reference answer on the current stored original, graded PASS/PARTIAL/FAIL per question by direct comparison, same rule and failure types as ADR-1464; compared with ADR-1464 vector-only (37/5/9) and ADR-1465 hybrid (35/10/6)',
  'Secondary: registered required articles acquired and cited per question (ADR-1464 74/98 after the hyphen-number correction); position of the required article in the first read menu; the 7 ADR-1464 search failures (009 029 030 031 043 010 022); lexical-only candidates kept per question; found_by of the required article in the first menu (vector, body search, both)',
  'Source spans/ACL/wire integrity, duplicate request adds 0 calls, budget respected'],
 'grading_rule':'PASS = the answer states the reference answer’s operative rule(s) from the right article(s) without a material error; a correct answer that also asks an optional follow-up still passes. PARTIAL = right article and part of the rule, or the right rule with a material omission/qualification, or the right conclusion withheld as a question while the rule is stated. FAIL = required article not read, wrong basis, misread, processing error or no answer. Same rule as ADR-1424/1458.',
 'limits':{'physical_total':500,'per_request':40,'per_physical_seconds':180,'reported_cost_usd':4,'time_box_minutes':150,'ram_floor_gib':3,'swap_free_floor_gib':1,'worker_swap_growth_mib':128,'global_swap_growth_mib':512,'workers':1},
 'stop':'UNKNOWN ends that request without retry; independent next question allowed. Three consecutive UNKNOWN cases, runner/resource failure, total budget or the 150-minute time box (checked before each next question) stop the batch. No other tests or model work in this session while the batch runs.',
 'quality_certified':False,'in_sample':True,'order':ORDER,
 'prior_observation':'ADR-1461 (MAIN178+3, vector): 25/9/17. ADR-1464 (MAIN181 code, vector): 37/5/9, required 73/98 (74 after the hyphen-number correction), first action READ 43. ADR-1465 (MAIN181 + hybrid RRF): 35/10/6, required in first menu 57/99, acquired 77/98. These variants were designed from the ADR-1464/1465 detail of these 51 questions, so the whole set is in-sample.'}
put(DES/'criteria.json',criteria);put(DES/'grading-only.json',grades);put(DES/'live-cases.json',cases)
put(DES/'question-source.json',{'path':str(qpath.relative_to(ROOT)),'sha256':sha(qpath),'registry_path':str(rpath.relative_to(ROOT)),'registry_sha256':sha(rpath),'question_policy':'Local experiments use the financial cm51; risk_cm105 not selected. Question strings authorized for the external experiment model by CM_EXPORT_AUTHORIZATION_20261024.'})
put(DES/'provider-policy.json',read(S/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'))
put(DES/'authorization.json',{'request':criteria['authorization'],'question_authorization_path':str(apath.relative_to(ROOT)),'question_authorization_sha256':sha(apath),'documents':granted,'scope':'Registered CM question strings only; reference answers and coordinates are never sent'})
for name in ('oracle-gold.json','embed-validate.json','embed-profile-files.json'):shutil.copyfile(P1459/name,DES/name)
dev=read(P1459/'deviation.json');dev.update(recorded_before_first_model_call=True,model_calls_so_far=0,inherited_from='ADR-1464 design/deviation.json',runner='06_TOOLS/EXPERIMENTS/adr_1467/live_hybrid.py')
put(DES/'deviation.json',dev)
transport=ART/'transport';shutil.copytree(ROOT/'04_EXPERIMENTS/ADR/ADR-1464-main179-definition-priority-cm51-qwen-r2/artifacts/transport',transport)
pins=read(transport/'transport-pins.json');assert all(sha(transport/n)==h for n,h in pins['files'].items())
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['scope'],primary_metric='Per-question PASS/PARTIAL/FAIL against the registered reference answer, compared with ADR-1464 (vector only) and ADR-1465 (hybrid)',success_criteria=criteria['required'],failure_criteria=[criteria['stop'],'Any source/ACL/wire mismatch or action substitution'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['retrieval_stage_plan']['stages_by_arm']={}
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':[],'changes':'Reference only: ADR-1464 MAIN181 code with vector-only initial search for the same 51 questions; not executed here','controls':'Same question strings and reference grading rule'},
 {'id':'candidate','role':'candidate','derived_from':['baseline'],'changes':'MAIN181 + vector list and body-search list shown separately in the first menu with found_by labels (GENOS_RAG_INITIAL_SEARCH=dual)','controls':'Same default profile, same dataset version, independent requests'}]
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
desc={'code_root':str(snapshot.relative_to(ROOT)),'candidate_files':staged,'base_release_files':files,'changed_from_main179':changed,'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
put(DES/'candidate-selected.json',desc)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,production_paths_modified_before_decision=False,runtime_import_allowed=False,production_registry_registered=False,main_wiring_unchanged=True,
 candidates=[dict(desc['pin'],candidate_id='candidate',experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'],runner_path=str(Path(__file__).with_name('live_hybrid.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).with_name('live_hybrid.py')))])
ra=m['retrieval_accounting'];ra['not_applicable_reason']='No stage ledger; per-question vector candidates and acquired/presented article roots are in artifacts/source-wire-audit.json and review-input.json.'
if isinstance(ra.get('stage_ledger'),dict):ra['stage_ledger']['not_applicable_reason']=ra['not_applicable_reason']
put(ADR/'실험/manifest.json',m)
put(ART/'preparation-issues.json',[])
paths=[*Path(__file__).parent.glob('*.py'),*(DES/x for x in ('criteria.json','live-cases.json','authorization.json','provider-policy.json','candidate-selected.json','grading-only.json','oracle-gold.json','embed-validate.json','embed-profile-files.json','deviation.json'))]
put(DES/'freeze-live.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'selected_pointer':ptr,'source_manifest_sha256':rel['data_manifest_sha256'],'model_calls_before_freeze':0})
print('Frozen dual candidate (',len(changed),'changed), 51 CM questions, budget 500/$4/150min; model0')
