from pathlib import Path
import json,hashlib,shutil,subprocess,sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0817-risk-main76-live-e2e';D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(R/pointer['manifest_path']);C=R/release['code_root'];G=R/release['data_path'];assert pointer['generation']==76
put(D/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'manifest':release})
registered=read(R/'01_DATA/GOLDEN/risk_cm/v1/questions.json')['cases'];cases=[]
for short,ident in [('risk-027','RISK-CM-027'),('risk-038','RISK-CM-038'),('risk-104','RISK-CM-104')]:
 c=next(c for c in registered if c['id']==ident);cases.append({'id':short,'registered_id':ident,'question':c['question'],'api_type':'WORKFLOW_RUN','workflow_id':'risk_team_compare_workflow','stage':'question_only','origin':'01_DATA/GOLDEN/risk_cm/v1/questions.json'})
prior=R/'04_EXPERIMENTS/ADR/ADR-0802-multi-issue-investigation-retry/artifacts/design/criteria.json';q=read(prior)['known_observation']['question'];cases.append({'id':'known-liquidity','registered_id':None,'question':q,'api_type':'LEGAL_AGENT','stage':'known_prior_failure','origin':str(prior.relative_to(R))})
put(D/'cases.json',cases)
criteria={'hypothesis':'Unchanged MAIN76 can execute real registered Risk questions through actual service bootstrap, both child RAG investigations, basis/compare and final response. Observe each boundary and independently audit returned claims against pinned originals. No synthetic substitute or legal-gold certification.',
 'selection':'Three original registered Risk questions027(definitions),038(multiple conditions/internal approval),104(liquidity source), plus exact previously failing liquidity comparison; selected before calls, each once in that order.',
 'success':['All4 cases produce a durable terminal response through selected actual service with use_llm=true and real approved Qwen calls','Both internal/external child results and their real statuses recorded; substantive completion separately requires adopted sources and resolved required issues','Every displayed citation matches current allowed original source spans; no guessed missing internal facts/version','Return/status/repeated completed request identical without additional model calls','Full raw provider input/output, usage, stage/error and code/data/model bindings preserved'],
 'semantic_rubric':{'risk-027':'Explain actual distinction with relevant financial-investment scope; distinguish missing internal source from external rule, do not substitute special corporate regimes without scope evidence.','risk-038':'Preserve A+ rating,1200 limit,1000 existing exposure,300 new resale-purpose loan and all question clauses. Cite actual internal rule or explicitly identify unavailable source; arithmetic alone cannot establish authority.','risk-104':'Find governing liquidity-ratio provision/definition and actual available internal source; distinguish missing rule from insufficient user facts.','known-liquidity':'Show actual internal/external investigation and source-backed differences or explicit missing/version block. Zero comparison rows is not completed substantive reconciliation.'},
 'grading':'Assistant post-run source-bound audit, no model judge, no approved gold/accuracy percentage; original105 question_only unchanged. Never inject these criteria or expected source coordinates into product.',
 'limits':{'per_case_model_attempts':40,'per_case_wall_seconds':1800,'per_case_outer_timeout':1920,'total_physical_model_calls':160,'serial_processes':True,'max_peak_rss_kib':12*1024*1024},
 'retries':'Only existing gateway/stage owners under unchanged profile; no new request/allowance after failure. One scheduled call per case; duplicate only for terminal states; no adaptive query rewrites or extra runs.',
 'quality_certified':False,'in_sample':True,'decision_eligible':False,'main_wiring':'unchanged','genos':'not accessed',
 'controls':{'release':pointer,'profile_sha256':sha(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json'),'policy_sha256':sha(C/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),'authorization_sha256':sha(C/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json'),'data_manifest_sha256':sha(G/'manifest.json')},
 'instrumentation':'Actual workspace service.application selects active release; only its existing transport physical send is delegated to common ExperimentClient for immutable exact wire/provider records. Original authorization, prompts, schemas, runtime budgets and outputs are retained.'}
put(D/'criteria.json',criteria)
# Offline frozen inventory only. It is never read by the product runner.
db=sqlite3.connect('file:'+str(G/'store.sqlite')+'?mode=ro',uri=True);docs=[];references=[]
for did,name,j in db.execute('select document_id,name,json from document'):
 meta=json.loads(j).get('document_metadata',{});docs.append({'document_id':did,'name':name,'category':meta.get('source_category'),'team':meta.get('team')})
 if did not in ('c9b5b42627710637','683c4222e1cd54cc'):continue
 units={str(u):json.loads(j) for u,j in db.execute('select unit_id,json from source_unit where document_id=?',(did,))}
 for uid,v in units.items():
  if v.get('coordinate_key') not in ('body:제3-8조','body:제3-24조의4'):continue
  ids={uid};pending=[uid]
  while pending:
   parent=pending.pop()
   for child,row in units.items():
    if str(row.get('parent'))==parent and child not in ids:ids.add(child);pending.append(child)
  blocks=[{'block_id':b,'unit_id':u,'text':t,'sha256':hashlib.sha256(t.encode()).hexdigest()} for b,u,t in db.execute('select block_id,unit_id,text from source_block where document_id=?',(did,)) if str(u) in ids]
  references.append({'document_id':did,'unit_id':uid,'coordinate_key':v['coordinate_key'],'title':v.get('title'),'blocks':blocks})
put(D/'offline-source-audit.json',{'documents':docs,'reference_provisions':references,'binding':criteria['controls']['data_manifest_sha256'],'product_input':False,'expert_approved_gold':False});db.close()
m=read(A/'실험/manifest.json');m.update(in_sample=True,decision_eligible=False);m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Actual end-to-end execution and source-grounded completeness, not legal accuracy certification',success_criteria=criteria['success'],failure_criteria=['Missing final/child stage, unsupported citation/meaning, budget/connection/schema failure; preserve all outcomes'],criteria_frozen_before_run=True)
m['design']['arms'][0].update(changes='Historical MAIN76 technical qualification only; no live baseline rerun',controls=['No product/data changes'])
m['design']['arms'][1].update(changes='Exact selected MAIN76, real original questions and common audited physical transport only',controls=['Same selected code/profile/data/authorization/model'])
m['runs'][0].update(arm_ids=['observed'],selection_rule=criteria['selection'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[{'role':'actual_workflow_and_child_rag','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':'selected runtime value; no override'}]
m['dataset'].update(name='risk_cm-original-three-and-known-liquidity',version='20261016-main76-live-v1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'),legal_version_checked=False,reference_version_checked=False)
plans=[{'stage_id':'native_read','kind':'source','parent_stage_ids':[]},{'stage_id':'child_adopted','kind':'select','parent_stage_ids':['native_read']},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['child_adopted']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={'observed':plans};m['retrieval_accounting'].update(changed=False,not_applicable_reason='Unchanged MAIN76 retrieval; observation ledger covers exact native reads, child adoption and final citations, not every intermediate search menu or golden recall.');m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None);put(A/'실험/manifest.json',m)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','observed','--experiment-id',m['experiment_id'],'--arm-id','observed','--run-id','run-001']
for n in release['files']:cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
S=R/'02_BACKEND/lawrag/research/candidates/adr_0817/observed/snapshot'
for n,h in release['files'].items():assert sha(C/n)==h;shutil.copyfile(C/n,S/n)
print('Prepared4 real questions, original data/active code unchanged, offline source audit separated')
