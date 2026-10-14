from pathlib import Path
import hashlib,json,subprocess,shutil,sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0767-polished-narrative-qualification';D=A/'artifacts/design'
P=R/'02_BACKEND/lawrag/research/candidates/adr_0766/narrative';C=R/'02_BACKEND/lawrag/research/candidates/adr_0767/polished';S=C/'snapshot'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
base=read(R/'04_EXPERIMENTS/ADR/ADR-0766-rich-grounded-answer-stream/artifacts/design/baseline.json')
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer_sha256'];put(D/'baseline.json',base)
criteria={'scope':'Inherit complete766 native paragraph streaming/claim preservation; improve prose structure and prohibit additional legal restrictions, including invented reporting deadlines. Keep retrieval, assessment schema, original data, caches, budgets and model/provider unchanged.',
 'required':{'candidate_primary_supported':2,'known_regression_supported':1,'structural_source_acl_state_stream_errors':0,'new_material_unsupported_duty_deadline_prohibition':0,'readable_direct_answer_and_subheadings':True,'new_contract_regressions':0,'extra_model_calls_max':2,'composition_seconds_max':180},
 'execution':{'order':[['R01','polished'],['H01','baseline'],['H01','polished'],['H02','polished'],['H02','baseline']],'repeats':1,'adaptive_reruns':False,'model_calls_per_request_max':40},
 'semantic_gate':'Offline original-source check: first answer directly answers requested scope, preserves explicit permissions/duties/deadlines/exceptions, no invented restriction. Minor wording/semantic misses recorded separately per user; severe unsupported effects block selection.',
 'sample':'Two new primary article roots outside exposure scan6216 roots, one known766B regression. Novelty relative to retained evaluated artifacts, not pretraining or full legal domain.',
 'performance':'One final writing call expected. Compare all failures and supported pairs separately, no artificial percent latency claim; native total budgets unchanged. No evidence-free padding.',
 'authorization':'User asked to make final answers polished and rich and to verify streaming. Local integration and concrete GENOS handoff preparation within scope; no email sending.',
 'rollback':'Original MAIN53 release retained; presentation guard structured restores original composition; GENOS applied code backup retained.'}
put(D/'criteria.json',criteria)
selection=[('H01','article:13d8cb2aa8962ecb8158382d','저장된 증권의 발행 및 공시 등에 관한 규정 제6-7조를 기준으로, 전자공시시스템 장애로 전자문서를 제출할 수 없을 때 제출인이 해야 할 일과 시스템 복구 후 감독원장이 해야 할 일을 구분해 설명해 주세요. 그 조항의 제출 방식·첨부 파일·복구 후 처리 내용만 다루고 다른 조항은 조사하지 말아 주세요.'),
 ('H02','article:10871d56c653a8ee4c9e4387','저장된 금융투자회사의 영업 및 업무에 관한 규정 제2-13조를 기준으로, 전문투자자 지정 절차, 효력기간, 재신청이 가능한 시점, 지정 거부와 말소 사유를 설명해 주세요. 신청서류의 세부 목록과 시행령의 자격요건은 추가 조사하지 말아 주세요.')]
ex=set(read(D/'excluded-source-ids.json'));assert all(sid not in ex for _,sid,_ in selection)
db=sqlite3.connect((R/base['manifest']['data_path']/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
allowed=set(read(R/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids']);cases=[];gold=[]
for cid,sid,q in selection:
    s=json.loads(db.execute('SELECT json FROM source WHERE id=?',(sid,)).fetchone()[0]);assert s['document_id'] in allowed
    cases.append({'case_id':cid,'question':q,'role':'out_of_sample_primary','arm_ids':['baseline','polished']})
    gold.append({'case_id':cid,'source_id':sid,**{k:s[k] for k in ('document_id','unit_id','document_name','heading','text','text_sha256','source_artifact_sha256')}})
known=next(c for c in read(R/'04_EXPERIMENTS/ADR/ADR-0766-rich-grounded-answer-stream/artifacts/design/public-probes.json')['cases'] if c['case_id']=='B')
cases.append({'case_id':'R01','question':known['question'],'role':'known_regression','arm_ids':['polished']})
gold.append({'case_id':'R01','source_id':known['sources'][0]['source_id'],**{k:known['sources'][0][k] for k in ('document_id','unit_id','document_name','heading','text','text_sha256','source_artifact_sha256')}});db.close()
put(D/'dataset.json',{'cases':cases,'product_gold':False,'source_generation':base['manifest']['data_path']});put(D/'gold.json',{'product_visible':False,'cases':gold,'version':'Pinned stored originals; not current-law advice'})
put(D/'selection-audit.json',{'excluded_roots':len(ex),'exposure_scan_sha256':sha(D/'exposure-scan.json'),'primary_roots':[s for _,s,_ in selection],'primary_overlap':False,'known':['R01'],'selection_before_results':True})
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['scope'],primary_metric='Grounded useful final prose and preserved native publication/streaming',success_criteria=criteria['required'],failure_criteria='Any required gate failure, keep MAIN53; failures never overwritten',criteria_frozen_before_run=True,repeats=1)
m['design']['evaluation_roles']={c['case_id']:c['role'] for c in cases};m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
for arm in m['design']['arms']:
    arm.update(changes='Selected MAIN53 unchanged' if arm['id']=='baseline' else criteria['scope'],controls='Same public65 source generation, Qwen3.8 Parasail FP8 none, full40call/1800sec native budgets and original scope.')
    if arm['id']=='baseline':arm.update(derived_from=[],source_binding={'path':str((D/'baseline.json').relative_to(R)),'sha256':sha(D/'baseline.json'),'source_arm':'ADR-0761-experiment-v1/integrated','replica_of_selected_release':True})
    else:arm['derived_from']=['ADR-0766-experiment-v1/narrative']
m['dataset'].update(name='Two distinct primary roots and known overstatement regression',version='v1',frozen_source=str((D/'dataset.json').relative_to(R)),sha256=sha(D/'dataset.json'),legal_version_checked=True,reference_version_checked=True)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['runs'][0].update(selection_rule='Exact5 full API requests in frozen order, no adaptive repeats',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
stages=[{'stage_id':'catalogue','kind':'source','parent_stage_ids':[]},{'stage_id':'recall','kind':'retrieve','parent_stage_ids':['catalogue']},{'stage_id':'acquired','kind':'select','parent_stage_ids':['recall']},{'stage_id':'presented','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','polished')};m['retrieval_accounting'].update(changed=False,not_applicable_reason=None);m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json.gz').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
parent=read(P/'candidate.json');cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','polished','--experiment-id',m['experiment_id'],'--arm-id','polished','--run-id','run-001']
for row in parent['files']:
    if (R/row['target_path']).is_file():cmd+=['--source',row['target_path']]
subprocess.run(cmd,cwd=R,check=True,stdout=subprocess.DEVNULL)
for row in parent['files']:
    name=row['target_path'];dest=S/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(P/'revisions/rev-003/snapshot'/name,dest)
    if not (R/name).exists():subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',name,'--upstream-state','absent'],check=True,stdout=subprocess.DEVNULL)
p=S/'02_BACKEND/semantic_runtime/legal_agent/narrative_answer.py';s=p.read_text();needle='JSON 객체 paragraphs만 출력한다.'
extra='''문서의 가독성을 위해 첫 문단은 **핵심 답변**으로 시작하여 질문에 대한 결론을 1~3문장으로 제시한다. 이어지는 문단에는 질문에 맞는 짧은 굵은 소제목을 붙인다. 복합 질문은 주체·요건·절차·예외를 목록이나 비교표로 풀어 설명한다. 단순 질문은 결론과 근거 설명만으로 충분하다. 사용자가 짧게 요청하면 소제목 없이 간결하게 답한다.
원문보다 강한 표현을 추가하지 않는다. 보고의무가 있다는 이유만으로 원문에 없는 보고 기한, 지연 금지, 즉시 이행, 위반 효과를 만들지 않는다. '지체 없이' 등의 문구는 그 문구가 실제로 적용되는 주체와 행동에만 쓴다. 다른 항·다른 주체의 기한을 옮기지 않는다. 일반적인 실무 조언·추측을 법적 의무처럼 추가하지 않는다.
첫 결론 뒤에는 구체적인 내용을 설명하되 마지막에 같은 항목을 모두 다시 요약하지 않는다. 원문에 근거한 절차의 순서, 주체별 역할, 허용과 의무의 차이를 명확하게 풀어 쓰는 것이 풍부한 답변이다.
'''
assert needle in s;s=s.replace(needle,extra+needle);p.write_text(s)
put(D/'parent-inheritance.json',{'parent':'ADR-0766-experiment-v1/narrative','revision':'rev-003','candidate_manifest_sha256':sha(P/'candidate.json'),'changes':['Generalized final prose instructions only; native streaming/grounding code unchanged'],'known_failure':'Report delay prohibition not present in its source; retained in766B.'})
print('Frozen2 independent primary roots+known regression; inherited native stream; candidate prose instructions refined.')
