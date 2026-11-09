"""Freeze the source-closure candidate (MAIN182 hybrid + server reads of named, lower-rule and cited
articles + user-only questions), the same SQLite-originals + Oracle-vector environment as ADR-1464/1465 and
the questions (ADR-1468: the 16 questions with a missed required article in ADR-1465/1466; ADR-1469: all 51)
before any model call. Reference answers go only to the grading-only file."""
from common import *
import shutil,csv
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
P1459=ROOT/'04_EXPERIMENTS/ADR/ADR-1464-main179-definition-priority-cm51-qwen-r2/artifacts/design'
STAGE=ROOT/'09_ARTIFACTS/AUDITS/20261109-source-closure/release'
DES.mkdir(exist_ok=False)
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert ptr['generation']==182 and ptr['release_id']=='hybrid-search-20261109-r1'
rel=read(ROOT/ptr['manifest_path']);files=rel['files'];assert len(files)==545
S=STAGE/'source-closure-r3'
staged={n:sha(S/n) for n in files}
changed=sorted(n for n in files if staged[n]!=files[n])
reg=read(STAGE/'regression-compare.json');assert reg['status']=='PASSED' and not reg['new_failures']
put(DES/'baseline.json',{'pointer':ptr,'release':rel,'candidate_source':{'stage':str(S.relative_to(ROOT)),'main_release':read(STAGE/'main-release.json')},'staged_changed_files':changed,
 'regression':{'path':str((STAGE/'regression-compare.json').relative_to(ROOT)),'sha256':sha(STAGE/'regression-compare.json'),'new_failures':0,'fixed':len(reg['fixed'])},
 'oracle_scale_guard':str(Path('09_ARTIFACTS/AUDITS/20261109-source-closure/scale-guard-hybrid'))})
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
MISSED=['cm-004','cm-007','cm-008','cm-010','cm-012','cm-013','cm-017','cm-018','cm-025','cm-029','cm-030','cm-043','cm-045','cm-047','cm-050','cm-051']
RUN=MISSED if TARGET=='1468' else ORDER
gold=read(P1459/'oracle-gold.json');granted=gold['granted_documents']
cases=[{'id':q['id'],'arms':['candidate'],'document_ids':granted,'steps':[{'number':1,'question':q['question'],'mode':'외규'}]} for q in questions if q['id'] in RUN]
assert all(c['steps'][0]['question']==registry[c['id']]['question'] for c in cases)
grades=[{'id':i,'reference_answer':registry[i]['reference_answer'],'as_of':registry[i]['as_of'],'facets':registry[i]['facets'],
 'main161':{k:prior[i][k] for k in ('grade','failure_type','required_acquired','required_total','reason')},
 'adr1464':{k:prior1461[i][k] for k in ('grade','failure_type','required_acquired','required_cited','required_total','reason')},
 'adr1465':{k:prior1465[i][k] for k in ('grade','failure_type','required_acquired','required_cited','required_total','reason')},
 'targets':[{k:t.get(k) for k in ('law','article','coordinate_key','coordinate_scope','role','evidence_role_v3','doc_id','source_text_sha256','node')} for t in registry[i]['targets']]} for i in ORDER if i in RUN]
criteria={'authorization':'1번 싹다 해주고 빠짐없이 / 2번도 진행 / 둘다 코딩해주고 실패했던거 실험해봐 봐그리고 성능측정까지해줘 — '+('실패했던 문항' if TARGET=='1468' else '성능 측정(51문항)'),
 'scope':'Candidate = MAIN182 (hybrid initial search, the selected MAIN) + server reads before the guided answer is final: (a) articles the answer names with a document name (open questions and answer points) are resolved through the request source session (the executor session has no matcher; before this every lookup stopped at NO_MATCHER) and read; (b) a lower rule (decree, rule, detailed rule) whose article specifies a read article with delegation wording (citation role SPECIFIES, another document) is found from that read article\'s connection directory and read; (c) an article the read originals cite by number whose title holds a question word or that two read articles cite is read; (d) the answer asks the user only what the user can answer (no "읽어볼까요/더 찾아볼까요"). At most 4 reads per answer round, a server-forced location is not forced twice. GENOS_RAG_INITIAL_SEARCH=hybrid as in ADR-1465. Same environment as ADR-1464/1465 (candidate service.py explicit generation, selected generation SQLite originals, isolated SQLite runtime, Oracle Gold bge-m3 vector candidates via the local bge-m3 endpoint). '+('The 16 questions with a missed required article in ADR-1465 or ADR-1466' if TARGET=='1468' else 'All 51 financial CM questions')+', once each, 외규 mode, scope = public grant ∩ financial team. Reference answers grading-only. No MAIN change.',
 'required':['Candidate code bytes unchanged during the run; every loaded semantic_runtime module from the candidate tree',
  'Primary (user instruction 2026-11-09: only how far the chosen documents match the golden set, no LLM judge): registered required articles acquired (read original paths) and cited (answer evidence), compared with ADR-1465 (hybrid = MAIN182 behaviour, 77/98 acquired, 68 cited) per article',
  'Secondary: server reads per kind (named, lower rule, cited, vector) and how many required articles they acquired; final answers that ask the user to read/search (볼까요 questions) vs ADR-1465; model calls and seconds vs ADR-1465',
  'Source spans/ACL/wire integrity, duplicate request adds 0 calls, budget respected'],
 'limits':{'physical_total':500,'per_request':40,'per_physical_seconds':180,'reported_cost_usd':4,'time_box_minutes':150,'ram_floor_gib':3,'swap_free_floor_gib':1,'worker_swap_growth_mib':128,'global_swap_growth_mib':512,'workers':1},
 'stop':'UNKNOWN ends that request without retry; independent next question allowed. Three consecutive UNKNOWN cases, runner/resource failure, total budget or the 150-minute time box (checked before each next question) stop the batch. No other tests or model work in this session while the batch runs.',
 'quality_certified':False,'in_sample':True,'order':[i for i in ORDER if i in RUN],
 'prior_observation':'ADR-1465 (MAIN181 + hybrid RRF, the MAIN182 search): acquired 77/98, cited 68, 295 calls, $1.43. ADR-1466 (+LLM rerank) 77/67, ADR-1467 (dual lists) 71/61. In ADR-1466 0 named lookups ran (NO_MATCHER), 6 of 15 missed-article questions answered COVERED, 1 searched again. The rules were designed from these questions, so the set is in-sample.'}
put(DES/'criteria.json',criteria);put(DES/'grading-only.json',grades);put(DES/'live-cases.json',cases)
put(DES/'question-source.json',{'path':str(qpath.relative_to(ROOT)),'sha256':sha(qpath),'registry_path':str(rpath.relative_to(ROOT)),'registry_sha256':sha(rpath),'question_policy':'Local experiments use the financial cm51; risk_cm105 not selected. Question strings authorized for the external experiment model by CM_EXPORT_AUTHORIZATION_20261024.'})
put(DES/'provider-policy.json',read(S/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'))
put(DES/'authorization.json',{'request':criteria['authorization'],'question_authorization_path':str(apath.relative_to(ROOT)),'question_authorization_sha256':sha(apath),'documents':granted,'scope':'Registered CM question strings only; reference answers and coordinates are never sent'})
for name in ('oracle-gold.json','embed-validate.json','embed-profile-files.json'):shutil.copyfile(P1459/name,DES/name)
dev=read(P1459/'deviation.json');dev.update(recorded_before_first_model_call=True,model_calls_so_far=0,inherited_from='ADR-1464 design/deviation.json',runner='06_TOOLS/EXPERIMENTS/adr_1468/live_hybrid.py')
put(DES/'deviation.json',dev)
transport=ART/'transport';shutil.copytree(ROOT/'04_EXPERIMENTS/ADR/ADR-1464-main179-definition-priority-cm51-qwen-r2/artifacts/transport',transport)
pins=read(transport/'transport-pins.json');assert all(sha(transport/n)==h for n,h in pins['files'].items())
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['scope'],primary_metric='Registered required articles acquired and cited (golden article match only, no judge), compared per article with ADR-1465 (hybrid, the MAIN182 search)',success_criteria=criteria['required'],failure_criteria=[criteria['stop'],'Any source/ACL/wire mismatch or action substitution'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['retrieval_stage_plan']['stages_by_arm']={}
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':[],'changes':'Reference only: ADR-1465 MAIN181 + hybrid RRF (the search MAIN182 serves) for the same questions; not executed here','controls':'Same question strings and reference grading rule'},
 {'id':'candidate','role':'candidate','derived_from':['baseline'],'changes':'MAIN182 + server reads before the answer (named, lower-rule, cited question-titled articles) + user-only questions (GENOS_RAG_INITIAL_SEARCH=hybrid)','controls':'Same default profile, same dataset version, independent requests'}]
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
print('Frozen source-closure candidate (',len(changed),'changed),',len(cases),'CM questions, budget 500/$4/150min; model0')
