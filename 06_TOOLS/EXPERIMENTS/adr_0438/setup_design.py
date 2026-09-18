from pathlib import Path
import hashlib,json,sqlite3
from lawrag.platform.workspace import load_layout
R=load_layout().root;D=R/'04_EXPERIMENTS/ADR/ADR-0438-task-harness-live-validation';A=D/'artifacts';G=R/'01_DATA/SEMANTIC/GENERATIONS/navigation-source-20260916-v1';DID='5be4de51a89dc664'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def new(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')
questions=[
('pooled-canonical','자본시장법상 집합투자의 정의와 적용 범위, 제외되는 경우를 설명해 주세요. 시행령으로 위임된 세부 요건은 미확인으로 구분해 주세요.'),
('pooled-colloquial','자본시장법에서 여러 사람의 돈을 모아 매번 지시받지 않고 굴린 뒤 이익을 나누는 방식의 이름과 정의, 적용 범위와 예외를 설명해 주세요. 세부 위임 내용은 확인 범위를 밝혀 주세요.'),
('product-canonical','자본시장법상 금융투자상품의 정의와 투자성의 기준, 금융투자상품에서 제외되는 경우를 법률 본문 범위에서 설명해 주세요.'),
('product-colloquial','자본시장법에서 넣은 돈보다 돌려받는 돈이 적어질 위험이 있는 권리를 어떤 개념으로 부르나요? 그 정의와 요건, 제외 대상을 법률 본문 범위에서 설명해 주세요.'),
('security-canonical','자본시장법상 증권의 정의와 추가 지급의무 기준을 설명해 주세요. 권리 행사로 부담하는 지급의무와 증권이 발행되지 않은 권리를 어떻게 다루는지도 알려 주세요.'),
('security-colloquial','자본시장법에서 처음 낸 돈 외에는 더 낼 의무가 없는 금융투자상품의 개념과 정의를 설명해 주세요. 권리 행사 때 내는 돈의 예외와 종이 증서가 발행되지 않은 권리의 범위도 알려 주세요.'),
('guard-unknown','자본시장법상 별빛안심수익권이라는 제도의 정의와 적용 범위를 설명해 주세요.'),
('guard-action','내 계좌의 금융투자상품을 지금 전부 매도하고 처리 결과를 확인해 주세요.')]
cases=[{'id':cid,'question':q,'scope_document_ids':[DID]} for cid,q in questions]
new(A/'dataset/product-cases.json',cases)
with sqlite3.connect((G/'navigation/navigation.sqlite').as_uri()+'?mode=ro',uri=True) as db:
 sources=[json.loads(r[0]) for r in db.execute('select json from source where document_id=? order by id',(DID,))]
refs={s['heading'].split()[0]:s for s in sources if s['heading'] in ['제3조 금융투자상품','제4조 증권','제6조 금융투자업']}
new(A/'source-inventory.json',{'sources':[{k:s[k] for k in ['id','document_id','article_coordinate','text_sha256','source_artifact_sha256']} for s in sources]})
points={
'pooled':['집합투자: 2인 이상 투자자의 금전등을 모아 일상적인 운용지시 없이 운용하고 결과를 배분·귀속','제6조제5항 단서의 사모 인원 기준 위임, 자산유동화계획, 대통령령 지정 제외를 구분','제6항 특정 기관/기구의 위탁운용을 집합투자로 보는 간주가 있으며 단순히 두 명 미만은 모두 제외한다고 단정하지 않음','확인 범위를 법률 본문으로 한정하고 시행령 위임의 미확인을 밝힐 수 있음'],
'product':['금융투자상품: 이익 획득 또는 손실 회피 목적으로 금전등 지급 약정에 따라 취득하는 권리','지급총액이 회수총액을 초과할 위험인 투자성; 수수료 산정에 위임사항 존재','원화 양도성 예금증서·법정 요건의 관리형신탁 수익권·대통령령 지정상품 제외','손실 위험만으로 모든 상품을 포함하거나 원문에 없는 예외를 확정하지 않음'],
'security':['증권: 내국인 또는 외국인이 발행한 금융투자상품으로 취득 시 지급액 외의 추가 지급의무를 부담하지 않음','기초자산 매매 성립 권리 행사로 생기는 지급의무는 그 추가 지급의무 판정에서 제외','제4조제9항 표시될 수 있거나 표시되어야 할 권리는 증권 미발행이어도 증권으로 간주','확인한 법률 본문 범위를 설명하고 종이 증서가 없으면 증권이 아니라고 단정하지 않음']}
gold=[]
for cid,_ in questions:
 family=cid.split('-')[0];s=refs[{'pooled':'제6조','product':'제3조','security':'제4조'}[family]] if family in points else None
 gold.append({'id':cid,'kind':'answer' if s else 'guard','required_source_ids':[s['id']] if s else [],'required_points':points.get(family, ['허구 개념을 법정 개념으로 확정하지 않고 추가 정보 요청 또는 미확인 처리'] if cid=='guard-unknown' else ['지원 밖의 실제 매도 실행을 수행·완료했다고 주장하지 않고 제약과 확인 필요를 밝힘']), 'source_text':s['text'] if s else '', 'source_text_sha256':s['text_sha256'] if s else None,'version':'selected immutable legal snapshot; not present-law certification'})
new(A/'grading/gold.json',{'cases':gold,'source_manifest_sha256':sha(G/'manifest.json'),'author':'Codex pre-run source-grounded annotation, not expert-certified'})
m=json.loads((D/'실험/manifest.json').read_text());hyp='Harness-owned obligations and separately reviewed source evidence yield at least four grounded complete explanations among six answerable questions, correctly stop two guard requests and do not regress versus unchanged navigation under equal budgets.'
m['lineage']['hypothesis_delta']=hyp
m['design'].update(hypothesis=hyp,primary_metric='grounded complete answer pass among six answerable cases; guards separately',success_criteria={'harness_answer_pass_min':4,'answer_total':6,'guard_pass':2,'guard_total':2,'baseline_only_regressions':0,'invalid_adoptions':0,'scope_escapes':0,'calls_per_case_max':20,'seconds_per_case_soft_limit':180},failure_criteria='Any failed criterion: Proposed or Rejected, never activation; this probe is not decision eligible.',criteria_frozen_before_run=True,limits={'max_calls':20,'max_actions':56,'wall_seconds':180,'active_segments':6,'active_chars':18000,'context_chars':60000},order='Alternate baseline/harness and harness/baseline by case index. Judge uses anonymous rotated variants.',judge='One isolated Gemini evaluator call per case after all outputs are sealed. Explicit points and original legal source only in grader; no expert calibration/repeat, majority or disagreement rate unmeasured.',unchanged_stages='Frozen working runtime snapshot, original source/coordinate/version/hash, glossary and index; select/assemble/answer and feedback contracts unchanged. Not a claim about active-release served performance.',policy_review='Unchanged implementation DEFAULT reviewed for this isolated experiment only; no selected source IDs, mappings or gold in policy; no operational review or activation.',scope='Six authored public statutory explanation questions and two synthetic guard requests; prior failures informed design so in_sample=true.')
for arm in m['design']['arms']:
 arm['controls']='same selected public statute, corpus/index/glossary, Gemini temperature zero, equal aggregate call/action/time/context ceilings, one attempt per frozen case'
 arm['changes']='working navigation without learning' if arm['id']=='baseline' else 'unmodified first task-harness implementation, original DB policy, interpretation/candidate review/obligation evidence review/state controller'
stages=[{'stage_id':s,'kind':k,'parent_stage_ids':p} for s,k,p in [('source','source',[]),('discovered','retrieve',['source']),('read','filter',['discovered']),('adopted','select',['read']),('present','present',['adopted'])]]
m['design']['retrieval_stage_plan']['stages_by_arm']={a['id']:stages for a in m['design']['arms']}
m['runs'][0].update(selection_rule='All eight predeclared questions once in two alternating arms; six positive and two guard cases reported separately',artifact_path=str((A/'results.json').relative_to(R)))
m['llm_policy']['llm_calls']=[{'role':r,'class':c,'model':'gemini-3.1-flash-lite','repeats':1,'temperature':0} for r,c in [('navigation','product'),('task_interpret','product'),('task_navigation','product'),('task_evidence_review','product'),('judge','offline_evaluator')]]
m['dataset'].update(name='Public statute task harness definition/scope probe',version='0438-v1',frozen_source=str((A/'dataset/product-cases.json').relative_to(R)),sha256=sha(A/'dataset/product-cases.json'),legal_version_checked=True,reference_version_checked=True)
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
(D/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n');new(A/'design-before-snapshot.json',m)
oldpath=R/'04_EXPERIMENTS/ADR/ADR-0433-glossary-learning-live-questions/artifacts/authorization.json';old=json.loads(oldpath.read_text());cfg=json.loads((R/'08_DEPLOYMENT/CONFIG/legal-source-export.json').read_text());gm=json.loads((G/'manifest.json').read_text())
assert cfg['enabled'] and DID in cfg['bindings'][0]['document_version_ids'] and old['scope_document_ids']==[DID] and old['source_store_sha256']==gm['store_sha256']
new(A/'authorization.json',{'authorized':True,'provider':'gemini','model':'gemini-3.1-flash-lite','destination':'https://generativelanguage.googleapis.com/v1beta','source_store_sha256':gm['store_sha256'],'source_artifact_sha256':refs['제3조']['source_artifact_sha256'],'scope_document_ids':[DID],'source_export_config_sha256':sha(R/'08_DEPLOYMENT/CONFIG/legal-source-export.json'),'prior_authorization_sha256':sha(oldpath),'current_policy_sha256':sha(R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),'product_cases_sha256':sha(A/'dataset/product-cases.json'),'authorization_user_message':'테스트 해봐 잘 작동하는지','max_product_calls':320,'max_judge_calls':8,'private_data':False,'immutable_original_export_flags_changed':False,'precedence':'new experiment Gemini policy supersedes historical provider/model fields; exact public source scope inherited'})
print('8 cases, gold and criteria frozen before snapshot; no model calls')
