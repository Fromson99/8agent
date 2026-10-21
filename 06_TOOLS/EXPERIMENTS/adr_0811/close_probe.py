from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0811-workflow-version-source-binding'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
models={arm:read(A/'artifacts/model-v2'/arm/'result.json') for arm in ('baseline','connected')}
assert all(len(v['results'])==3 and v['model_calls']==3 for v in models.values())
f=read(A/'artifacts/design/freeze.json');assert all(sha(R/n)==h for n,h in f['files'].items())
c=read(A/'artifacts/candidate-consumer-v2.json');assert all(c['checks'].values())
counts={k:sum(x['correct'] for x in v['results']) for k,v in models.items()}
limitations=['Synthetic comparison only; no retrieval or full legal accuracy claim','Actual selected corpus1547 has no verified workflow_version/valid_from records; substantive legal comparisons remain gated','Needed internal regulations are not established as available','Missing user facts without issue linkage still gate all issues','Packet budgets count duplicated pre-projection originals; followup required']
result={'status':'complete','strict_success':False,'checks':{'boundary_contracts':True,'actual_service':True,'synthetic_success':counts['connected']==3},'tests':{'initial_passed':99,'initial_failed':1,'failure':'Obsolete assertion inspected continuation removed from model view; journal-native replacement passes without changing product','replacement_passed':1,'regressions_passed':142,'actual_api':12},'models':models,'synthetic_correct':counts,'limitations':limitations,'quality_certified':False}
put(A/'artifacts/run-001/result.json',result)
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'))
m['results'].update(status='complete',by_arm={k:{'status':'complete','correct':counts[k],'total':3,'strict_success':False} for k in models},usage={'product_model_calls':6,'offline_evaluator_calls':0},error_taxonomy=[{'kind':'other','detail':'Repeated dimension names/rows and output-length exhaustion; original import harness failure occurred before calls and is preserved'}]);put(A/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=['Rejected for promotion: structural and API checks pass, but the frozen real model probe did not satisfy comparison success. MAIN75 and working serving source unchanged.',
'Inherited generalized source/definition/issue/span/deferred repairs from completed0810. Corrected omitted workflow version by resolving unique registered definition before request hash, instead of hardcoding1.1.',
'Frozen design/criteria.json controls source/hash/ACL/state and synthetic numeric comparison. No threshold or legal-answer rules in product.',
'MAIN75 baseline vs frozen0811 rev001; three fictional lower/stricter/same thresholds each, no repeat/repair/fallback. Known-defect probe; in_sample=true, decision_eligible=false.',
'338 serving files, unchanged generation/profile/model. Qwen3.8 Parasail FP8 reasoning none. Original runner import failed before any call; supplemental exact-file/hash common client binding preserves original runner/error and uses new output folder.',
f'Original100 tests:99pass/1obsolete assertion failure; journal-native replacement1pass; regressions142pass; actualAPI12pass. Fictional canonical+verdict correct baseline{counts["baseline"]}/3, connected{counts["connected"]}/3. Raw outputs and usage: artifacts/model-v2.',
'Baseline repeated numeric names; candidate repeated rows/dimensions and output-token exhaustion. Never accepted incomplete replies. A known single pair and dimension inventory should be system-owned wire structure; a new ADR is required.',
'6 total external product calls; exact usage/elapsed in model-v2/*/result.json. Retrieval recall and real legal answer accuracy not measured.',
'Exact source and durable joins improve structural integrity, but more elaborate free-form output can regress completion. Do not promote this probe based on software tests alone.',
'\n'.join(limitations),
'No MAIN/GENOS/Git main changes. Preserve all failed calls. Followup uses complete0811/connected parent and new prospective output/context criteria.',
'audit_pinned.py; run_tests.py; consumer_check.py candidate; model_probe_bound.py baseline then connected. Supplemental model-runner-binding.json records exact harness correction.']
meta=(A/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Rejected')
(A/'README.md').write_text('---'+meta+'---\n\n# ADR-0811 선택 워크플로우와 원문 완결성\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,texts),1))+'\n')
(A/'RESULT.txt').write_text('\n\n'.join(texts)+'\n');(A/'실험/README.md').write_text('# 실험 기록\n\n고정 모의3문항×2arms. 기대판정은 제품입력과 분리했습니다. artifacts/model-v2에 정확입출력·사용량·판정이 있습니다. 실제 법률정답 인증이 아닙니다.\n')
files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and not p.name.endswith(('-wal','-shm','.lock'))]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0811','created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen contracts, service and synthetic model records','contains_raw_prompts_and_outputs':'model-v2' in p.parts} for p in files]})
print(counts)
