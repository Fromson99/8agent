"""Freeze the open-links candidate, the standalone CM51 question strings and three provider
profiles before any model call (ADR-1477; ADR-1476 was stopped after 3 questions).

Candidate = MAIN183 + source-closure r5/r6/r7 (ADR-1470/1474/1475) + open links:
  (1) the next article is chosen from the sentence the answer rests on (준용 / value reference /
      lower rule of a used article), not from title words; (2) the answer is not final while such a
      link of its own evidence is unread (read in every answer round, one step deep);
  (3) a first-screen article whose title adds a question word no read title holds is read first and
      the next answer call is told to compare subjects; (4) the answer call receives at most 45,000
      characters of originals and 12 evidence references per explanation, and an answer call with an
      unknown outcome returns the verified draft or the acquired originals (never a second send);
  (5) the body search also gets the question's own content words.
Reference answers go only to the grading-only file."""
from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
P1464=ROOT/'04_EXPERIMENTS/ADR/ADR-1464-main179-definition-priority-cm51-qwen-r2/artifacts/design'
STAGE=ROOT/'09_ARTIFACTS/AUDITS/20261109-open-links'
STAGED={'A':STAGE/'staged-r3','B':STAGE/'staged-r3-B','C':STAGE/'staged-r3-C'}
DES.mkdir(exist_ok=False)
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert ptr['generation']==183 and ptr['release_id']=='citation-relations-20261109-r1'
rel=read(ROOT/ptr['manifest_path']);files=rel['files'];assert len(files)==545
staged={p:{n:sha(S/n) for n in files} for p,S in STAGED.items()}
changed=sorted(n for n in files if staged['A'][n]!=files[n])
ROUTING='00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'
for p in ('B','C'):
 differs=sorted(n for n in files if staged[p][n]!=staged['A'][n])
 assert ROUTING in differs and all(n==ROUTING or n=='00_SYSTEM/PIPELINE.json' or n.startswith('02_BACKEND/ENGINES/') for n in differs),differs
reg=read(STAGE/'regression-compare-r3.json');intended=read(STAGE/'intended-test-changes.json')
assert sorted(reg['new_failures'])==sorted(x['test'] for x in intended['intended_contract_changes']),reg['new_failures']
guard=read(STAGE/'pytest-guard-hybrid-r3/report.json');assert guard['passed'] is True
put(DES/'baseline.json',{'pointer':ptr,'release':rel,'candidate_source':{'stages':{p:str(S.relative_to(ROOT)) for p,S in STAGED.items()},'main_release':read(STAGE/'main-release.json')},
 'staged_changed_files':changed,'profile_only_differences':'provider routing file and derived pins',
 'regression':{'path':str((STAGE/'regression-compare-r3.json').relative_to(ROOT)),'sha256':sha(STAGE/'regression-compare-r3.json'),'new_failures':reg['new_failures'],
  'intended_contract_changes':str((STAGE/'intended-test-changes.json').relative_to(ROOT)),'fixed':len(reg['fixed'])},
 'oracle_scale_guard':{'path':str((STAGE/'pytest-guard-hybrid-r3').relative_to(ROOT)),'passed':guard['passed'],'sql_per_turn_max':guard['sql_per_turn_max'],'mode':'hybrid'}})
qpath=ROOT/'09_ARTIFACTS/AUDITS/20261109-cm-standalone-questions/질문_독립형_51.json'
rpath=ROOT/'01_DATA/GOLDEN/registry-v3-execution-scope.json';apath=ROOT/'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json';spath=ROOT/'01_DATA/review/cm_core_e2e_v3.json'
auth=read(apath);assert any(f['path']=='01_DATA/review/cm_core_e2e_v3.json' and f['sha256']==sha(spath) for f in auth['files'])
standalone=read(qpath);assert standalone['source']['sha256']==sha(spath) and standalone['reference_answers_used'] is False
questions=standalone['cases'];ORDER=[q['id'] for q in questions];assert len(ORDER)==51
registry={c['id']:c for c in read(rpath)['cases'] if c['collection']=='cm'}
assert all(registry[i]['stage']=='ready' and 'local_execution_allowed' in registry[i]['tags'] and 'financial' in registry[i]['tags'] for i in ORDER)
assert all(q['source_question']==registry[q['id']]['provenance']['source_question'] for q in questions)
# ADR-1475 per-article state (registered question strings), a reference only
os.environ['ADR_TARGET']='1477'
import subprocess
old=subprocess.run([sys.executable,'-c','import sys,json,os;os.environ["ADR_TARGET"]="1475";sys.path.insert(0,"06_TOOLS/EXPERIMENTS/adr_1475");import collect_review as cr;cr.put=lambda *a,**k:None;print(json.dumps(cr.collect(),ensure_ascii=False))'],cwd=ROOT,capture_output=True,text=True,check=True)
rows1475=json.loads(old.stdout.strip().splitlines()[-1]);prior={r['case_id']:r for r in rows1475};assert set(prior)==set(ORDER)
put(DES/'adr1475-review-rows.json',{'rows':[{k:r[k] for k in ('case_id','http_status','required_acquired','required_cited','required_total','targets','physical_calls','request_seconds')} for r in rows1475],
 'note':'ADR-1475 used the registered question strings with the (업무 문맥: …) line'})
gold=read(P1464/'oracle-gold.json');granted=gold['granted_documents']
cases=[{'id':q['id'],'arms':['candidate'],'document_ids':granted,'provider_profile':PROFILES[n%3],'source_question':q['source_question'],'rewrite_type':q['rewrite_type'],
 'steps':[{'number':1,'question':q['standalone_question'],'mode':'외규'}]} for n,q in enumerate(questions)]
grades=[{'id':i,'reference_answer':registry[i]['reference_answer'],'as_of':registry[i]['as_of'],'facets':registry[i]['facets'],
 'adr1475':{k:prior[i][k] for k in ('http_status','required_acquired','required_cited','required_total')},
 'targets':[{k:t.get(k) for k in ('law','article','coordinate_key','coordinate_scope','role','evidence_role_v3','doc_id','source_text_sha256','node')} for t in registry[i]['targets']]} for i in ORDER]
criteria={'authorization':'싹다 구현해보고 한번 실험돌려봐봐 전체다 여러개 배치로 돌려 qwen으로 넣는것도 여러 공급자 다양하게 써서해줘 (2026-11-09); 질문은 사용자 요청으로 만든 독립형 51문항("cm을 각각 질문으로 한다고 했을때 … 만들어봐봐", "우리 다 바꿨거든")',
 'scope':__doc__,
 'questions':'Standalone strings (one sentence, no (업무 문맥: …) line): A unchanged 22, B subject from the topic\'s first question 17, C subject from the topic heading 8, D article-specified 4 (cm-002/003/004/019). Reference answers and required articles are the registered ones.',
 'required':['Candidate code bytes unchanged during the run; every loaded semantic_runtime module from the candidate tree of the question\'s provider profile',
  'Primary (golden article match only, no judge): registered required articles acquired and cited out of 98, reported for all 51, for the 47 not article-specified, and split into the directly answering article (evidence_role_v3 MAIN) and its companion articles',
  'Requests that end without an answer (HTTP != 200): ADR-1475 had 4 (504 x3, 422 x1)',
  'Secondary: server reads per kind (LINK, EVIDENCE_CITED, VECTOR, SPECIFIES, CITED, NAMED, NAMED_RELATIVE) and required articles reached by each; answer calls per request and their input size; GUIDED_ANSWER_INPUT_BUDGET and GUIDED_ANSWER_CALL_UNKNOWN events; model calls and seconds',
  'Source spans/ACL/wire integrity, budget respected'],
 'not_like_for_like':'ADR-1475 (77 acquired, 66 cited) used the registered question strings; this run changes the question strings and the code together, so the difference is not attributed to either. No baseline arm on the standalone strings is run here.',
 'limits':{'physical_total':800,'per_request':40,'per_physical_seconds':180,'reported_cost_usd':8,'time_box_minutes':240,'ram_floor_gib':3,'swap_free_floor_gib':1,'worker_swap_growth_mib':384,'global_swap_growth_mib':1536,'workers':2},
 'parallel':'User instruction: several batches, several providers. Three provider profiles by question position (n mod 3): A Parasail FP8 then Near AI FP8 on HTTP 429; B Reka FP8 then Parasail FP8; C Near AI FP8 then Reka FP8. Same model qwen/qwen3.8-27b, FP8, reasoning none, one switch on HTTP 429 only. Two workers take questions from one queue (a third worker does not fit the 3GiB available-RAM floor); each question runs once in a fresh process with the candidate tree of its profile. The provider is a recorded factor and results are also reported per profile.',
 'stop':'UNKNOWN ends that model call without retry (the candidate returns the verified draft or the acquired originals). Per worker: three consecutive questions with an unknown call and no answer, two consecutive runner/resource failures before an answer, the total budget or the 240-minute time box stop it. No other tests or model work during the batch.',
 'quality_certified':False,'in_sample':True,'order':ORDER,
 'adr1476':'Stopped by the operator after 3 questions (cm-008, cm-001, cm-002; all HTTP 200, 20 calls). cm-008 read 코스닥 제13조 only in the second answer round, after two plain citations of the evidence, and its 시행세칙 제15조 was not followed because links stopped by answer round. r3: link depth is counted along the chain (a first-screen/named/chosen read starts at 0), binding links then another-direction first-screen reads go first in a round, and one article is scheduled once.',
 'prior_observation':'ADR-1475 misses traced per logic (09_ARTIFACTS/AUDITS/20261109-closure-relations/결과.txt): twelve-location cut by common title words and reversed ties, locations without a unit id merged by document, link reads only in the first round, lower-rule anchors in reading order, named articles without a law name unresolved, definition articles read first, body search without the question words, answer calls growing to 128k characters and four requests without an answer.'}
put(DES/'criteria.json',criteria);put(DES/'grading-only.json',grades);put(DES/'live-cases.json',cases)
put(DES/'question-source.json',{'path':str(qpath.relative_to(ROOT)),'sha256':sha(qpath),'registered_suite_path':str(spath.relative_to(ROOT)),'registered_suite_sha256':sha(spath),'registry_path':str(rpath.relative_to(ROOT)),'registry_sha256':sha(rpath),
 'question_policy':'Local experiments use the financial cm51. The standalone strings are rewrites of the authorized question strings from the same questions and topic headings (no reference answer content); not registered in 01_DATA/GOLDEN.'})
sys.path.insert(0,str(STAGED['A']/'02_BACKEND'));from semantic_runtime.legal_agent.provider_routing import validate_policy
for p,S in STAGED.items():
 pol=read(S/ROUTING);validate_policy(pol);put(DES/('provider-policy-'+p+'.json'),pol)
put(DES/'authorization.json',{'request':criteria['authorization'],'question_authorization_path':str(apath.relative_to(ROOT)),'question_authorization_sha256':sha(apath),'documents':granted,
 'scope':'Standalone rewrites of the authorized CM question strings only; reference answers and coordinates are never sent'})
for name in ('oracle-gold.json','embed-validate.json','embed-profile-files.json'):shutil.copyfile(P1464/name,DES/name)
dev=read(P1464/'deviation.json');dev.update(recorded_before_first_model_call=True,model_calls_so_far=0,inherited_from='ADR-1464 design/deviation.json',runner='06_TOOLS/EXPERIMENTS/adr_1477/live_hybrid.py')
put(DES/'deviation.json',dev)
transport=ART/'transport';shutil.copytree(ROOT/'04_EXPERIMENTS/ADR/ADR-1464-main179-definition-priority-cm51-qwen-r2/artifacts/transport',transport)
pins=read(transport/'transport-pins.json');assert all(sha(transport/n)==h for n,h in pins['files'].items())
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['scope'],primary_metric='Registered required articles acquired and cited (golden article match only, no judge); requests without an answer',success_criteria=criteria['required'],failure_criteria=[criteria['stop'],'Any source/ACL/wire mismatch or action substitution'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['retrieval_stage_plan']['stages_by_arm']={}
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':[],'changes':'Reference only: ADR-1475 (MAIN183 + source-closure r7, registered question strings); not executed here and not like-for-like','controls':'Same reference answers and required articles'},
 {'id':'candidate','role':'candidate','derived_from':['baseline'],'changes':'MAIN183 + source-closure r5/r6/r7 + open links, answer input budget, unknown-outcome return, coverage-first first-screen reads, question words in the body search; standalone question strings; GENOS_RAG_INITIAL_SEARCH=hybrid','controls':'Same default profile, same dataset version, independent requests, three provider profiles of the same model'}]
m['dataset'].update(name='financial CM 51 standalone strings (draft 2026-11-09)',version='cm51-standalone-questions-draft',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'),legal_version_checked=True,reference_version_checked=False)
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
print('Frozen open-links candidate (',len(changed),'changed), 3 provider profiles,',len(cases),'standalone CM questions, budget 800/$8/240min; model0')
