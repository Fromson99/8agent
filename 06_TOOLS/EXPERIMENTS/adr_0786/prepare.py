from pathlib import Path
import hashlib,json,sqlite3,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0786-risk-compare-qwen-live-probe';D=A/'artifacts/design';D.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text())
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
g=R/'01_DATA/TERM_RELEASES/risk-compare-docx-20261015-r1-index/serving/baseline/generation';gm=read(g/'manifest.json')
q='유동성비율 관련 외부규정은 무엇이고 내부 규정에는 어떻게 되어 있나?'
documents={}
with sqlite3.connect('file:'+str(g/'store.sqlite')+'?mode=ro',uri=True) as db:
 for did,name,h,raw in db.execute('SELECT document_id,name,source_artifact_sha256,json FROM document'):
  v=json.loads(raw);md=v.get('document_metadata',{})
  if (md.get('source_category')=='external' and md.get('team')=='risk_team') or did=='deb0727589aad3cc':
   documents[did]={'name':name,'category':md['source_category'],'source_sha256':h}
assert len(documents)==360
grant={'schema_version':'research-workflow-export-v1','authorized':True,'adr_id':'ADR-0786',
 'authorization_text':'Agent.md에서 외부 전송관련내용 빼버려 보내도 됨',
 'authorization_context':'User requested actual Qwen experiment of this liquidity comparison after disclosure of OpenRouter/Parasail and internal DOCX transmission',
 'model':'qwen/qwen3.8-27b','provider':'openrouter','upstream_provider':'Parasail','endpoint':'https://openrouter.ai/api/v1',
 'policy_sha256':sha(R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),'question':q,
 'generation_path':str(g.relative_to(R)),'generation_id':gm['generation_id'],'generation_manifest_sha256':sha(g/'manifest.json'),
 'store_sha256':gm['store_sha256'],'export_allowed_in_source':False,'document_ids':sorted(documents),'documents':documents,
 'scope_note':'All 359 registered risk_team external documents plus the one provided internal DOCX; no target-article injection; current internal gold document absent',
 'principal':{'user_id':'adr0786-research','team_id':'risk_team'},'session_id':'adr0786-liquidity',
 'request_id':'adr0786-liquidity-qwen-run001','as_of':None,'max_model_calls':40,'max_tool_calls':1024,'wall_seconds':1800,
 'main_changed':False,'immutable_source_flags_changed':False,'reference_answer_allowed_in_product':False}
put(D/'authorization.json',grant)
put(D/'request.json',{'question':'대사: '+q,'session_id':grant['session_id'],'request_id':grant['request_id'],'use_llm':True,'document_ids':grant['document_ids']})
gold={'visibility':'offline evaluator only','source':'user correction in current conversation',
 'external':{'document_id':'c9b5b42627710637','title':'금융투자업규정','article':'제3-24조의4','paragraph':2,'unit_id':'788','source_id':'article:c3af79efc692a91026430460','block_ids':['817','818','819'],'present':True},
 'internal':{'title':'위험관리기준시행세칙','article':'제6-4조','paragraph':1,'present':False,'reason':'No corresponding registered document in generation or RAW/internal; provided group rules are a different document'},
 'limitations':['Current applicability not certified','Known case, not unused holdout','Missing internal target prevents complete reconciliation; distinguish corpus absence from retrieval/model miss']}
put(D/'gold-offline.json',gold)
criteria={'question_count':1,'hypothesis':'Actual Qwen can execute the unchanged comparison stages; required evidence, partial output and failures are measured without answer injection',
 'primary':'Both user-nominated paragraphs actually read and correctly reconciled from exact sources',
 'secondary':['Actual provider/model/routing verified','Original question only, gold kept offline','External gold article/paragraph recall','Missing internal document reported instead of invented','Exact quote and source hashes preserved','No unauthorized document or credential in payload','Same model/tool/deadline ledger'],
 'baseline':'Parent ADR0785 unchanged workflow with external binding; expected blocked and zero model calls',
 'candidate':'Same business/retrieval/report code, research-only explicit external authorization hook and audited ExperimentClient',
 'runs':['run-001'],'repeats':1,'adaptive_reruns':False,'limits':{'models':40,'tools':1024,'seconds':1800},
 'failure_policy':'Existing stage correction once and transport retry owner; do not relax quote/schema/version checks; preserve partial/failed result. Any follow-up fix after observed result requires a new ADR.',
 'success_impossible_if_internal_target_remains_missing':True,'main_changed':False}
put(D/'criteria.json',criteria)
put(D/'baseline.json',{'code_root':read(R/'04_EXPERIMENTS/ADR/ADR-0785-risk-team-compare-workflow/artifacts/design/freeze.json')['code_root'],
 'main_pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'source_adr':'ADR-0785-experiment-v1/workflow'})
m=read(A/'실험/manifest.json');m['design'].update(hypothesis=criteria['hypothesis'],primary_metric=criteria['primary'],success_criteria=criteria['secondary'],failure_criteria=criteria['failure_policy'],criteria_frozen_before_run=True)
m['dataset'].update(name='Known user liquidity comparison; actual registered corpus',version='liquidity-user-correction-20261015',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'),legal_version_checked=False,reference_version_checked=True)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
for arm in m['design']['arms']:
 arm['changes']=criteria['baseline'] if arm['id']=='baseline' else criteria['candidate'];arm['controls']='Same source generation, original question, unchanged business prompts/logic; known-case single run, no MAIN change'
m['design']['retrieval_stage_plan']={'schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','stages_by_arm':{arm:[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'retrieve','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['retrieve']}] for arm in ('baseline','qwen')}}
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',not_applicable_reason=None)
m['llm_policy']['llm_calls']=[{'role':'workflow decisions','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0}]
put(A/'실험/manifest.json',m)
files=read(R/'04_EXPERIMENTS/ADR/ADR-0785-risk-team-compare-workflow/artifacts/design/freeze.json')['serving_files']
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','qwen','--experiment-id',m['experiment_id'],'--arm-id','qwen','--run-id','run-001']
for n in sorted(files):cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
print('Prepared: 331 pinned candidate files, 360 authorized documents, offline-only target evidence')
