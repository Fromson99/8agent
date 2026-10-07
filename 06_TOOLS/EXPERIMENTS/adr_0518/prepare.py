from pathlib import Path
import json,hashlib,copy,datetime
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0518-five-source-replacement-loop'
P=R/'04_EXPERIMENTS/ADR/ADR-0517-bounded-provenance-protocol'
def read(p):return json.loads(p.read_text())
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
m=read(A/'실험/manifest.json');old=read(P/'실험/manifest.json')
for f in ['product-cases.json','gold-cases.json']: (A/f).write_bytes((P/f).read_bytes())
for k in ['llm_policy','dataset','gemma_binding','retrieval_accounting']:m[k]=copy.deepcopy(old[k])
m['dataset']['frozen_source']=str((A/'product-cases.json').relative_to(R))
m['gemma_binding']['live_calls']=0
m['lineage']['hypothesis_delta']='Target about5, permit justified distinct-issue/dependency overflow; replace instead of append. Show exact witness relations among selected originals.'
plan={
 'hypothesis':'Question-focused original slices, verified reference witnesses and replacement reduce redundant evidence toward5 while allowing necessary overflow and improving retention over ADR0517.',
 'primary_metric':'Canonical source retention paired with final source count; replacement gains/losses; relation witness integrity',
 'success_criteria':'gold_final>=85/90 (baseline80), mean final_count<=6, final_count<=12 technical per-call guard with unresolved overflow explicit; zero schema/scope/witness errors; composed p95<=240s. Target5 is not a hard semantic cap. No generalization or promotion claim.',
 'failure_criteria':'Any scope/witness corruption or unmet above criterion; missing evidence remains unresolved; no all-pool fallback.',
 'criteria_frozen_before_run':True,
 'retrieval_stage_plan':{'schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','stages_by_arm':{}},
 'code_isolation':{'schema_version':'adr-code-isolation-v1','mode':'candidate_snapshot','reason':None,'production_paths_modified_before_decision':False,'runtime_import_allowed':False,'production_registry_registered':False,'main_wiring_unchanged':True,'candidates':[]},
 'arms':[{'id':'baseline','role':'baseline','derived_from':['ADR-0517-experiment-v1/selection'],'changes':'Exact completed517 selected results reused; no baseline model rerun.','controls':'Same61 public questions and513 acquired pool; same Gemma/provider; no gold in product.'}, {'id':'selection','role':'candidate','derived_from':['baseline'],'changes':'Initial metadata+160char original slices; target5 with justified overflow<=12. Up to2 replacement rounds: active2400char originals, 16 targeted challenger600char excerpts, exact reference witnesses. Record final source list and literal relation witnesses. No answer generation.','controls':'Same source pool/generation, question plans, public scope, original packets and scope authorization.'}]
}
for arm in ['baseline','selection']:
 ids=['acquired','final_pool'] if arm=='baseline' else ['acquired','triage','replace_1','replace_2','final_pool']
 plan['retrieval_stage_plan']['stages_by_arm'][arm]=[{'stage_id':v,'kind':'source' if i==0 else 'present' if v=='final_pool' else 'select','parent_stage_ids':[] if i==0 else [ids[i-1]]} for i,v in enumerate(ids)]
m['design']=plan
m['runs']=[{'id':'run-001','purpose':'primary','parent_run_id':None,'arm_ids':['baseline','selection'],'selection_rule':'All fixed61 once;3 isolated workers;up to3 model calls/case;no retries/fallback;composed240s deadline. Baseline exact historical517 outputs.','status':'planned','artifact_path':str((A/'artifacts/run-001/results.json').relative_to(R)),'sha256':'PENDING','case_ids':old['runs'][0]['case_ids']}]
m['results']={'status':'planned','by_arm':{},'comparisons':[],'usage':{},'latency':{},'error_taxonomy':[]}
for k in ['before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity']:m['retrieval_accounting'][k]={}
m['retrieval_accounting']['stage_ledger'].update(artifact_path=str((A/'artifacts/retrieval-stage-ledger.json').relative_to(R)),sha256='PENDING')
policy=read(P/'artifacts/gemma-policy.json');policy.update(adr_id=m['adr_id'],experiment_id=m['experiment_id'])
policy['authorization'].update(scope='Public61 adaptive target5 source replacement and witness inspection;max183 Gemma calls;public originals only;no MAIN changes',latest_steering='한번 수정해보고 실험해봐; 실제 많은 조항이 필요하면 딱5개 유지 불필요; 최종 결과에 준용 등 조문 관계 표시')
write(A/'artifacts/gemma-policy.json',policy)
m['llm_policy']['llm_calls'][0].update(role='adaptive_source_replacement',repeats=3)
m['llm_policy']['experiment_override'].update(policy_path=str((A/'artifacts/gemma-policy.json').relative_to(R)),policy_sha256=sha(A/'artifacts/gemma-policy.json'))
grant=read(P/'artifacts/export-rebinding.json');grant.update(experiment_policy_path=str((A/'artifacts/gemma-policy.json').relative_to(R)),policy_sha256=sha(A/'artifacts/gemma-policy.json'),parent_rebinding_sha256=sha(P/'artifacts/export-rebinding.json'))
write(A/'artifacts/export-rebinding.json',grant)
write(A/'실험/manifest.json',m)
(A/'PLAN.md').write_text('# 사전 동결 설계\n\n사용자 후속 정정: 5개는 목표이며 복잡한 질문은 필요한 조문을 더 유지한다. 최초 immutable claim의 fixed-five 표현은 선점 당시 범위이고, 아래 설계를 첫 호출 전에 확정한다.\n\n'+json.dumps(plan,ensure_ascii=False,indent=2)+'\n\n183회 이하,3worker,모든61문항,공개 원문만. 기준답변·과거 누락 목록을 모델에 넣지 않는다. API429는 실패로 분리하며 재시도하지 않는다. 기존 전체회수와 실제 최종답변을 새로 실행하지 않는다. 관계 원문 확인은 적용성 판단과 다르다.\n')
print('Design prepared before candidate creation;61 cases,183 max calls.')
