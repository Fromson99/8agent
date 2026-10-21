from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0812-comparison-wire-context'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
models={'baseline':read(R/'04_EXPERIMENTS/ADR/ADR-0811-workflow-version-source-binding/artifacts/model-v2/connected/result.json'),'connected':read(A/'artifacts/model-v2/connected/result.json')}
assert all(len(v['results'])==3 and v['model_calls']==3 for v in models.values())
f=read(A/'artifacts/design/freeze.json');assert all(sha(R/n)==h for n,h in f['files'].items())
c=read(A/'artifacts/candidate-consumer-v2.json');assert all(c['checks'].values())
counts={k:sum(x['correct'] for x in v['results']) for k,v in models.items()}
limitations=['Synthetic comparison only; no retrieval or full legal accuracy claim','Actual selected corpus1547 has no verified workflow_version/valid_from records; substantive legal comparisons remain gated','Needed internal regulations are not established as available','Missing user facts without issue linkage still gate all issues','Initial numeric verdict can contradict correctly extracted threshold differences; canonical validator rejects it; service single correction not exercised in this direct first-attempt probe']
result={'status':'complete','strict_success':False,'checks':{'boundary_contracts':True,'actual_service':True,'synthetic_success':counts['connected']==3},'tests':{'boundary_passed':146,'regressions_passed':170,'actual_api':12,'actual_source_cases':6,'source_read_plans':76},'models':models,'synthetic_correct':counts,'limitations':limitations,'quality_certified':False}
put(A/'artifacts/run-001/result.json',result)
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'))
m['results'].update(status='complete',by_arm={k:{'status':'complete','correct':counts[k],'total':3,'strict_success':False} for k in models},usage={'product_model_calls':3,'offline_evaluator_calls':0},error_taxonomy=[{'kind':'other','detail':'Two numeric proposals select CONFORMS despite value DIFFERENT and are rejected. No format/output length failure; one-attempt probe has no service correction. Parent diagnostic harness differs; no causal accuracy improvement estimate.'}]);put(A/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=['Proposed/complete diagnostic; no promotion from this in-sample probe. Structural/API checks pass; numeric first-attempt judgments remain inconsistent in2/3cases. MAIN75 and working source unchanged.',
'Completed0811 had free-form duplicate rows/dimensions/output exhaustion and counted duplicate raw originals against context. Actual attachment hierarchy exposed multiple canonical source groups rejected by single-source assumption.',
'Frozen criteria in artifacts/design/criteria.json before implementation/calls; generalized wire shape, actual payload budget, complete source partitions. No question-specific thresholds, answer rules or arbitrary source slicing.',
'Fixed candidate338files;146 new/inherited boundary tests,170 regressions,12 actual API checks, actual selected-generation coordinates and readplans. Same fictional three cases; one attempt each,4000token cap, no fallback/repair. Parent recorded result is a diagnostic reference, not an identical-prompt controlled baseline.',
'Qwen3.8 Parasail FP8 reasoning none. Probe uses shared product SYSTEM, captured COMPARE instructions, strict_json and opaque packet hash. Prior harness omitted shared SYSTEM and used semantic case labels; this chronology is explicit. Expected verdict never enters candidate product input.',
f'All316 software checks and12 actualAPI checks pass. Actual embedded annex305blocks plus detached74source groups:76readplans,431unique blocks hash-verified. Model3 complete outputs; canonical+verdict correct{counts["connected"]}/3. Other2 rejected for CONFORMS withDIFFERENT. Exact source and raw model receipts preserved.',
'One pair/required dimension keys/short exact citation IDs remove output-length and duplicate-field failures in these three calls. Numeric values are correctly described, but verdict generated before analysis anchors on identical definition. Next probe will put source dimensions before final decision and exercise existing service correction owner.',
'3 new model calls; no evaluator call. Actual usage/elapsed in model-v2/connected/result.json. No retrieval recall, whole-RAG latency or legal accuracy estimate.',
'Technical completeness improved but correct evidence does not guarantee correct synthesis. Validator prevents two contradictory conclusions from becoming answers. No automatic semantic correction or verdict substitution.',
'\n'.join(limitations),
'No MAIN/GENOS/Git-main change. All earlier failed probes retained. Separate frozen followup before further output-order/prompt/model tests; finite independent technical qualification still required for promotion.',
'repin.py → candidate freeze/validate → freeze.py → run_tests.py/tests+regressions → consumer_check.py candidate → actual_source_check.py → model_probe.py connected.']

meta=(A/'README.md').read_text().split('---',2)[1]
(A/'README.md').write_text('---'+meta+'---\n\n# ADR-0812 비교 형식·원문 예산·계층 원문 연결\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,texts),1))+'\n')
(A/'RESULT.txt').write_text('\n\n'.join(texts)+'\n');(A/'실험/README.md').write_text('# 실험 기록\n\n고정 모의3문항 후보3호출과 완료0811 기록 비교. 공통 SYSTEM/opaque hash 차이가 있으므로 인과적 정확도 향상으로 해석하지 않습니다. 기대판정은 제품입력과 분리했습니다. artifacts/model-v2에 정확입출력·사용량·판정이 있습니다. 실제 법률정답 인증이 아닙니다.\n')
files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and not p.name.endswith(('-wal','-shm','.lock'))]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0812','created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen contracts, service and synthetic model records','contains_raw_prompts_and_outputs':'model-v2' in p.parts} for p in files]})
print(counts)
