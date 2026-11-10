"""Freeze the citation-relations candidate (MAIN182 + finer citation relations: delegation
definition with item frames, cited rule as subject, application method, case-specific application;
reverse 준용 / case application / lower-rule implementing sentences as selectable one-sentence cards;
question-word-first automatic forward reads), the same SQLite-originals + Oracle-vector environment
as ADR-1464/1465 and a 6-question subset before any model call. Reference answers go only to the
grading-only file."""
from common import *
import shutil,csv
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
P1459=ROOT/'04_EXPERIMENTS/ADR/ADR-1464-main179-definition-priority-cm51-qwen-r2/artifacts/design'
STAGE=ROOT/'09_ARTIFACTS/AUDITS/20261109-closure-relations'
DES.mkdir(exist_ok=False)
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert ptr['generation']==183 and ptr['release_id']=='citation-relations-20261109-r1'
rel=read(ROOT/ptr['manifest_path']);files=rel['files'];assert len(files)==545
S=STAGE/'staged-r5'
staged={n:sha(S/n) for n in files}
changed=sorted(n for n in files if staged[n]!=files[n])
reg=read(STAGE/'regression-compare.json');assert reg['status']=='PASSED' and not reg['new_failures']
put(DES/'baseline.json',{'pointer':ptr,'release':rel,'candidate_source':{'stage':str(S.relative_to(ROOT)),'main_release':read(STAGE/'main-release.json')},'staged_changed_files':changed,
 'regression':{'path':str((STAGE/'regression-compare.json').relative_to(ROOT)),'sha256':sha(STAGE/'regression-compare.json'),'new_failures':0,'fixed':len(reg['fixed'])},
 'oracle_scale_guard':str(Path('09_ARTIFACTS/AUDITS/20261109-citation-relations/scale-guard-hybrid-r5'))})
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
RUN=ORDER  # all 51
gold=read(P1459/'oracle-gold.json');granted=gold['granted_documents']
cases=[{'id':q['id'],'arms':['candidate'],'document_ids':granted,'steps':[{'number':1,'question':q['question'],'mode':'외규'}]} for q in questions if q['id'] in RUN]
assert all(c['steps'][0]['question']==registry[c['id']]['question'] for c in cases)
grades=[{'id':i,'reference_answer':registry[i]['reference_answer'],'as_of':registry[i]['as_of'],'facets':registry[i]['facets'],
 'main161':{k:prior[i][k] for k in ('grade','failure_type','required_acquired','required_total','reason')},
 'adr1464':{k:prior1461[i][k] for k in ('grade','failure_type','required_acquired','required_cited','required_total','reason')},
 'adr1465':{k:prior1465[i][k] for k in ('grade','failure_type','required_acquired','required_cited','required_total','reason')},
 'targets':[{k:t.get(k) for k in ('law','article','coordinate_key','coordinate_scope','role','evidence_role_v3','doc_id','source_text_sha256','node')} for t in registry[i]['targets']]} for i in ORDER if i in RUN]
criteria={'authorization':'1회 실행만하고 1단계 우리 세션에서 싹다해봐 96을 목표로 해봐 / 첫화면 범위는 top 30으로 해줘 / (ADR-1474 18문항 브리핑 뒤) 되물을때 정확하게 되물었는가 · 연결관계 타고갈때는 제한이 필요없는데 · 3번은 빼버려 · 이거 수정하고 돌아갈때마다 정답조문 관련해서 어떻게 바뀌었는지 확인해줘 · 여러개 배치로 돌릴수 있나? 우리 공급자 여러개써서 (2026-11-09)',
 'scope':'Candidate = MAIN183 + source-closure r5 (ADR-1470) + r6 (ADR-1474: evidence-cited reads, narrowed lower-rule reads, first-screen top 30 with at most four a request, read order with carry-over, kept draft points, mode prefix note) + r7 changes made after the 18 questions of ADR-1474: (a) an article reached through a citation (a citing block acquired in this investigation names it, or a lower rule names the acquired article it specifies) is readable even when the first request narrowed the direct search scope; the document must be in the request authorization and the citation is verified again before the read (cm-004: 인수규정 제5조 was refused with NO_ORIGINAL_IN_SELECTED_SCOPE); (b) the investigation asks the user only what the user alone can answer - not which of several readable targets, not whether to read more (cm-007 asked which market, cm-008 asked 더 확인해볼까요) - and a question asked after originals were read no longer drops the server reads; (c) first-screen reads are nearest first again (title-word ordering removed).',
 'required':['Candidate code bytes unchanged during the run; every loaded semantic_runtime module from the candidate tree',
  'Primary (user instruction: golden article match only, no judge): registered required articles acquired and cited out of 98, compared per article with ADR-1470 (81 acquired, 64 cited) and ADR-1465 (77, 68); per-question change is written after every question (artifacts/gold-progress.txt). User target 96 (in-scope ceiling).',
  'Secondary: server reads per kind and required articles reached; connection grants issued and reads still refused by scope; investigation questions to the user; model calls and seconds vs ADR-1470',
  'Source spans/ACL/wire integrity, duplicate request adds 0 calls, budget respected'],
 'limits':{'physical_total':520,'per_request':40,'per_physical_seconds':180,'reported_cost_usd':4,'time_box_minutes':170,'ram_floor_gib':3,'swap_free_floor_gib':1,'worker_swap_growth_mib':384,'global_swap_growth_mib':1536,'workers':2},
 'parallel':'User instruction: two batches at once with two providers. Shard A = questions at even positions, provider order Parasail FP8 then Near AI FP8 on HTTP 429; shard B = odd positions, Near AI FP8 then Parasail FP8 on HTTP 429. Same model (qwen/qwen3.8-27b), same quantization, reasoning none. One request per worker at a time; the two workers and the embedding server share the host, floors unchanged (available RAM 3GiB, free swap 1GiB). Provider is a recorded factor: results of the two shards are also reported separately.',
 'resource_guard_note':'Growth limits 384MiB worker / 1536MiB host as in ADR-1473/1474; with two workers host swap growth is shared, the RAM and free-swap floors are the stop.',
 'stop':'Per shard: UNKNOWN ends that request without retry; three consecutive UNKNOWN cases, total budget (both shards together) or the 170-minute time box stop the shard. A worker that exits by the resource guard after its answer was saved does not stop the shard; a runner/resource failure before the answer leaves that question unanswered and the shard continues, two consecutive such failures stop it. No other tests or model work during the batch.',
 'quality_certified':False,'in_sample':True,'order':[i for i in ORDER if i in RUN],
 'prior_observation':'ADR-1474 (r6, stopped by the operator after 18 questions): acquired 30/39 vs ADR-1470 31 on the same questions, cited 25 vs 22, calls 129 vs 111. cm-008 lost two (the investigation asked the user and the answer stage had no read locations), cm-004 named 인수규정 제5조 but the read was refused by the narrowed scope, cm-013 first-screen reads ordered by title words took the four places, cm-009 gained 코스닥 제31조. Server reads: EVIDENCE_CITED 25, VECTOR 25, SPECIFIES 6, NAMED 3, CITED 1.'}
put(DES/'criteria.json',criteria);put(DES/'grading-only.json',grades);put(DES/'live-cases.json',cases)
put(DES/'question-source.json',{'path':str(qpath.relative_to(ROOT)),'sha256':sha(qpath),'registry_path':str(rpath.relative_to(ROOT)),'registry_sha256':sha(rpath),'question_policy':'Local experiments use the financial cm51; risk_cm105 not selected. Question strings authorized for the external experiment model by CM_EXPORT_AUTHORIZATION_20261024.'})
pol=read(S/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json');put(DES/'provider-policy.json',pol)
polb={**pol,'providers':list(reversed(pol['providers'])),'authorization':{'source':'user_message','text':'추가적으로 여러개 배치로 돌릴수 있나? 우리 공급자 여러개써서','session_id':'1f5448c5-7ec1-5462-99d0-f9c08a637d0e','date':'2026-11-09','retained_rule':'HTTP429 only, one switch to the other FP8 provider'},'reason':'Second parallel shard uses Near AI FP8 first (user instruction 2026-11-09).'}
polb.pop('previous_error',None)
import importlib.util as _u;_s=_u.spec_from_file_location('pr',S/'02_BACKEND/semantic_runtime/legal_agent/provider_routing.py')
sys.path.insert(0,str(S/'02_BACKEND'));from semantic_runtime.legal_agent.provider_routing import validate_policy;validate_policy(polb)
put(DES/'provider-policy-b.json',polb)
put(DES/'authorization.json',{'request':criteria['authorization'],'question_authorization_path':str(apath.relative_to(ROOT)),'question_authorization_sha256':sha(apath),'documents':granted,'scope':'Registered CM question strings only; reference answers and coordinates are never sent'})
for name in ('oracle-gold.json','embed-validate.json','embed-profile-files.json'):shutil.copyfile(P1459/name,DES/name)
dev=read(P1459/'deviation.json');dev.update(recorded_before_first_model_call=True,model_calls_so_far=0,inherited_from='ADR-1464 design/deviation.json',runner='06_TOOLS/EXPERIMENTS/adr_1470/live_hybrid.py')
put(DES/'deviation.json',dev)
transport=ART/'transport';shutil.copytree(ROOT/'04_EXPERIMENTS/ADR/ADR-1464-main179-definition-priority-cm51-qwen-r2/artifacts/transport',transport)
pins=read(transport/'transport-pins.json');assert all(sha(transport/n)==h for n,h in pins['files'].items())
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['scope'],primary_metric='Registered required articles acquired and cited (golden article match only, no judge), compared per article with ADR-1465 (hybrid, the MAIN182 search)',success_criteria=criteria['required'],failure_criteria=[criteria['stop'],'Any source/ACL/wire mismatch or action substitution'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['retrieval_stage_plan']['stages_by_arm']={}
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':[],'changes':'Reference only: ADR-1470 (MAIN182 + source-closure r5) and ADR-1465 (MAIN181 + hybrid RRF) for the same questions; not executed here','controls':'Same question strings and reference grading rule'},
 {'id':'candidate','role':'candidate','derived_from':['baseline'],'changes':'MAIN183 + source-closure r5 + r6 (evidence-cited reads, narrowed lower-rule reads, first-screen top 12, read order and carry-over, kept draft points, mode prefix note; GENOS_RAG_INITIAL_SEARCH=hybrid)','controls':'Same default profile, same dataset version, independent requests'}]
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
paths=[*Path(__file__).parent.glob('*.py'),*(DES/x for x in ('criteria.json','live-cases.json','authorization.json','provider-policy.json','provider-policy-b.json','candidate-selected.json','grading-only.json','oracle-gold.json','embed-validate.json','embed-profile-files.json','deviation.json'))]
put(DES/'freeze-live.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'selected_pointer':ptr,'source_manifest_sha256':rel['data_manifest_sha256'],'model_calls_before_freeze':0})
print('Frozen citation-relations candidate (',len(changed),'changed),',len(cases),'CM questions, budget 520/$4/170min; model0')
