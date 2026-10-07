from pathlib import Path
import json,hashlib,copy,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0519-root-selection-protected-relations';P=R/'04_EXPERIMENTS/ADR/ADR-0518-five-source-replacement-loop';C=R/'02_BACKEND/lawrag/research/candidates/adr_0519/selection'
def read(p):return json.loads(p.read_text())
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
m=read(A/'실험/manifest.json');old=read(P/'실험/manifest.json')
for name in ['product-cases.json','gold-cases.json']: (A/name).write_bytes((P/name).read_bytes())
# Exact public reference cache is immutable and kept at parent path rather than copied.
for key in ['llm_policy','dataset','gemma_binding','retrieval_accounting']:m[key]=copy.deepcopy(old[key])
m['dataset']['frozen_source']=str((A/'product-cases.json').relative_to(R));m['gemma_binding']['live_calls']=0;m['gemma_binding']['live_calls_planned']=61
m['lineage']['hypothesis_delta']='Only direct search roots may be selected/rejected. All already-acquired linked originals are protected regardless of root decisions; dual-role nodes remain protected. No count target.'
d={'hypothesis':'Prevent relation-derived original deletion by separating direct-root selection from a deterministic protected relation union; recover90/90 while avoiding individual pruning of linked originals.',
 'primary_metric':'Canonical original retention; protected-source loss; counts of selected roots and protected linked sources separately',
 'success_criteria':'90/90 required originals retained across61; every acquired relation-derived source preserved (loss0), no source/scope/witness corruption; errors0;composed p95<=240s. No count threshold.',
 'failure_criteria':'Any protected-source loss, missing required original, source mutation or model error. On model/protocol failure retain all acquired sources and mark DEGRADED; never count degraded mode as successful model selection.',
 'criteria_frozen_before_run':True,
 'arms':[{'id':'baseline','role':'baseline','derived_from':['ADR-0518-experiment-v1/selection'],'changes':'Exact completed518 final outputs (run002), replayed; quality72/90.','controls':'Same fixed61 public questions,513 acquired originals,public scope,Gemma model/provider.'},{'id':'selection','role':'candidate','derived_from':['baseline'],'changes':'One model call selects from direct search roots only, with320char verbatim original slices and query paths; deterministic union retains every acquired anchor-linked original including ambiguous links with explicit unconfirmed status. Dual-role and unclassified origins protected. Error retains pool and marks degraded. Final source list distinguishes selected roots/protected connections.','controls':'No gold or parent selection results in product input; unchanged original pool and raw reference paths; no new corpus-wide retrieval.'}],
 'retrieval_stage_plan':{'schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','stages_by_arm':{
 'baseline':[{'stage_id':'acquired','kind':'source','parent_stage_ids':[]},{'stage_id':'final_pool','kind':'present','parent_stage_ids':['acquired']}],
 'selection':[{'stage_id':'acquired','kind':'source','parent_stage_ids':[]},{'stage_id':'root_candidates','kind':'filter','parent_stage_ids':['acquired']},{'stage_id':'root_selection','kind':'select','parent_stage_ids':['root_candidates']},{'stage_id':'protected','kind':'filter','parent_stage_ids':['acquired']},{'stage_id':'protected_union','kind':'union','parent_stage_ids':['root_selection','protected']},{'stage_id':'final_pool','kind':'present','parent_stage_ids':['protected_union']}]}},
 'code_isolation':{'schema_version':'adr-code-isolation-v1','mode':'candidate_snapshot','reason':None,'production_paths_modified_before_decision':False,'runtime_import_allowed':False,'production_registry_registered':False,'main_wiring_unchanged':True,'candidates':[]}}
m['design']=d
m['runs']=[{'id':'run-001','purpose':'primary','parent_run_id':None,'arm_ids':['baseline','selection'],'selection_rule':'All fixed61 once;3 isolated workers;one Gemma call/case,no provider fallback or retries.240s parent recorded retrieval+new root selection deadline. Retain pool on error with explicit degraded status.','status':'planned','artifact_path':str((A/'artifacts/run-001/results.json').relative_to(R)),'sha256':'PENDING','case_ids':old['runs'][-1]['case_ids']}]
m['results']={'status':'planned','by_arm':{},'comparisons':[],'usage':{},'latency':{},'error_taxonomy':[]}
for k in ['before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity']:m['retrieval_accounting'][k]={}
m['retrieval_accounting']['stage_ledger'].update(summary_run_id='run-001',artifact_path=str((A/'artifacts/retrieval-stage-ledger.json').relative_to(R)),sha256='PENDING')
pol=read(P/'artifacts/gemma-policy.json');pol.update(adr_id=m['adr_id'],experiment_id=m['experiment_id'],run_id='run-001',max_output_tokens=2304)
pol['authorization'].update(scope='Public61 root-only selection; max61 Gemma calls; protect all acquired relation sources; no count target; no MAIN change',latest_steering='연결관계 조항은 제거 대상에서 제외하고 전부 보존; 첫 시작점만 원문 사용 여부 판단')
write(A/'artifacts/gemma-policy.json',pol);ph=sha(A/'artifacts/gemma-policy.json')
m['llm_policy']['llm_calls']=[{'role':'direct_root_selection','class':'product','model':'google/gemma-4-31b-it','repeats':1}]
m['llm_policy']['experiment_override'].update(policy_path=str((A/'artifacts/gemma-policy.json').relative_to(R)),policy_sha256=ph)
m['gemma_binding'].update(policy_path=str((A/'artifacts/gemma-policy.json').relative_to(R)),policy_sha256=ph)
g=read(P/'artifacts/export-rebinding.json');g.update(experiment_policy_path=str((A/'artifacts/gemma-policy.json').relative_to(R)),policy_sha256=ph,parent_rebinding_sha256=sha(P/'artifacts/export-rebinding.json'));write(A/'artifacts/export-rebinding.json',g)
write(A/'실험/manifest.json',m)
(A/'PLAN.md').write_text('# 사전 설계: 시작점 선별과 연결 원문 보호\n\n'+json.dumps(d,ensure_ascii=False,indent=2)+'\n\n보호는 기존513에서 회수 완료한 범위 전체에 적용한다. 채택한 시작점 연결만으로 다시 자르지 않는다. 연결 경로가 없는 직접 시작점만 제외 가능하다. 연결 여부 미확인/출처 미분류는 보수적으로 보존하고 정식 적용 관계로 승격하지 않는다. 회수 풀 밖 경로는 별도 미회수 수로 기록한다. 전체 코퍼스의 모든 연결을 새로 읽었다고 주장하지 않는다. 모델 오류가 보존 실패를 만들지 않도록 전체 입력을 유지하되 성공률·지연·비용에서 오류를 숨기지 않는다. 최종 답변은 생성하지 않으며 최종 출처 목록과 원문 관계만 준비한다.\n')
print('Design frozen before candidate:root-only,all acquired connections protected.')
