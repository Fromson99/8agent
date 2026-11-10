"""Freeze the relation-clause candidate (plan r5), the standalone question strings r2 (cm-050 out of
scope, 50 questions) and three provider profiles before any model call (ADR-1478).

Candidate = MAIN183 + open links r3 (ADR-1477) + r4 (form originals stored without JSONDecodeError,
forms are not first-screen server reads) + r5:
  (1) relation clauses: an article whose citing sentence sets how an article the answer rests on relates
      to something else is read by the server (준용 to a question-word subject, 경합 when the question
      asks how rules combine, 우선/배제 and 그 밖의 사항 of the same institution), two per request;
  (2) phrase groups: the other articles of one citation phrase (2 to 4, a range included) standing in an
      original the answer rests on or in a read relation clause are read together; longer lists in a
      relation sentence are offered as titles with listed_with;
  (3) relative family names ("법 시행규칙 제14조") resolve by the citing document's declaration, never to
      its own article; the answer's relative mentions use the declared 법;
  (4) generic document family names in the question ("거래소 규정") give a small fusion bonus;
  (5) title words split compounds; a word in a third of first-screen titles is not a title match;
      first-screen server reads per request 4 -> 2; round order relation -> links -> groups -> own picks.
Reference answers go only to the grading-only file."""
from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
P1464=ROOT/'04_EXPERIMENTS/ADR/ADR-1464-main179-definition-priority-cm51-qwen-r2/artifacts/design'
STAGE=ROOT/'09_ARTIFACTS/AUDITS/20261109-open-links'
STAGED={'A':STAGE/'staged-r5c','B':STAGE/'staged-r5c-B','C':STAGE/'staged-r5c-C'}
DES.mkdir(exist_ok=False)
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert ptr['generation']==183 and ptr['release_id']=='citation-relations-20261109-r1'
rel=read(ROOT/ptr['manifest_path']);files=rel['files'];assert len(files)==545
staged={p:{n:sha(S/n) for n in files} for p,S in STAGED.items()}
changed=sorted(n for n in files if staged['A'][n]!=files[n])
ROUTING='00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'
for p in ('B','C'):
 differs=sorted(n for n in files if staged[p][n]!=staged['A'][n])
 assert ROUTING in differs and all(n==ROUTING or n=='00_SYSTEM/PIPELINE.json' or n.startswith('02_BACKEND/ENGINES/') for n in differs),differs
reg=read(STAGE/'regression-compare-r5c.json');intended=read(STAGE/'intended-test-changes-r5.json')
assert sorted(reg['new_failures'])==sorted(x['test'] for x in intended['intended_contract_changes']),reg['new_failures']
guard=read(STAGE/'pytest-guard-hybrid-r5/report.json');assert guard['passed'] is True
put(DES/'baseline.json',{'pointer':ptr,'release':rel,'candidate_source':{'stages':{p:str(S.relative_to(ROOT)) for p,S in STAGED.items()},'main_release':read(STAGE/'main-release.json')},
 'staged_changed_files':changed,'profile_only_differences':'provider routing file and derived pins',
 'regression':{'path':str((STAGE/'regression-compare-r5c.json').relative_to(ROOT)),'sha256':sha(STAGE/'regression-compare-r5c.json'),'new_failures':reg['new_failures'],
  'intended_contract_changes':str((STAGE/'intended-test-changes-r5.json').relative_to(ROOT)),'fixed':len(reg['fixed'])},
 'simulation':{'path':str((STAGE/'r5/모의적용.json').relative_to(ROOT)),'sha256':sha(STAGE/'r5/모의적용.json')},
 'oracle_scale_guard':{'path':str((STAGE/'pytest-guard-hybrid-r5').relative_to(ROOT)),'passed':guard['passed'],'sql_per_turn_max':guard['sql_per_turn_max'],'mode':'hybrid'}})
qpath=ROOT/'09_ARTIFACTS/AUDITS/20261109-cm-standalone-questions/질문_독립형_51_r2.json'
rpath=ROOT/'01_DATA/GOLDEN/registry-v3-execution-scope.json';apath=ROOT/'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json';spath=ROOT/'01_DATA/review/cm_core_e2e_v3.json'
auth=read(apath);assert any(f['path']=='01_DATA/review/cm_core_e2e_v3.json' and f['sha256']==sha(spath) for f in auth['files'])
standalone=read(qpath);assert standalone['source']['sha256']==sha(spath) and standalone['reference_answers_used'] is False
questions=[q for q in standalone['cases'] if q['id']!='cm-050'];ORDER=[q['id'] for q in questions];assert len(ORDER)==50
registry={c['id']:c for c in read(rpath)['cases'] if c['collection']=='cm'}
assert all(registry[i]['stage']=='ready' and 'local_execution_allowed' in registry[i]['tags'] and 'financial' in registry[i]['tags'] for i in ORDER)
assert all(q['source_question']==registry[q['id']]['provenance']['source_question'] for q in questions)
# ADR-1477 per-article state (standalone strings r1, code r3), a reference only
os.environ['ADR_TARGET']='1478'
import subprocess
old=subprocess.run([sys.executable,'-c','import sys,json,os;os.environ["ADR_TARGET"]="1477";sys.path.insert(0,"06_TOOLS/EXPERIMENTS/adr_1477");import collect_review as cr;cr.put=lambda *a,**k:None;print(json.dumps(cr.collect(),ensure_ascii=False))'],cwd=ROOT,capture_output=True,text=True,check=True)
rows1477=json.loads(old.stdout.strip().splitlines()[-1]);prior={r['case_id']:r for r in rows1477};missing1477=sorted(set(ORDER)-set(prior))  # no response in ADR-1477 (cm-006 resource stop)
put(DES/'adr1477-review-rows.json',{'rows':[{k:r[k] for k in ('case_id','http_status','required_acquired','required_cited','required_total','targets','physical_calls','request_seconds','provider_profile')} for r in rows1477 if r['case_id'] in ORDER],
 'note':'ADR-1477 used the standalone strings r1 (cm-028 differs in r2) and the open-links r3 code'})
assigned={c['id']:c['provider_profile'] for c in read(ROOT/'04_EXPERIMENTS/ADR/ADR-1477-main183-open-links-r3-standalone-cm51-qwen/artifacts/design/live-cases.json')}
gold=read(P1464/'oracle-gold.json');granted=gold['granted_documents']
cases=[{'id':q['id'],'arms':['candidate'],'document_ids':granted,'provider_profile':assigned[q['id']],'source_question':q['source_question'],'rewrite_type':q['rewrite_type'],
 'steps':[{'number':1,'question':q['standalone_question'],'mode':'외규'}]} for n,q in enumerate(questions)]
grades=[{'id':i,'reference_answer':registry[i]['reference_answer'],'as_of':registry[i]['as_of'],'facets':registry[i]['facets'],
 'adr1477':({k:prior[i][k] for k in ('http_status','required_acquired','required_cited','required_total')} if i in prior else None),
 'targets':[{k:t.get(k) for k in ('law','article','coordinate_key','coordinate_scope','role','evidence_role_v3','doc_id','source_text_sha256','node')} for t in registry[i]['targets']]} for i in ORDER]
criteria={'authorization':'우리 그럼 위에서 말했던 거 포함해서 상세하게 계획 세워봐 → 범위인용은 4개를 한번에 읽게 하자 바로 진행 (2026-11-10); 계획 r5(09_ARTIFACTS/AUDITS/20261109-open-links/계획_r5.txt) 7-3: 50문항(cm-050 제외), 질문 r2, 공급자 묶음 3개·작업 2개, 1회, 자원 중단 문항은 끝난 뒤 1회 단독 재실행',
 'scope':__doc__,
 'questions':'Standalone strings r2 (cm-028 adds "과세특례"; the other 49 are r1). cm-050 is out of scope (its required documents are not in the granted set). Reference answers and required articles are the registered ones.',
 'required':['Candidate code bytes unchanged during the run; every loaded semantic_runtime module from the candidate tree of the question\'s provider profile',
  'Pre-registered (plan r5 7-3): requests without an answer = 0; required articles acquired > ADR-1477 on the same 50 questions (77/95) with at most 3 lost; server reads in total <= ADR-1477 (EVIDENCE_CITED 77 + VECTOR 94 + NAMED 17 + LINK 77 + SPECIFIES 23 + CITED 17 + NAMED_RELATIVE 16 = 321)',
  'Primary (golden article match only, no judge): registered required articles acquired and cited out of 95, split into the directly answering article and its companion articles',
  'Secondary: server reads per kind (RELATION, LINK, GROUP, EVIDENCE_CITED, VECTOR, SPECIFIES, CITED, NAMED, NAMED_RELATIVE) and required articles reached by each; RELATION_CLAUSES_OFFERED events; answer calls per request; model calls and seconds',
  'Source spans/ACL/wire integrity, budget respected'],
 'not_like_for_like':'ADR-1477 (78/98 incl. cm-050; 77/95 without) used the r3 code and the standalone strings r1; this run changes the code (r4+r5) and cm-028\'s string. A reference, not a baseline arm.',
 'limits':{'physical_total':800,'per_request':40,'per_physical_seconds':180,'reported_cost_usd':8,'time_box_minutes':240,'ram_floor_gib':3,'swap_free_floor_gib':1,'worker_swap_growth_mib':384,'global_swap_growth_mib':1536,'workers':2},
 'parallel':'Same as ADR-1477: three provider profiles with the same per-question assignment as ADR-1477 (A Parasail FP8 then Near AI FP8 on HTTP 429; B Reka FP8 then Parasail FP8; C Near AI FP8 then Reka FP8), qwen/qwen3.8-27b, FP8, reasoning none, one switch on HTTP 429 only. Two workers take questions from one queue; each question runs once in a fresh process with the candidate tree of its profile.',
 'rerun':'After both workers finished, every question the resource guard stopped (resource-stop.json and no answer) runs once more alone (rerun.py, folder …-candidate-rerun); that result counts. No other retry; a rerun is not repeated.',
 'stop':'UNKNOWN ends that model call without retry (the candidate returns the verified draft or the acquired originals). Per worker: three consecutive questions with an unknown call and no answer, two consecutive runner/resource failures before an answer, the total budget or the 240-minute time box stop it. No other tests or model work during the batch.',
 'quality_certified':False,'in_sample':True,'order':ORDER,
 'simulation':'Model-free application of the r5 rules to the ADR-1477 evidence articles and the reference index (09_ARTIFACTS/AUDITS/20261109-open-links/r5/모의적용.json): 0.92 extra reads per request (max 9 in one request, spread by the four-place rounds), reaching cm-043 상법 제415조, cm-013 벤처법 제16조의6·상법 제340조의5, cm-027 상법 제542조의3; cm-025 depends on the model choosing 제35·39조 from the 22 titles 상증법 제43조 lists.',
 'prior_observation':'ADR-1477 (09_ARTIFACTS/AUDITS/20261109-open-links/결과.txt): 422 x3 from storing a form original (journal_storage), cm-006 resource stop, cm-028 lost the tax context in r1, 9 search misses traced to unread relation clauses, phrase members, family names and title words.'}
put(DES/'criteria.json',criteria);put(DES/'grading-only.json',grades);put(DES/'live-cases.json',cases)
put(DES/'question-source.json',{'path':str(qpath.relative_to(ROOT)),'sha256':sha(qpath),'registered_suite_path':str(spath.relative_to(ROOT)),'registered_suite_sha256':sha(spath),'registry_path':str(rpath.relative_to(ROOT)),'registry_sha256':sha(rpath),
 'question_policy':'Local experiments use the financial cm51. The standalone strings are rewrites of the authorized question strings from the same questions and topic headings (no reference answer content); not registered in 01_DATA/GOLDEN.'})
sys.path.insert(0,str(STAGED['A']/'02_BACKEND'));from semantic_runtime.legal_agent.provider_routing import validate_policy
for p,S in STAGED.items():
 pol=read(S/ROUTING);validate_policy(pol);put(DES/('provider-policy-'+p+'.json'),pol)
put(DES/'authorization.json',{'request':criteria['authorization'],'question_authorization_path':str(apath.relative_to(ROOT)),'question_authorization_sha256':sha(apath),'documents':granted,
 'scope':'Standalone rewrites of the authorized CM question strings only; reference answers and coordinates are never sent'})
for name in ('oracle-gold.json','embed-validate.json','embed-profile-files.json'):shutil.copyfile(P1464/name,DES/name)
dev=read(P1464/'deviation.json');dev.update(recorded_before_first_model_call=True,model_calls_so_far=0,inherited_from='ADR-1464 design/deviation.json',runner='06_TOOLS/EXPERIMENTS/adr_1478/live_hybrid.py')
put(DES/'deviation.json',dev)
transport=ART/'transport';shutil.copytree(ROOT/'04_EXPERIMENTS/ADR/ADR-1464-main179-definition-priority-cm51-qwen-r2/artifacts/transport',transport)
pins=read(transport/'transport-pins.json');assert all(sha(transport/n)==h for n,h in pins['files'].items())
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['scope'],primary_metric='Registered required articles acquired and cited (golden article match only, no judge); requests without an answer',success_criteria=criteria['required'],failure_criteria=[criteria['stop'],'Any source/ACL/wire mismatch or action substitution'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['retrieval_stage_plan']['stages_by_arm']={}
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':[],'changes':'Reference only: ADR-1477 (MAIN183 + open links r3, standalone strings r1); not executed here and not like-for-like','controls':'Same reference answers and required articles'},
 {'id':'candidate','role':'candidate','derived_from':['baseline'],'changes':'MAIN183 + open links r3 + r4 form fixes + r5 relation clauses, phrase groups, family names, title words; standalone question strings r2; GENOS_RAG_INITIAL_SEARCH=hybrid','controls':'Same default profile, same dataset version, independent requests, three provider profiles of the same model'}]
m['dataset'].update(name='financial CM 50 standalone strings r2 (cm-050 out of scope)',version='cm51-standalone-questions-r2',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'),legal_version_checked=True,reference_version_checked=False)
m['runs'][0].update(arm_ids=['candidate'],selection_rule=criteria['stop'],artifact_path=str((ART/'review-input.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['in_sample']=True
pinned=[]
for p,S in STAGED.items():
 can=ac.snapshot(ADR,'candidate-'+p.lower(),list(files),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
 for n in files:
  if sha(can/'snapshot'/n)!=staged[p][n]:shutil.copyfile(S/n,can/'snapshot'/n)
 ac.freeze(can);assert not ac.validate(can),ac.validate(can)
 cm=read(can/'candidate.json');rev=cm['revisions'][-1];snapshot=can/'revisions'/rev['revision_id']/'snapshot'
 assert all(sha(snapshot/n)==staged[p][n] for n in files)
 desc={'provider_profile':p,'code_root':str(snapshot.relative_to(ROOT)),'candidate_files':staged[p],'base_release_files':files,'changed_from_main183':sorted(n for n in files if staged[p][n]!=files[n]),
  'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
 put(DES/('candidate-selected-'+p+'.json'),desc)
 pinned.append(dict(desc['pin'],candidate_id='candidate-'+p.lower(),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'],runner_path=str(Path(__file__).with_name('live_hybrid.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).with_name('live_hybrid.py'))))
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,production_paths_modified_before_decision=False,runtime_import_allowed=False,production_registry_registered=False,main_wiring_unchanged=True,candidates=pinned)
ra=m['retrieval_accounting'];ra['not_applicable_reason']='No stage ledger; per-question vector candidates and acquired/presented article roots are in the journals and review-input.json.'
if isinstance(ra.get('stage_ledger'),dict):ra['stage_ledger']['not_applicable_reason']=ra['not_applicable_reason']
put(ADR/'실험/manifest.json',m)
put(ART/'preparation-issues.json',[])
paths=[*Path(__file__).parent.glob('*.py'),*(DES/x for x in ('criteria.json','live-cases.json','authorization.json','provider-policy-A.json','provider-policy-B.json','provider-policy-C.json','candidate-selected-A.json','candidate-selected-B.json','candidate-selected-C.json','grading-only.json','oracle-gold.json','embed-validate.json','embed-profile-files.json','deviation.json'))]
put(DES/'freeze-live.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'selected_pointer':ptr,'source_manifest_sha256':rel['data_manifest_sha256'],'model_calls_before_freeze':0})
print('Frozen relation-clause candidate (',len(changed),'changed), 3 provider profiles,',len(cases),'standalone CM questions r2, budget 800/$8/240min; model0')
