from pathlib import Path
import json,hashlib,sqlite3
R=Path('/home/jin/8-AGENT');D=R/'04_EXPERIMENTS/ADR/ADR-0444-cm-schema-navigation-real-probe';A=D/'artifacts';G=R/'01_DATA/SEMANTIC/GENERATIONS/navigation-source-20260916-v1';OLD=R/'04_EXPERIMENTS/ADR/ADR-0425-cm-glossary-validation/artifacts';IDS=[f'cm-{i:03}' for i in [1,11,21,31,41,51]]
def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def new(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')
auth=read(OLD/'authorization.json');gm=read(G/'manifest.json');suitepath=R/'01_DATA/review/cm_core_e2e_v2.json';suite=read(suitepath);assert sha(suitepath)=='d3c707caa114dec379201c2ba9d2177b0c6bc17ceb4ae9394df1397e9dbfccb1';assert auth['authorized'] and auth['model']=='gemini-3.1-flash-lite' and sha(G/'store.sqlite')==auth['source_store_sha256']==gm['store_sha256']
full=read(OLD/'dataset/product-cases.json');cases=[c for c in full if c['id'] in IDS];assert [c['id'] for c in cases]==IDS
assert all(sorted(c['scope_document_ids'])==sorted(gm['scope']['document_version_ids']) for c in cases)
suitecases={c['id']:c for c in suite['cases']};assert all(c['question']==suitecases[c['id']]['question'] for c in cases)
new(A/'dataset/product-cases.json',cases)
nav=G/gm['navigation']['path'];db=sqlite3.connect((nav/'navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True);sources={r[0]:json.loads(r[1]) for r in db.execute('select id,json from source')};db.close()
gold=[c for c in read(OLD/'dataset/gold.json')['cases'] if c['id'] in IDS]
for c in gold:
 assert c['reference_answer']==suitecases[c['id']]['reference_answer']
 for e in c['expected_articles']+c['required_companions']:
  actual=sources[e['source_id']];assert actual['text']==e['source_text'];assert actual['document_id'] in cases[0]['scope_document_ids']
new(A/'grading/gold.json',{'cases':gold,'original_reference_answers_unchanged':True,'source_rebinding':'Unique exact IDs and original source bytes verified against selected generation; no product gold access'})
rows=[]
for s in sources.values():
 v={k:s[k] for k in ['id','document_id','article_coordinate','text_sha256','source_artifact_sha256']}
 try:v['canonical_coordinate']={'doc_id':s['document_id'],'node':int(s['article_coordinate']['node'])};v['coordinate_status']='STRUCTURED_SOURCE_ROOT'
 except (ValueError,TypeError):v['canonical_coordinate']=None;v['coordinate_status']='UNSTRUCTURED_BLOCK_NO_ARTICLE_COORDINATE'
 rows.append(v)
new(A/'source-inventory.json',{'rows':rows,'source_total':len(rows),'canonical_total':sum(v['canonical_coordinate'] is not None for v in rows),'unstructured_total':sum(v['canonical_coordinate'] is None for v in rows),'note':'Canonical source-unit root IDs include non-article headings; unstructured blocks remain searchable but are separately counted outside article-coordinate ledger.'})
new(A/'authorization.json',{'authorized':True,'provider':auth['provider'],'model':auth['model'],'destination':auth['destination'],'current_user_request':'우리 실제 cm 데이터가지고 해볼래?','prior_explicit_authorization_path':str((OLD/'authorization.json').relative_to(R)),'prior_authorization_sha256':sha(OLD/'authorization.json'),'original_approval':auth['approval_user_message'],'payload_scope':auth['payload_scope'],'source_store_sha256':gm['store_sha256'],'scope_document_ids':gm['scope']['document_version_ids'],'suite_sha256':sha(suitepath),'product_cases_sha256':sha(A/'dataset/product-cases.json'),'case_ids':IDS,'max_product_calls':144,'max_judge_calls':6,'unrelated_private_data_allowed':False,'immutable_original_export_flags_changed':False})
m=read(D/'실험/manifest.json');hyp='The unchanged ADR0442 schema navigation candidate can produce grounded complete answers for at least four of six actual CM questions over the full selected159-document scope without regressions against selected-release navigation.'
m['lineage']['hypothesis_delta']=hyp;m['design'].update(hypothesis=hyp,primary_metric='grounded complete CM task success; semantic judgment AND required-source adoption, exact quote, original result contract and FINISH',success_criteria={'candidate_pass_min':4,'total':6,'baseline_only_regressions_max':0,'invalid_quotes_max':0,'scope_escapes_max':0,'model_calls_per_case_max':12,'controller_seconds_soft_max':180},failure_criteria='Any failed criterion keeps Proposed/Rejected; no quality certification or MAIN activation',criteria_frozen_before_run=True,limits={'max_calls':12,'max_actions':40,'wall_seconds':180,'active_segments':6,'active_chars':18000,'context_chars':60000},order='Alternate baseline/schema by case; rotate anonymous evaluator positions',judge='One Gemini evaluator per case after product seal. Only this case question/reference and required+selected source texts. Tool execution is measured from receipts, not guessed by evaluator. Errors/unavailable evaluator reported separately. No question-specific criterion in shared judge system.',implementation_scope='Unchanged ADR0442 schema_navigation bytes and full selected release; source ownership mapper and explicit retrieval adapter connect original Store/TermIndex/Glossary/ReverseMatcher. No algorithm/prompt repairs despite known failures.',scope='Fixed evenly spaced CM IDs001,011,021,031,041,051 from51, chosen before outcomes;159documents same for all. No gold-driven scope filters or sources injected into product.',controls='Same source/glossary/index generation, selected release, provider/model/budget, questions. Existing issue/ID/completion failures intentionally retained.',source_binding={'generation_path':str(G.relative_to(R)),'manifest_sha256':sha(G/'manifest.json'),'store_sha256':gm['store_sha256'],'suite_path':str(suitepath.relative_to(R)),'suite_sha256':sha(suitepath)})
for arm in m['design']['arms']:
 arm['derived_from']=['ADR-0432-experiment-v1/navigation'] if arm['id']=='baseline' else ['ADR-0442-experiment-v1/schema']
 arm['changes']='unchanged active-release navigation-loop-v1' if arm['id']=='baseline' else 'unchanged ADR0442 schema tools plus real source owner mapping and explicit serving adapter'
 arm['controls']='same original159documents and glossary; same actual CM question and12-call/180-second controller budget'
stages=[{'stage_id':s,'kind':k,'parent_stage_ids':p} for s,k,p in [('source','source',[]),('discovered','retrieve',['source']),('read','filter',['discovered']),('adopted','select',['read']),('present','present',['adopted'])]]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ['baseline','schema']};m['runs'][0].update(selection_rule='Fixed CM indices1,11,21,31,41,51 once per arm; all159documents remain in search scope',artifact_path=str((A/'results.json').relative_to(R)))
m['llm_policy']['llm_calls']=[{'role':r,'class':c,'model':'gemini-3.1-flash-lite','repeats':1,'temperature':0} for r,c in [('navigation','product'),('judge','offline_evaluator')]];m['dataset'].update(name='Actual CM6 systematic sample from frozen CM51',version='cm_core_e2e_v2+selected-source-20260916',frozen_source=str((A/'dataset/product-cases.json').relative_to(R)),sha256=sha(A/'dataset/product-cases.json'),legal_version_checked=True,reference_version_checked=True,version_note='Selected snapshot exact identity/text checked; no present-law certification; historical work reference preserved')
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None);m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
(D/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n');new(A/'design-before-snapshot.json',m)
print('Frozen6actual CM questions;159documents;',len(rows),'sources;',len([v for v in rows if v['canonical_coordinate'] is None]),'unstructured roots counted separately')
