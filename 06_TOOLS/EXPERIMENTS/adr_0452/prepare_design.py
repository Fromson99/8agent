from pathlib import Path
import json,hashlib,shutil
R=Path.cwd();D=R/'04_EXPERIMENTS/ADR/ADR-0452-gemini-expression-routing-probe';A=D/'artifacts';P=R/'04_EXPERIMENTS/ADR/ADR-0449-multi-entry-catalogue-navigation/artifacts/dataset'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
if (A/'design-before-snapshot.json').exists():raise ValueError('already designed')
for name in ['sources.json','documents.json','terms.json','edges.json','references.json','structure-units.json']:shutil.copyfile(P/name,(A/'dataset'/name) if (A/'dataset').exists() else ((A/'dataset').mkdir() or A/'dataset'/name))
docs=read(A/'dataset/documents.json');sources=read(A/'dataset/sources.json')
for d in docs:
 if d['id']=='customer':d['name']='모의 ESG채권 인증평가 기준'
for s in sources:
 s['document_name']=next(d['name'] for d in docs if d['id']==s['document_id'])
 if s['document_id']=='customer':s['text']='제1조 이 모의 ESG채권 인증평가 기준은 시험용 문서이다. 실제 법령이나 협회 기준이 아니다.'
 if s['document_id']=='vendor':s['text']+=' ESG채권이라는 표현은 본문에만 있고 이 문서의 이름에는 없다.'
 if s['document_id'] in ('customer','vendor'):
  s['blocks'][0]['text']=s['text'];s['text_sha256']=s['source_artifact_sha256']=hashlib.sha256(s['text'].encode()).hexdigest()
write(A/'dataset/documents.json',docs);write(A/'dataset/sources.json',sources)
allids=sorted(d['id'] for d in docs);internal=sorted(d['id'] for d in docs if d['document_category']=='internal');external=sorted(d['id'] for d in docs if d['document_category']=='external');kofia=['customer','vendor'];hr=['approval','leave','pay'];gold=[];cases=[]
def add(cid,q,kind,ids=None,**kw):
 cases.append({'id':cid,'question':q,'scope_document_ids':allids,'dataset':'synthetic','initial_mappings':kw.pop('initial_mappings',[]),'followup':kw.pop('followup',None)})
 gold.append({'id':cid,'kind':kind,'expected_document_ids':sorted(ids or []),'required_source_ids':[],'required_points':[],**kw})
add('internal','내규들은 어떤 게 있어?','catalogue',internal)
add('external-abbreviation','외규 어떤 게 있지?','catalogue',external)
add('unseen-internal','내문 어떤 게 있지?','catalogue',internal)
add('parenthetical','내문(내부문서) 목록 알려줘','catalogue',internal)
add('kofia','kofia에 있는 문서 알려줘','catalogue',kofia)
add('kofia-abbreviation','금투협에 있는 문서들 알려줘','catalogue',kofia)
add('uppercase','KOFIA에 있는 문서 목록 보여줘','catalogue',kofia)
add('title-only','외부 문서 중 kofia 폴더에서 ESG채권 관련 문서들을 문서명으로 찾아줘','catalogue',['customer'])
add('unknown-alias','뽀문 어떤 게 있지?','clarify')
add('all-documents','우리 DB에 있는 전체 문서 목록 알려줘','catalogue',allids)
add('tree','kofia 폴더를 트리로 보여줘','tree',kofia,required_folder_paths=['external/kofia/규정'])
add('nested-folder','internal/hr 폴더 안에 있는 문서 목록 알려줘','catalogue',hr)
add('user-document-map','보규 문서의 목차 알려줘','outline',['pay'],initial_mappings=[{'expression':'보규','target':{'type':'document','identity':'pay'}}])
add('mapping-proposal','내문을 내부문서에 연결하는 표현 매핑을 제안해줘','mapping',internal,followup='내문 어떤 게 있지?',expected_mapping={'expression':'내문','target':{'type':'folder','identity':'internal'}})
for cid,q,initial in [('multi-entry-alias','상여와 휴직이 겹치면 직원에게 어떤 지급 기준, 기준일과 예외 승인 요건이 적용돼?',[{'expression':'상여','target':{'type':'term','identity':'performance'}}]),('multi-entry-literal','성과급과 휴직이 겹치면 직원에게 어떤 지급 기준, 기준일과 예외 승인 요건이 적용돼?',[])]:
 add(cid,q,'content',initial_mappings=initial,required_source_ids=['article:pay-base','article:pay-date','article:leave-exception','article:approval-rule'],required_points=['평가점수 80점 이상인 직원에게 성과급 지급','지급 기준일은 매년 12월 31일','휴직 중인 직원은 원칙적으로 성과급 미지급','업무상 재해로 휴직한 직원은 예외적으로 지급 대상에 포함 가능','예외에는 인사위원회의 서면 승인 필요','협력업체/고객 혜택/과거 사례집을 직원의 현행 지급 근거로 사용하지 않음'])
write(A/'dataset/product-cases.json',cases);write(A/'grading/gold.json',{'cases':gold,'visible_to_product':False,'version':'synthetic-routing-gold-v1'});write(A/'source-inventory.json',{'sources':sources,'data_status':'EXAMPLE','article_count':len(sources),'document_count':len(docs)})
m=read(D/'실험/manifest.json');prior=R/'04_EXPERIMENTS/ADR/ADR-0450-typed-keyword-navigation/실험/manifest.json';p=read(prior)
m['lineage']['parents'].append({'experiment_id':p['experiment_id'],'arm_id':'typed','relation':'retests','manifest_path':str(prior.relative_to(R)),'manifest_sha256':sha(prior)})
m['lineage']['source_branch_paths'][p['experiment_id']+'/typed']=p['lineage']['branch_path']
h='Compare unchanged typed routing ADR0450 to unchanged first-call expression mapping ADR0451 with the same synthetic questions, Gemini model and budgets; aliases should improve scope/intent success without widening or evidence regressions.'
m['lineage']['hypothesis_delta']=h;m['design'].update(hypothesis=h,primary_metric='Exact task success across 16 cases, with 14 metadata/mapping and 2 grounded content cases reported separately',success_criteria='mapped >=14/16; no baseline-only regressions; unknown-alias clarification; no document scope leaks or invalid source citations; each turn <=14 calls and 180s controller budget',failure_criteria='Any criterion missed; API/schema/engine failures count as task failure, not successful clarification',criteria_frozen_before_run=True,implementation_scope='Retest frozen products unchanged, explicit research Gemini provider only',controls='Identical synthetic corpus, whole questions, scope, registered terms, template coordinates, provider model, temperature0 and limits; arm execution alternates per case; only mapped runtime consumes new mapping ledger',protocol_notes='in-sample probe with familiar task patterns; one repetition; no tuning or rerun after seeing model results',limits={'max_calls':14,'max_actions':56,'wall_seconds':180,'active_chars':18000,'context_chars':60000},arm_order='case index even baseline then mapped; odd mapped then baseline',mapping_review_policy='for mapping-proposal, simulated user approves the first returned candidate without reading gold; reopen a fresh conversation using same ledger then ask the fixed follow-up')
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':[p['experiment_id']+'/typed'],'changes':'Frozen ADR0450 typed routing unchanged','controls':'Same Gemini transport and corpus; preloaded entity mappings exist in both ledgers but baseline does not consume this unsupported feature'},{'id':'mapped','role':'candidate','derived_from':['ADR-0451-experiment-v1/mapped'],'changes':'Frozen ADR0451 first-call interpretation and entity mapping unchanged','controls':'Same budgets and source contracts; no code/prompt fixes in this run'}]
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'discovered','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'read','kind':'filter','parent_stage_ids':['discovered']},{'stage_id':'adopted','kind':'select','parent_stage_ids':['read']},{'stage_id':'present','kind':'present','parent_stage_ids':['adopted']}]
m['design']['retrieval_stage_plan']={'schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','stages_by_arm':{a:stages for a in ['baseline','mapped']}}
m['runs']=[{'id':'run-001','purpose':'probe','parent_run_id':None,'arm_ids':['baseline','mapped'],'selection_rule':'All frozen 16 cases once; mapping case includes fixed approval and follow-up','status':'planned','artifact_path':str((A/'results.json').relative_to(R)),'sha256':'PENDING'}]
m['llm_policy']['llm_calls']=[{'role':'structured_navigation','class':'product','model':'gemini-3.1-flash-lite','repetitions':1,'temperature':0,'max_calls_per_turn':14},{'role':'content_judge','class':'offline_evaluator','model':'gemini-3.1-flash-lite','repetitions':1,'temperature':0,'case_count':2}]
m['dataset'].update(name='Synthetic typed folder and expression routing',version='expression-routing-452-v1',frozen_source=str((A/'dataset/product-cases.json').relative_to(R)),sha256=sha(A/'dataset/product-cases.json'),legal_version_checked=True,reference_version_checked=True,version_note='All documents and facts synthetic EXAMPLE; no real legal or internal data exported')
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None);m['retrieval_accounting']['stage_ledger']={'mode':'measured','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':'run-001','artifact_path':str((A/'retrieval-ledger.json').relative_to(R)),'sha256':'PENDING','not_applicable_reason':None}
write(D/'실험/manifest.json',m);write(A/'design-before-snapshot.json',m)
write(A/'authorization.json',{'user_request':'Gemini로 실험해봐','model':'gemini-3.1-flash-lite','client':'lawrag.research.experiment_client.GeminiExperimentClient','source_scope':'synthetic only','real_internal_data':False,'public_source_export_policy':'inspected; existing law fingerprint authorization is for different source/backend, so not extended; no real source is exported','main_wiring':'unchanged'})
print('design frozen before snapshot: 16 synthetic questions, 2 arms')
