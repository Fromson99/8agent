from pathlib import Path
import hashlib,json,re
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0876-original-coverage-scope-probe';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');f=read(D/'freeze.json');assert m['reservation']['status']=='in_progress'
assert all(sha(R/n)==h for n,h in f['files'].items())
cases=read(D/'cases.json');manual=read(O/'manual-review.json');runs={c['id']:read(O/c['id']/'result.json') for c in cases};audits={c['id']:read(O/c['id']/'audit.json') for c in cases}
checks=read(A/'artifacts/live-contract-checks.json')['checks'];log=(A/'artifacts/candidate-api.log').read_text();assert '314 passed' in log
usage=[v for r in runs.values() for v in r['usage']];spans=[x for a in audits.values() for x in a['evidence_span_checks']]
result={'status':'complete','candidate':f['candidate'],'technical_tests':314,'checks':checks,'cases':{cid:{k:v for k,v in r.items() if k!='usage'} for cid,r in runs.items()},'manual_review':manual,
 'model_calls':sum(r['model_calls'] for r in runs.values()),'original_span_checks':len(spans),'original_span_mismatches':sum(not x['exact_original_match'] for x in spans),
 'actual_models':sorted({v['model'] for v in usage}),'actual_providers':sorted({v['upstream_provider'] for v in usage}),
 'usage':{'input_tokens':sum(v.get('input_tokens') or 0 for v in usage),'output_tokens':sum(v.get('output_tokens') or 0 for v in usage),'cost_usd':sum(v.get('cost_usd') or 0 for v in usage)},
 'in_sample':True,'decision_eligible':False,'legal_quality_certified':False,'genos_executed':False,'data_changed':False}
put(O/'result.json',result)
# Measured original sets; the source span audit owns exact IDs. No gold or ranking quality claim.
plans=[{'stage_id':'native_read','kind':'source','parent_stage_ids':[]},{'stage_id':'child_return','kind':'select','parent_stage_ids':['native_read']},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['child_return']}]
def unique(v):return [json.loads(s) for s in sorted({json.dumps(x,sort_keys=True) for x in v})]
ledgercases=[]
for c in cases:
 cid=c['id'];a=audits[cid];before=[];stages=[]
 sets=[[r for child in a['children'].values() for r in child['canonical_read']], [r for child in a['children'].values() for r in child['canonical_adopted']],a['canonical_final']]
 for plan,raw in zip(plans,sets):
  after=unique(raw);added=[x for x in after if x not in before];discarded=[x for x in before if x not in after];reason='Not in current source-return or final citation set; original journal retained. No legal irrelevance or absence claim.'
  stages.append({**plan,'executed':True,'skip_reason':None,'before':before,'added':added,'discarded':discarded,'after':after,'before_count':len(before),'added_count':len(added),'discarded_count':len(discarded),'after_count':len(after),'occurrence_counts':{'before':len(before),'after':len(raw),'canonical_collapsed_before':0,'canonical_collapsed_after':len(raw)-len(after)},'discard_receipts':[{'identity':x,'reason':reason} for x in discarded],'discard_reason_counts':{reason:len(discarded)} if discarded else {},'gold_total':0,'gold_before':0,'gold_added':0,'gold_discarded':0,'gold_after':0,'golden_recall':None,'gold_before_identities':[],'gold_added_identities':[],'discarded_gold':[],'gold_after_identities':[]});before=after
 ledgercases.append({'schema_version':'retrieval-stage-ledger-v1','computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':'case_id + canonical article-root coordinate','arm_id':'scoped','case_id':cid,'gold_total':0,'gold_identities':[],'stages':stages})
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':[{'arm_id':'scoped','declared_stage_ids':[p['stage_id'] for p in plans],'cases':ledgercases,'aggregate':{'cases':2,'presented_total':sum(len(a['canonical_final']) for a in audits.values()),'gold_total':0}}]}]}
put(O/'retrieval-ledger.json',ledger)
m['design']['retrieval_stage_plan']['stages_by_arm']={'scoped':plans};m['runs'][0].update(status='complete',artifact_path=str((O/'result.json').relative_to(R)),sha256=sha(O/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','basis':'Completed0875 record, not rerun'},'scoped':{'status':'complete','checks':checks,'manual_review':manual}},usage={'product_model_calls':result['model_calls'],'offline_evaluator_calls':0,**result['usage']},error_taxonomy=manual['remaining'])
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((O/'retrieval-ledger.json').relative_to(R)),sha256=sha(O/'retrieval-ledger.json'),not_applicable_reason=None)
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q,c in zip(m['questions'],cases):
 cid=c['id'];p=A/'실험'/q['file'];parts=['run-001/scoped; frozen MAIN84-derived candidate, selected data unchanged.',c['question'],'Approved legal gold absent; no accuracy certification.',f'../artifacts/design/cases.json and frozen binding.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n../artifacts/run-001/retrieval-ledger.json; exact spans in {cid}/audit.json.',f'../artifacts/run-001/{cid}/raw/call-*/request.json and response.json; ExperimentClient Qwen3.8 Parasail FP8.',f'{cid}/calls.json, generations.json and canonical/*.json.gz; all native decisions and failures preserved.','No evaluator model. Read-only exact original and scope review.',json.dumps(manual.get(cid,{}),ensure_ascii=False)]
 p.write_text('# '+cid+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{x}' for i,(h,x) in enumerate(zip(heads,parts),1))+'\n');q['sha256']=sha(p)
put(A/'실험/manifest.json',m)
sections=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
parts=['Known-case probe complete; independent qualification required before MAIN.','Data audit separates missing selected inputs, unread ranges, acquired-but-pruned originals, and model applicability judgments.',json.dumps(read(D/'criteria.json'),ensure_ascii=False),'Each case once; frozen candidate and current data, sequential resource guard. No adaptive product edits.',str(f['candidate']),json.dumps(result,ensure_ascii=False),json.dumps(manual,ensure_ascii=False),'Resource receipts; shared existing generation; no large data clone.','Original-context retention is deterministic. Scope and legal applicability remain reviewable model opinions.','Known questions, no approved legal gold; no GENOS/model field claim.','MAIN84 unchanged during probe; new finite qualification needed. Missing selected RAW requires separate explicit scope/package update.','seal.py; preview.py; resource_guard run_validation.py candidate; live.py committee-comparison; live.py withdrawal; audit.py; inspect_live.py; finalize_probe.py; stable validate --final and graph.']
meta=(A/'README.md').read_text().split('---',2)[1];meta=re.sub(r'(?m)^status:.*$','status: Proposed',meta)
(A/'README.md').write_text('---'+meta+'---\n\n# 원문 전달과 적용범위 실제 모델 점검\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{x}' for i,(h,x) in enumerate(zip(sections,parts),1))+'\n')
(A/'실험/README.md').write_text('# 실제 모델 점검\n\n'+'\n'.join('- ['+q['case_id']+']('+q['file']+')' for q in m['questions'])+'\n')
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen actual-model audit','contains_raw_prompts_and_outputs':'/raw/' in str(p) or '/canonical/' in str(p)} for p in (A/'artifacts').rglob('*') if p.is_file() and p!=A/'artifacts/manifest.json' and not p.name.endswith(('-wal','-shm'))]})
print('Probe complete',result['model_calls'],'calls; original mismatches',result['original_span_mismatches'])
