from pathlib import Path
import json,hashlib
from lawrag.core.structure import pipeline,recipe_template,recipe_regions,viewer,recipe_basic
from lawrag.core.structure.model import Block
R=Path.cwd();D=R/'04_EXPERIMENTS/ADR/ADR-0449-multi-entry-catalogue-navigation';A=D/'artifacts'
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
docs=[('pay','모의 직원 보수 내규','internal'),('leave','모의 직원 휴직 내규','internal'),('vendor','모의 협력업체 성과급 기준','external'),('customer','모의 고객 혜택 규정','external'),('approval','모의 인사 승인 절차','internal'),('unknown','모의 특별 규정',None),('travel','모의 출장 내규','internal'),('archive','모의 과거 사례집','external'),('safety','모의 안전 지침','internal'),('privacy','모의 정보 관리 내규','internal')]
texts=[('pay-base','pay','제1조 성과급은 평가점수 80점 이상인 직원에게 지급한다.',['performance']),('pay-date','pay','제2조 성과급 지급 기준일은 매년 12월 31일이다.',['performance']),('leave-exception','leave','제1조 휴직 중인 직원에게는 성과급을 지급하지 않는다. 다만 업무상 재해로 인한 휴직자는 모의 인사 승인 절차 제1조의 승인을 받으면 지급 대상에 포함한다.',['leave']),('leave-form','leave','제2조 휴직 신청은 인사팀에 신청서를 제출하여 처리한다.',['leave']),('vendor-pay','vendor','제1조 협력업체 성과급은 납품 실적에 따라 지급하며 회사 직원에게 적용하지 않는다.',['performance']),('customer-point','customer','제1조 고객 혜택으로 적립금을 지급한다. 직원 보수에는 적용하지 않는다.',['benefit']),('approval-rule','approval','제1조 업무상 재해로 휴직한 직원의 지급 예외는 인사위원회의 서면 승인을 받아야 한다.',['approval']),('special','unknown','제1조 특별 규정의 문서 분류는 아직 확인되지 않았다.',['special']),('travel-rule','travel','제1조 출장 여비는 영수증을 확인하여 정산한다.',['travel']),('archived-pay','archive','제1조 이 사례집의 성과급 설명은 과거 사례 소개이며 현재 지급 기준으로 적용하지 않는다.',['performance']),('safety-rule','safety','제1조 안전 교육은 매년 실시한다.',['safety']),('privacy-rule','privacy','제1조 개인정보는 승인된 담당자만 열람한다.',['privacy'])]
rows=[];units={};receipts=[]
for sid,did,text,terms in texts:
 doc=next(d for d in docs if d[0]==did);blocks=[Block(0,text)];template=recipe_basic.default_template();template=recipe_template.compile_recipe(template['heading_rules'],{k:{} for k in template['heading_rules']});recipe={'tag':recipe_regions.VERSION,'version':1,'source_block_count':1,'regions':[{'start_block':0,'end_block':1,'template_id':'base','label':'synthetic','reason':'frozen example grammar'}],'templates':{'base':template}};result=recipe_regions.build(pipeline,blocks,recipe);flat=[];viewer._flat_tree(result.tree,flat);out=units.setdefault(did,[]);off=len(out)
 for n in flat:
  n['id']+=off
  if n['parent'] is not None:n['parent']+=off
  n['block']+=off;n['span']=[x+off for x in n['span']]
 out+=flat;n=next(n for n in flat if n['family']=='kr_article');h=hashlib.sha256(text.encode()).hexdigest()
 rows.append({'id':'article:'+sid,'document_id':did,'document_name':doc[1],'unit_id':str(n['id']),'block_id':str(off),'heading':text.split(' ')[0],'text':text,'text_sha256':h,'source_artifact_sha256':h,'blocks':[{'block_id':str(off),'text':text}],'article_coordinate':{'doc_id':did,'node':n['id']},'terms':terms,'data_status':'EXAMPLE'})
 receipts.append({'source_id':sid,'recipe':recipe})
for d,nodes in units.items():viewer.annotate_coordinate_scopes(nodes,document_kind='law')
terms=[('performance','성과급'),('leave','휴직'),('incentive','인센티브'),('approval','승인'),('benefit','혜택'),('special','특별'),('travel','출장'),('safety','안전'),('privacy','개인정보')]
edges=[{'id':'incentive-performance','source':'incentive','target':'performance','code':'synthetic-related'}]
refs=[{'id':'ref-leave-approval','source_id':'article:leave-exception','target_source_ids':['article:approval-rule'],'locator':'모의 인사 승인 절차 제1조','resolution':'RESOLVED'}]
write(A/'dataset/sources.json',rows);write(A/'dataset/structure-units.json',units);write(A/'dataset/structure-receipts.json',receipts);write(A/'dataset/documents.json',[{'id':d,'name':name,'document_category':kind} for d,name,kind in docs]);write(A/'dataset/terms.json',[{'id':k,'label':label} for k,label in terms]);write(A/'dataset/edges.json',edges);write(A/'dataset/references.json',refs)
allids=[d[0] for d in docs]
cases=[('two-roots','직원 성과급 지급 점수 기준과 휴직자의 지급 제외·예외 및 승인 요건을 함께 알려줘.','answer',['article:pay-base','article:leave-exception','article:approval-rule'],['평가점수80점 이상','휴직자는 원칙적으로 미지급','업무상 재해 휴직 예외','인사위원회 서면 승인']),('chain-and-root','직원 인센티브 지급 점수 기준과 휴직자 예외·승인 요건을 함께 설명해줘.','answer',['article:pay-base','article:leave-exception','article:approval-rule'],['평가점수80점 이상','휴직자는 원칙적으로 미지급','업무상 재해 휴직 예외','인사위원회 서면 승인']),('overlap','직원 성과급의 평가점수 기준과 지급 기준일을 알려줘.','answer',['article:pay-base','article:pay-date'],['평가점수80점 이상','12월31일']),('catalog-all','우리 DB에 있는 문서 전체 목록과 개수를 알려줘.','catalogue',[],[]),('catalog-internal','우리 내규들은 어떤 게 있어? 전체 목록과 개수를 알려줘.','catalogue',[],[]),('catalog-unknown','우리 내규들은 어떤 게 있어? 분류가 없으면 확인되지 않았다고 알려줘.','catalogue',[],[])]
product=[];gold=[]
for cid,q,kind,required,points in cases:
 scope=['unknown'] if cid=='catalog-unknown' else allids
 product.append({'id':cid,'question':q,'scope_document_ids':scope,'dataset':'synthetic'})
 expected=[{'id':d,'name':name} for d,name,category in docs if d in scope and (cid=='catalog-all' or category=='internal')]
 gold.append({'id':cid,'kind':kind,'required_source_ids':required,'required_points':points,'source_text':'\n'.join(s['text'] for s in rows if s['id'] in required),'expected_documents':expected if kind=='catalogue' else [],'expected_unknown':1 if cid in ['catalog-internal','catalog-unknown'] else 0})
write(A/'dataset/product-cases.json',product);write(A/'grading/gold.json',{'cases':gold});write(A/'authorization.json',{'scope':'synthetic only','model':'gemini-3.1-flash-lite','private_or_actual_corpus_sent':False,'max_product_calls':384,'max_judge_calls':6})
m=json.loads((D/'실험/manifest.json').read_text());h='All matched entry paths contribute to a deduplicated candidate pool before evidence selection; pending candidate review prevents early completion. Typed scoped catalogue preserves unknown category.'
m['lineage']['hypothesis_delta']=h;m['design'].update(hypothesis=h,primary_metric='Required multi-article adoption plus grounded answer; exact filtered catalogue with unknown classification',success_criteria={'candidate_pass_min':6,'total':6,'scope_escape_max':0,'invalid_quote_max':0,'early_finish_with_pending_max':0,'contracts_required':True},failure_criteria='Any failed criterion prevents acceptance/MAIN',criteria_frozen_before_run=True,limits={'max_calls':32,'max_actions':64,'wall_seconds':240,'active_chars':18000,'context_chars':60000},implementation_scope='Registered term/structure seeds; one-hop registered relation expansion; candidate union+provenance+pagination; per-candidate read/judge or metadata dismissal; reference followup; explicit category catalogue with unknown, no name heuristics.',controls='Same12 synthetic articles/10docs/questions/model/32calls across arms; parent0448 exact code; candidate only changes specified controller.',order='alternate arms and anonymous X/Y judge position; one run, known synthetic developer questions; not holdout')
for a in m['design']['arms']:a.update(changes='unchanged ADR0448/inherited' if a['id']=='baseline' else h,controls='same synthetic source generation/model/budget')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None)
stages=json.loads((R/'04_EXPERIMENTS/ADR/ADR-0447-template-bound-tool-handles/artifacts/pre-call-manifest.json').read_text())['design']['retrieval_stage_plan']['stages_by_arm']['bound'];m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ['baseline','multi']}
m['dataset'].update(name='Multi-entry and scoped catalogue synthetic6',version='synthetic-449-v1',frozen_source=str((A/'dataset/product-cases.json').relative_to(R)),sha256=sha(A/'dataset/product-cases.json'),legal_version_checked=True,reference_version_checked=True,version_note='Synthetic rules, not actual legal advice')
m['runs'][0].update(selection_rule='All6 frozen cases, once per arm; no post-result retries',artifact_path=str((A/'results.json').relative_to(R)))
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None);m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
write(D/'실험/manifest.json',m);write(A/'design-before-snapshot.json',m);print('frozen design:12sources,10docs,6cases')
