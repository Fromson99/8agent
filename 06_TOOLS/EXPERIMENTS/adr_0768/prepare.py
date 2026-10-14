"""Independent public qualification; preserve rejected parent and exact code."""
from pathlib import Path
import json,hashlib,sqlite3,subprocess,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0768-bounded-wiki-public-qualification';D=A/'artifacts/design';P=R/'04_EXPERIMENTS/ADR/ADR-0765-bounded-wiki-recall'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
base=read(P/'artifacts/design/baseline.json');assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer_sha256']
for p,h in base['manifest']['files'].items():assert sha(R/p)==h,'Concurrent working change: '+p
put(D/'baseline.json',base)
criteria=read(P/'artifacts/design/criteria.json')
criteria['scope']='Unchanged completed0765 bounded memory code. New prospective public permission case paired with selected MAIN53; prior failed comparison and legal-effect label error retained, not rescored.'
criteria['required'].update(candidate_supported=1,matched_memory_selected=1,no_match_normal_discovery=0)
criteria['execution']['order']=[['public-memory-04','baseline'],['public-memory-04','integrated']]
criteria['limits']='One new public paired question; not overall CM accuracy or speed. Inherit exact-code source/ACL/state and hit/miss contracts from completed0765. Parent baseline 422 and candidate legal-effect-as-duty label remain failed; neither treated as success. User 2026-10-07 permits semantic-detail failures to remain follow-up work. Explicit permission polarity in new source still required.'
criteria['prior_final_documentation']='0765 final validation found unresolved scaffold fields in question Markdown after completion. Preserve completed manifest/question bytes; exact real requests/outputs are available in verified raw archive. New qualification supplies complete question documentation and must pass its own final validator.'
put(D/'criteria.json',criteria)
sid='article:7b6b6a3a08025d3a37498fa0';cid='public-memory-04'
question='상인이 자신의 영업범위 안에서 다른 사람을 위해 일을 했을 때 상당한 보수를 요구할 수 있는지, 상법의 상인의 보수청구권 규정 자체를 확인해 주세요.'
db=sqlite3.connect((R/base['manifest']['data_path']/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
source=json.loads(db.execute('SELECT json FROM source WHERE id=?',(sid,)).fetchone()[0]);db.close()
assert source['document_id'] in read(R/base['manifest']['code_root']/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids']
assert sid not in {x['id'] for x in read(P/'artifacts/design/gold.json')['cases']}
assert sid not in set(read(R/'04_EXPERIMENTS/ADR/ADR-0761-scoped-title-public-qualification/artifacts/design/excluded-source-ids.json'))
case={'case_id':cid,'question':question,'memory_expected':True,'role':'prospectively-authored-public-holdout','arm_ids':['baseline','integrated']}
put(D/'dataset.json',{'cases':[case],'source_generation':base['manifest']['data_path'],'gold_product_visible':False})
put(D/'gold.json',{'product_visible':False,'cases':[{'case_id':cid,**{k:source[k] for k in ('id','document_id','unit_id','document_name','heading','text','text_sha256','source_artifact_sha256')}}]})
put(D/'memory-seeds.json',{'seeds':[{'seed_id':cid,'question':'영업범위 내 타인을 위한 행위의 상당 보수 청구','topic':'상인의 보수청구권','source_id':sid,'provenance':'SYNTHETIC_PUBLIC_MEMORY_FIXTURE_NOT_ACTUAL_USER_HISTORY'}],'answer_in_seed':False,'scope':'Public synthetic history; no internal CM'})
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['scope'],primary_metric='Independent paired native completion with bounded history reuse and original authority',success_criteria=criteria['required'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,repeats=1)
for arm in m['design']['arms']:
 arm.update(changes='Selected MAIN53 unchanged' if arm['id']=='baseline' else criteria['scope'],controls='Same public sources, one public fixture, native API and fixed model/budgets')
 if arm['id']=='integrated':arm['derived_from']=['ADR-0765-experiment-v1/integrated']
 else:arm.update(derived_from=[],source_binding={'path':str((D/'baseline.json').relative_to(R)),'sha256':sha(D/'baseline.json'),'source_arm':'ADR-0761-experiment-v1/integrated','replica_of_selected_release':True})
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
m['dataset'].update(name='Fresh public remuneration permission question',version='v1',frozen_source=str((D/'dataset.json').relative_to(R)),sha256=sha(D/'dataset.json'),legal_version_checked=True,reference_version_checked=True)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['runs'][0].update(selection_rule='Exactly two requests, baseline then candidate; no adaptive retries',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['design']['retrieval_stage_plan']=read(P/'실험/manifest.json')['design']['retrieval_stage_plan']
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json.gz').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
q=A/'실험/질문-001-public-memory-04.md'
headings=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
texts=['ADR0768/run-001; 신규 공개 쌍, exact provider records와 시각은 artifacts/run-001.',question,'동결 gold.json의 상법 제61조. 제품 runner는 읽지 않는다. 명시된 보수 청구 허용과 영업범위 내 타인을 위한 행위라는 조건을 보존해야 한다.','### 회수·탈락 단계 원장 — run·arm별\n\nNative API의 실제 후보·원문·단계 목록은 retrieval-ledger.json.gz 및 provider 기록. 기준답변은 선택 후 결합.','Qwen3.8 Parasail FP8 none no fallback; 매 물리 호출의 request/response/usage를 case/provider 아래 저장하고 검증된 raw archive로 보존.','같은 audited client 사용, 위키 별도 호출0이 기준. 모든 repair 포함 총40 이하.','채점 모델 호출 없음. 저장 응답과 동결 원문의 별도 대조. 결과는 semantic-review.json에 기록.','실행 전에 고정. 실행 후 아래 결과 표와 result.json에 성공/실패 모두 보존.']
q.write_text('# '+cid+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(headings,texts),1))+'\n')
m['questions']=[{'number':1,'case_id':cid,'file':q.name,'sha256':sha(q)}];put(A/'실험/manifest.json',m)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','integrated','--experiment-id',m['experiment_id'],'--arm-id','integrated','--run-id','run-001']
initial=set(base['manifest']['files'])|{'02_BACKEND/lawrag/research/experiment_client.py'}
for name in sorted(initial):cmd+=['--source',name]
subprocess.run(cmd,cwd=R,check=True,stdout=subprocess.DEVNULL)
parent=R/'02_BACKEND/lawrag/research/candidates/adr_0765/integrated';pcm=read(parent/'candidate.json');rev=pcm['revisions'][-1];src=parent/'revisions'/rev['revision_id']/'snapshot';child=R/'02_BACKEND/lawrag/research/candidates/adr_0768/integrated'
for row in pcm['files']:
 name=row['target_path'];target=child/'snapshot'/name;target.parent.mkdir(exist_ok=True,parents=True);shutil.copy2(src/name,target)
 if name not in initial:subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(child),'--target',name,'--upstream-state','present' if (R/name).is_file() else 'absent'],check=True,stdout=subprocess.DEVNULL)
required=['candidate_supported','matched_memory_selected','no_match_normal_discovery','no_auxiliary_model_calls','one_bounded_lookup','all_successful_citations_verified','gold_presented','public_scope_only','actual_binding_valid','state_and_content_preserved','public_diagnostics_not_leaked','new_contracts_all_pass','no_new_regression','same_code_to_release','physical_call_accounting','main_unchanged','frozen_files_unchanged','actual_model_provider_binding']
parent_result=P/'artifacts/run-001/result.json';assert all(read(parent_result)['checks'][k] for k in required)
put(D/'parent-inheritance.json',{'parent':'ADR-0765-experiment-v1/integrated','manifest_sha256':sha(parent/'candidate.json'),'revision':rev['revision_id'],'serving_code_changes':0,'files':{x['target_path']:sha(src/x['target_path']) for x in pcm['files']},'result':{'path':str(parent_result.relative_to(R)),'sha256':sha(parent_result)},'required_parent_checks':required,'excluded_parent_gates':{'baseline_supported':'Preserved baseline 422, not candidate failure; a new complete pair is required here','source_meaning_preserved':'Preserved legal-effect-as-duty label error, not changed or certified. Follow-up semantic issue under user 2026-10-07 policy; fresh explicit permission still checked.'}})
for name,v in [('preview-authorization.json',{'purpose':'integration_preview','quality_gate_override':False}),('preview-validation.json',{'structural_checks_passed':True})]:put(D/name,v)
shutil.copy2(P/'artifacts/contract-result.json',A/'artifacts/contract-result.json')
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(child)],check=True,stdout=subprocess.DEVNULL)
print('New public pair fixed; identical completed code and contract evidence inherited')
