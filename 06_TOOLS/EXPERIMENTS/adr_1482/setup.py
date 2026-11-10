"""Freeze the r8 candidate on MAIN187, the standalone question strings r2 (50) and three provider profiles
before any model call (ADR-1482, repeat 2 of 2: ADR-1481 and ADR-1482 run the same frozen code to
measure run-to-run variance).

r8 = MAIN187 (r5 = ADR-1478's code, + modes, + MAIN186/187 logging and Oracle retry) with:
  (1) the r5 losses undone: first-screen server reads per request back to 4 (r5 cut to 2 lost cm-030 rank 4),
      relation-clause anchors 16 in reading order (r5 kept the 6 latest, cm-043 lost 제388조), no
      two-syllable title pieces ("고서");
  (2) a citation inside a list of more than 4 articles is offered, not forced every round (cm-043: 13 reads);
  (3) answer stage: acquired originals are explained before any pause question (cm-006/021 had none),
      one full correction of an invalid answer (cm-042), and the prompt asks to cite the requirement /
      준용 / value / exception articles an explanation rests on (22 read required articles were not cited).
User 2026-11-10: "R5를 강화하는 형태로하는게 맞냐" -> "만들고 실험해봐".
Reference answers go only to the grading-only file."""
from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
P1464=ROOT/'04_EXPERIMENTS/ADR/ADR-1464-main179-definition-priority-cm51-qwen-r2/artifacts/design'
STAGE=ROOT/'09_ARTIFACTS/AUDITS/20261109-open-links'
STAGED={'A':STAGE/'staged-r8b','B':STAGE/'staged-r8b-B','C':STAGE/'staged-r8b-C'}
DES.mkdir(exist_ok=False)
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert ptr['generation']==187 and ptr['release_id']=='hydration-retry-20261110-r1'
rel=read(ROOT/ptr['manifest_path']);files=rel['files'];assert len(files)==545
staged={p:{n:sha(S/n) for n in files} for p,S in STAGED.items()}
changed=sorted(n for n in files if staged['A'][n]!=files[n])
ROUTING='00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'
for p in ('B','C'):
 differs=sorted(n for n in files if staged[p][n]!=staged['A'][n])
 assert ROUTING in differs and all(n==ROUTING or n=='00_SYSTEM/PIPELINE.json' or n.startswith('02_BACKEND/ENGINES/') for n in differs),differs
reg=read(STAGE/'regression-compare-r8.json');intended=read(STAGE/'intended-test-changes-r8.json')
assert sorted(reg['new_failures'])==sorted(x['test'] for x in intended['intended_contract_changes']),reg['new_failures']
guard=read(STAGE/'pytest-guard-hybrid-r8/report.json');assert guard['passed'] is True
put(DES/'baseline.json',{'pointer':ptr,'release':rel,'candidate_source':{'stages':{p:str(S.relative_to(ROOT)) for p,S in STAGED.items()},'main_release':read(STAGE/'main-release.json')},
 'staged_changed_files':changed,'profile_only_differences':'provider routing file and derived pins',
 'regression':{'path':str((STAGE/'regression-compare-r8.json').relative_to(ROOT)),'sha256':sha(STAGE/'regression-compare-r8.json'),'new_failures':reg['new_failures'],
  'intended_contract_changes':str((STAGE/'intended-test-changes-r8.json').relative_to(ROOT)),'fixed':len(reg['fixed'])},
 'r5_simulation':{'path':str((STAGE/'r5/모의적용.json').relative_to(ROOT)),'sha256':sha(STAGE/'r5/모의적용.json')},
 'oracle_scale_guard':{'path':str((STAGE/'pytest-guard-hybrid-r8').relative_to(ROOT)),'passed':guard['passed'],'sql_per_turn_max':guard['sql_per_turn_max'],'mode':'hybrid'}})
qpath=ROOT/'09_ARTIFACTS/AUDITS/20261109-cm-standalone-questions/질문_독립형_51_r2.json'
rpath=ROOT/'01_DATA/GOLDEN/registry-v3-execution-scope.json';apath=ROOT/'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json';spath=ROOT/'01_DATA/review/cm_core_e2e_v3.json'
auth=read(apath);assert any(f['path']=='01_DATA/review/cm_core_e2e_v3.json' and f['sha256']==sha(spath) for f in auth['files'])
standalone=read(qpath);assert standalone['source']['sha256']==sha(spath) and standalone['reference_answers_used'] is False
questions=[q for q in standalone['cases'] if q['id']!='cm-050'];ORDER=[q['id'] for q in questions];assert len(ORDER)==50
registry={c['id']:c for c in read(rpath)['cases'] if c['collection']=='cm'}
assert all(registry[i]['stage']=='ready' and 'local_execution_allowed' in registry[i]['tags'] and 'financial' in registry[i]['tags'] for i in ORDER)
assert all(q['source_question']==registry[q['id']]['provenance']['source_question'] for q in questions)
# ADR-1478 per-article state (same strings r2, r5 code = MAIN184), a reference only
os.environ['ADR_TARGET']='1482'
import subprocess
old=subprocess.run([sys.executable,'-c','import sys,json,os;os.environ["ADR_TARGET"]="1478";sys.path.insert(0,"06_TOOLS/EXPERIMENTS/adr_1478");import collect_review as cr;cr.put=lambda *a,**k:None;print(json.dumps(cr.collect(),ensure_ascii=False))'],cwd=ROOT,capture_output=True,text=True,check=True)
rows1478=json.loads(old.stdout.strip().splitlines()[-1]);prior={r['case_id']:r for r in rows1478};assert set(ORDER)<=set(prior)
put(DES/'adr1478-review-rows.json',{'rows':[{k:r[k] for k in ('case_id','http_status','required_acquired','required_cited','required_total','targets','physical_calls','request_seconds','provider_profile')} for r in rows1478 if r['case_id'] in ORDER],
 'note':'ADR-1478 used the same strings r2 and the r5 code (MAIN184)'})
assigned={c['id']:c['provider_profile'] for c in read(ROOT/'04_EXPERIMENTS/ADR/ADR-1478-main183-relation-clauses-r5-cm50-qwen/artifacts/design/live-cases.json')}
gold=read(P1464/'oracle-gold.json');granted=gold['granted_documents']
cases=[{'id':q['id'],'arms':['candidate'],'document_ids':granted,'provider_profile':assigned[q['id']],'source_question':q['source_question'],'rewrite_type':q['rewrite_type'],
 'steps':[{'number':1,'question':q['standalone_question'],'mode':'외규'}]} for n,q in enumerate(questions)]
grades=[{'id':i,'reference_answer':registry[i]['reference_answer'],'as_of':registry[i]['as_of'],'facets':registry[i]['facets'],
 'adr1478':({k:prior[i][k] for k in ('http_status','required_acquired','required_cited','required_total')} if i in prior else None),
 'targets':[{k:t.get(k) for k in ('law','article','coordinate_key','coordinate_scope','role','evidence_role_v3','doc_id','source_text_sha256','node')} for t in registry[i]['targets']]} for i in ORDER]
criteria={'authorization':'R5를 강화하는 형태로하는게 맞냐 → 만들고 실험해봐 (2026-11-10)',
 'scope':__doc__,
 'questions':'Standalone strings r2, 50 questions (cm-050 out of scope), the same strings and provider assignment as ADR-1478.',
 'required':['Candidate code bytes unchanged during the run; every loaded semantic_runtime module from the candidate tree of the question\'s provider profile',
  'Primary (golden article match only, no judge): registered required articles acquired and cited out of 95, next to ADR-1478 (88 acquired, 66 cited)',
  'Requests without an answer (ADR-1478: 0)',
  'Secondary: body-search terms per question (fusion terms, phrases kept), server reads per kind, model calls and seconds',
  'Source spans/ACL/wire integrity, budget respected'],
 'not_like_for_like':'Code changes from ADR-1478: r8 (listed in scope) plus MAIN186/187 logging and Oracle retry (not on the local SQLite path). ADR-1481 and ADR-1482 are two identical runs; their difference is the run-to-run variance, against which the change from ADR-1478 (one run) is read.',
 'limits':{'physical_total':800,'per_request':40,'per_physical_seconds':180,'reported_cost_usd':8,'time_box_minutes':240,'ram_floor_gib':3,'swap_free_floor_gib':1,'worker_swap_growth_mib':384,'global_swap_growth_mib':1536,'workers':2},
 'parallel':'Same as ADR-1478 (provider profiles A/B/C with the same per-question assignment, two workers on one queue).',
 'rerun':'After both workers finished, every question the resource guard stopped (resource-stop.json and no answer) runs once more alone (rerun.py); that result counts.',
 'rerun_external':'Then every question whose first model call got a provider 5xx (STOP_EXTERNAL.json) runs once more alone with the same provider profile (rerun_external.py, ADR-1479 lost 17 questions to Near AI 5xx); it stops at the first repeated 5xx; that result counts.',
 'stop':'UNKNOWN ends that model call without retry. Per worker: three consecutive questions with an unknown call and no answer, two consecutive runner/resource failures before an answer, the total budget or the 240-minute time box stop it. No other tests or model work during the batch.',
 'quality_certified':False,'in_sample':True,'order':ORDER}
put(DES/'criteria.json',criteria);put(DES/'grading-only.json',grades);put(DES/'live-cases.json',cases)
put(DES/'question-source.json',{'path':str(qpath.relative_to(ROOT)),'sha256':sha(qpath),'registered_suite_path':str(spath.relative_to(ROOT)),'registered_suite_sha256':sha(spath),'registry_path':str(rpath.relative_to(ROOT)),'registry_sha256':sha(rpath),
 'question_policy':'Local experiments use the financial cm51. The standalone strings are rewrites of the authorized question strings from the same questions and topic headings (no reference answer content); not registered in 01_DATA/GOLDEN.'})
sys.path.insert(0,str(STAGED['A']/'02_BACKEND'));from semantic_runtime.legal_agent.provider_routing import validate_policy
for p,S in STAGED.items():
 pol=read(S/ROUTING);validate_policy(pol);put(DES/('provider-policy-'+p+'.json'),pol)
put(DES/'authorization.json',{'request':criteria['authorization'],'question_authorization_path':str(apath.relative_to(ROOT)),'question_authorization_sha256':sha(apath),'documents':granted,
 'scope':'Standalone rewrites of the authorized CM question strings only; reference answers and coordinates are never sent'})
for name in ('oracle-gold.json','embed-validate.json','embed-profile-files.json'):shutil.copyfile(P1464/name,DES/name)
dev=read(P1464/'deviation.json');dev.update(recorded_before_first_model_call=True,model_calls_so_far=0,inherited_from='ADR-1464 design/deviation.json',runner='06_TOOLS/EXPERIMENTS/adr_1482/live_hybrid.py')
put(DES/'deviation.json',dev)
transport=ART/'transport';shutil.copytree(ROOT/'04_EXPERIMENTS/ADR/ADR-1464-main179-definition-priority-cm51-qwen-r2/artifacts/transport',transport)
pins=read(transport/'transport-pins.json');assert all(sha(transport/n)==h for n,h in pins['files'].items())
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['scope'],primary_metric='Registered required articles acquired and cited (golden article match only, no judge); requests without an answer',success_criteria=criteria['required'],failure_criteria=[criteria['stop'],'Any source/ACL/wire mismatch or action substitution'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['retrieval_stage_plan']['stages_by_arm']={}
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':[],'changes':'Reference only: ADR-1478 (r5 code = MAIN184, same strings r2); not executed here','controls':'Same reference answers and required articles'},
 {'id':'candidate','role':'candidate','derived_from':['baseline'],'changes':'MAIN187 + r8 (r5 losses undone, long lists offered, answer explains first / one correction / cites support articles); standalone question strings r2; GENOS_RAG_INITIAL_SEARCH=hybrid','controls':'Same default profile, same dataset version, independent requests, three provider profiles of the same model'}]
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
print('Frozen r8 candidate (',len(changed),'changed), 3 provider profiles,',len(cases),'standalone CM questions r2, budget 800/$8/240min; model0')
