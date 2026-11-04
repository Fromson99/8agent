from common import *
import shutil,sqlite3
DES.mkdir(exist_ok=False)
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
assert pointer['generation']==142
release=read(ROOT/pointer['manifest_path']);C=ROOT/release['code_root']
assert sha(ROOT/pointer['manifest_path'])==pointer['release_manifest_sha256']
assert all(sha(C/n)==h for n,h in release['files'].items())
put(DES/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release':release})
cases=[{'id':'charter','arms':['baseline','ontology-on'],'document_ids':['7bbe815ff43b6635'],'steps':[{'number':1,'question':'정관을 변경할 때 주주총회 결의요건은 무엇인가요?','mode':'외규'}]},
 {'id':'charter-followup','arms':['baseline','ontology-on'],'document_ids':['7bbe815ff43b6635'],'steps':[{'number':1,'question':'정관 변경에 필요한 찬성 의결권 비율은 무엇이고, 각 비율은 무엇을 기준으로 계산하나요?','mode':'외규'}]}]
put(DES/'live-cases.json',cases)
criteria={'user_request':'온톨로지가 잘 구축되는지 qwen으로 확인 1 그리고 사용했을때 성능이 좋아지는지 확인',
 'build':'One real archived MAIN142 charter judgment, current source bytes, unchanged Workspace.propose/apply -> normalize -> source analysis -> project/compile; one model repair per product stage, maximum9 physical calls.',
 'build_success':['Source-grounded statement with correct thresholds, denominators and conjunction; exact provenance, no invented exceptions or facts.','Existing compiler/validation passes, explicit experimental source review, isolated SQLite publication and new-process lookup.'],
 'use_success':['Both fixed questions have correct supported final answers in OFF and ON; zero source/ACL/wire drift and duplicates add zero calls.','Newly constructed publication actually reaches ON model inputs.','At least10% paired aggregate reduction in request latency, physical calls or reported tokens, without answer regression.'],
 'schedule':['build once','review once; do not hand-correct generated legal content','charter OFF then ON','charter-followup ON then OFF'],
 'build_failure_policy':'Keep failure. Do not invent or hand-repair a bundle. New-bundle A/B remains not executable; independently test existing verified ontology if a suitable exact archived package can be admitted before any live call; otherwise report this dependency explicitly.',
 'limits':{'build_calls':9,'rag_per_request':40,'rag_total':160,'heavy_workers':1,'rss_GiB':5,'start_available_GiB':5,'stop_available_GiB':3,'swap_growth_MiB':128,'stop_after_UNKNOWN':True,'no_adaptive_rerun':True},
 'fixed':{'code':'MAIN142 exact528','model':'qwen/qwen3.8-27b','quantization':'FP8','reasoning':'none','sources':'public Commercial Act selected immutable SQLite snapshot','state':'isolated SQLite','reviews':'default ON','output_cap':None,'production_changes':0},
 'grading':'Codex offline source comparison, not independent human or general legal certification; no grading key enters product; known development case plus unseen wording, no holdout claim.'}
put(DES/'criteria.json',criteria)
grant=read(C/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json');assert cases[0]['document_ids'][0] in grant['public_document_ids']
put(DES/'authorization.json',{'user_request':criteria['user_request'],'public_document_ids':cases[0]['document_ids'],'grant_sha256':sha(C/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json'),'isolated_approval_only':True})
put(DES/'source-scope.json',{'public':cases[0]['document_ids'],'internal':[]})
shutil.copyfile(C/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json',DES/'provider-policy.json')
origin=ROOT/'04_EXPERIMENTS/ADR/ADR-1338-main142-charter-resolution-live/artifacts/public-live/charter-main142/canonical'
record=read(origin/'005-output.json.gz')['answer_progress']['goals'][0]
put(DES/'records.json',[{'id':'actual-charter-judgment','payload':record,'origin':{'path':str((origin/'005-output.json.gz').relative_to(ROOT)),'sha256':sha(origin/'005-output.json.gz'),'pointer':'/answer_progress/goals/0'}}])
view=read(origin/'005.json.gz')['view'];data=ROOT/release['data_path'];db=sqlite3.connect((data/'store.sqlite').as_uri()+'?mode=ro',uri=True)
originals={}
for s in view['sources']:
 did=s['document_id'];assert did in cases[0]['document_ids']
 version=db.execute('SELECT source_artifact_sha256 FROM document WHERE document_id=?',(did,)).fetchone()[0]
 for span in s['spans']:
  uid,text,ver=db.execute('SELECT unit_id,text,source_artifact_sha256 FROM source_block WHERE document_id=? AND block_id=?',(did,span['block_id'])).fetchone()
  assert ver==version and text[span['start_cp']:span['end_cp']]==span['text']
  text='\n'.join(r[0] for r in db.execute('SELECT text FROM source_block WHERE document_id=? AND unit_id=? ORDER BY CAST(block_id AS INTEGER)',(did,uid)))
  anchor={'document_id':did,'version':version,'unit_id':str(uid),'content_sha256':hashlib.sha256(text.encode()).hexdigest(),'label':s['heading']+' / '+str(uid)}
  originals[str(uid)]={'id':'S'+str(uid),'anchor':anchor,'text':text}
db.close();put(DES/'originals.json',list(originals.values()))
put(DES/'originals-origin.json',{'path':str((origin/'005.json.gz').relative_to(ROOT)),'sha256':sha(origin/'005.json.gz'),'selector':'Every own-body unit in actual call005 sources; no golden selection'})
shutil.copytree(ROOT/'04_EXPERIMENTS/ADR/ADR-1338-main142-charter-resolution-live/artifacts/transport',ART/'transport')
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']='Actual generation and native usage of source-grounded ontology on unchanged MAIN142.'
m['design'].update(hypothesis='Existing Qwen authoring produces a reusable source-grounded charter bundle, whose native use improves completed-answer efficiency.',primary_metric='Build source correctness and paired completed-answer efficiency',success_criteria=criteria['build_success']+criteria['use_success'],failure_criteria=['Build or final-answer failure is retained; failed elapsed time is not acceleration; UNKNOWN stops new sends.'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms'][0].update(changes='Ontology OFF',controls='Same528 code, corpus, model, reviews, fresh process/state')
m['design']['arms'][1].update(changes='Ontology ON with newly generated, reviewed, isolated publication',controls='Same528 code, corpus, model, reviews, fresh process/state; build cost separately reported')
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','ontology-on')}
m['dataset'].update(name='Actual public charter investigation and two fixed usage questions',version='20261104-r1',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'))
m['runs'][0].update(arm_ids=['baseline','ontology-on'],selection_rule='One build; two paired questions with alternating order; no adaptive rerun; stop UNKNOWN',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['retrieval_accounting']['stage_ledger'].update(mode='measured',not_applicable_reason=None)
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
can=ac.snapshot(ADR,'main142-build-use',[release['code_root']+'/'+n for n in release['files']],experiment_id=m['experiment_id'],arm_id='ontology-on',run_ids=['run-001'])
ac.freeze(can);assert not ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1]
desc={'code_root':str((can/'revisions'/rev['revision_id']/'snapshot'/release['code_root']).relative_to(ROOT)),'selected_files':release['files'],'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
put(DES/'candidate.json',desc)
print('Prepared exact MAIN142',len(release['files']),'source units',len(originals),flush=True)
