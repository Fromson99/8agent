from pathlib import Path
import datetime,hashlib,json,shutil,subprocess,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0921-connected-read-document-terms';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert pointer['generation']==88
release=read(R/pointer['manifest_path']);C=R/release['code_root']
put(D/'baseline.json',{'pointer':pointer,'manifest':release})
put(D/'cases.json',[{'id':'leverage-comparison','api_type':'WORKFLOW_RUN','workflow_id':'risk_team_compare_workflow','question':'대사: 레버리지비율 관련한 외부 규정은 무엇이고, 내부 규정에는 어떻게 반영되어있냐'}])
c={'hypothesis':'Persistent acquired-source reference anchors and document-bounded term discovery expose related originals; after reading a linked original the model can retain and select both originals under existing read/adoption contracts.',
'primary_metric':'Actual candidate discovery/delivery and linked-source joint selection with bounded resources and intact evidence/state contracts.',
'success_criteria':['Synthetic A unread conclusion -> incoming B read -> A+B selected with exact sources, no automatic legal adoption','Document-scoped terms expose cross-article candidates and paginated continuation without whole-corpus search or hidden original adoption','Focus restoration/reentry preserves acquired reference anchors and known unread candidates','ACL/hash/stale binding/timeout/partial/duplicate/repeated cursor contracts pass; no new semantic finish gate','One frozen actual user workflow per arm reaches durable completed or partial response, original receipts consistent; report legal misses separately'],
'failure_criteria':['Unauthorized, unread or modified source adopted','Lost original or repeat budgets reset on return/resume','Unbounded catalogue loading or repeated failing query','Stale action accepted or source model-return blocked for uncertainty'],
'limits':{'workers':1,'physical_calls_per_request':40,'wall_seconds_per_request':1800,'rss_gib':6,'address_space_gib':8,'min_available_gib':4,'disk_gib':10},
'selection':'Known leverage question once per baseline and connected arm in that order; synthetic finite contracts frozen before testing. No gold in product input, adaptive live rerun or automatic MAIN activation.',
'controls':'MAIN88 full serving inventory/data/profile/model unchanged except declared candidate products and their dependency manifests. Existing local public/synthetic scope only.',
'failure_owner':'Existing navigation execute-tool and output.bounded_decision own recovery/one repair. Automatic bounded term catalogue records failed/partial status without retrying unchanged inputs. Hash/ACL/state failures propagate; original handoff remains allowed with uncertainty.',
'candidate_policy':{'term_documents_per_view':4,'term_articles_per_page':6,'term_keys_per_document':4,'term_previews_per_article':1,'max_catalogue_chars':10000,'reference_anchors_per_round':16,'semantic_role':'LLM opinion, no automatic applicability or forced read-all'},
'in_sample':True,'decision_eligible':False,'model':'qwen/qwen3.8-27b','provider':'Parasail FP8','reasoning':'none','fallback':False,'new_data_generation':False,'genos_execution':False,'main_changed':False}
put(D/'criteria.json',c)
put(D/'working-before.json',{n:sha(R/n) for n in release['files']})
put(D/'parent-drift.json',[{'path':n,'selected':h,'working':sha(R/n)} for n,h in release['files'].items() if sha(R/n)!=h])
m=read(A/'실험/manifest.json');m['design'].update({k:c[k] for k in ('hypothesis','primary_metric','success_criteria','failure_criteria')});m['design']['criteria_frozen_before_run']=True
m['lineage']['hypothesis_delta']=c['hypothesis'];m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-0917-experiment-v1/qualified'],'changes':'None; frozen MAIN88 same application/service dispatch as candidate','controls':c['controls']},{'id':'connected','role':'candidate','derived_from':['baseline'],'changes':c['hypothesis'],'controls':c['controls']}]
m['runs'][0].update(arm_ids=['baseline','connected'],selection_rule=c['selection'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='connected-read-known-leverage',version='20261019-v1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
m['llm_policy']['llm_calls']=[{'role':'workflow_and_native_rag','class':'product','model':c['model'],'repeats':2,'max_calls':80,'temperature':0}]
stages=[{'stage_id':'native_read','kind':'source','parent_stage_ids':[]},{'stage_id':'child_adopted','kind':'select','parent_stage_ids':['native_read']},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['child_adopted']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','connected')}
m['retrieval_accounting']['changed']=True;m['retrieval_accounting']['not_applicable_reason']='Known required-source checks kept offline; full legal gold unapproved. Exact native read, handoff and final cited ledger plus separate observed candidate trace.'
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','connected','--experiment-id',m['experiment_id'],'--arm-id','connected','--run-id','run-001']
for n in release['files']:cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
S=R/'02_BACKEND/lawrag/research/candidates/adr_0921/connected/snapshot'
for n,h in release['files'].items():
 assert sha(C/n)==h,n
 shutil.copy2(C/n,S/n)
put(D/'baseline-binding.json',{'code_root':release['code_root'],'serving_files':release['files']})
print('Criteria frozen; MAIN88 isolated snapshot created; existing unrelated working changes preserved.')
