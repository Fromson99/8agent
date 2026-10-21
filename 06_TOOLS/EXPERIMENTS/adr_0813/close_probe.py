"""Close the fixed probe without converting known-case observations to adoption."""
from pathlib import Path
import json,hashlib,re
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0813-evidence-first-comparison'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def count(name):
 s=(A/'artifacts'/name).read_text();assert not re.search(r'\b[1-9]\d* failed\b',s),name
 return int(re.findall(r'(\d+) passed',s)[-1])
f=read(A/'artifacts/design/freeze.json');assert all(sha(R/n)==h for n,h in f['files'].items())
model=read(A/'artifacts/model-real-stack/connected/result.json');assert len(model['results'])==3 and model['model_calls']<=6
consumer=read(A/'artifacts/candidate-consumer-v2.json');assert all(consumer['checks'].values())
counts={'boundary':count('boundary-tests.txt'),'regression':count('regression-tests.txt'),'actual_api':len(consumer['checks'])}
navigation={arm:read(A/'artifacts/navigation'/f'{arm}.json') for arm in ('baseline','connected')}
assert sorted(navigation['connected']['available'],key=str)==sorted(navigation['connected']['presented'],key=str)
correct=sum(x['correct'] for x in model['results']);reuse=all(x['reopen_no_additional_calls'] and x['reopen_same_deadline'] and x['reopen_same_budget'] for x in model['results'])
limits=['Known fictional cases; combined evidence-first output and actual service-owned repair observation, not an isolated order effect estimate or legal holdout.',
'Actual selected1547 documents have no verified workflow_version/valid_from records; substantive legal comparison remains gated.',
'Needed internal regulation availability remains unconfirmed; retrieval fixes do not create missing source data.',
'Missing user facts without issue linkage still gate all issues.',
'Full real-data RAG comparison was not rerun; actual gateway experiment uses synthetic originals. GENOS unchanged.']
result={'status':'complete','strict_success':correct==3 and reuse,'checks':{'contracts':True,'actual_service':True,'initial_navigation_complete':True,'durable_model_reuse':reuse,'fictional_correct':correct==3},'tests':counts,'models':model,'correct':correct,'navigation_counts':{a:{k:len(v[k]) for k in ('available','presented')} for a,v in navigation.items()},'quality_certified':False,'limitations':limits}
put(A/'artifacts/run-001/result.json',result)
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','basis':'Completed0812 diagnostic records; no comparable one-repair baseline call'},'connected':{'status':'complete','strict_success':result['strict_success'],'correct':correct,'total':3}},usage={'product_model_calls':model['model_calls'],'offline_evaluator_calls':0},error_taxonomy=[] if correct==3 else [{'kind':'other','detail':'Remaining fictional comparison errors retained in exact gateway/journal records'}]);put(A/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=['Proposed/complete diagnostic. In-sample probe cannot authorize promotion. Working code and MAIN75 unchanged at probe closure.',
'Initial model could correctly extract differing thresholds then say CONFORMS. Saved invalid raw response could loop after interruption before failure receipt. Initial navigation silently cut definition/term/document/structure locations before the first planner.',
'Before freeze/calls: evidence and dimension observations precede verdict; existing single repair owner revalidates recovered proposals without resetting allowance; full initial navigation locations and verified definition references are retained under actual existing context budget. No question-specific answer rules or arbitrary text slicing.',
'Three fixed fictional cases, actual ModelAdapter/WorkRepository/workflow.Repository/Services.structured gateway/SourcePort; at most2 physical calls per case,6 total. Deterministic recovery/fault tests and selected-generation service checks are separate from model observations.',
'Exact338 serving files, code/data/profile/client/prompt hashes in design/freeze.json. Qwen3.8 Parasail FP8 reasoning none no fallback; only synthetic originals sent. Raw wire/schema field orders, journal attempts, corrections and original binding retained.',
f"Boundary{counts['boundary']} and shared regression{counts['regression']} pass; actual API{counts['actual_api']} pass. Model correct{correct}/3, calls{model['model_calls']}; reopened journal unchanged budget/deadline and no new calls={reuse}.",
'Per-case first proposal validation, correction, final verdict, usage and restart results in artifacts/model-real-stack/connected/result.json. Provider success and canonical judgment validity are distinct. Interrupted invalid proposal is repaired by the same owner; stale/hash/ACL/source failures are fail-stop.',
'Model usage/elapsed from raw common-client receipts. No whole-RAG or legal accuracy estimate. Context budget is measured on complete source-query-plan wire input; oversized input stops with explicit incompleteness, without trimming source locations.',
'General source completeness, exact citation projection and mechanical recovery can be verified independently of legal interpretation. Meaning remains model-owned; no numerical threshold rule determines the verdict.',
'\n'.join(limits),
'No MAIN/GENOS/Git-main change from this probe. Subsequent frozen finite technical qualification must be independently completed before same-code promotion. Preserve prior failed probes.',
'repin.py → adr_candidate freeze/validate → freeze.py → run_tests.py → navigation_probe.py both arms → account_navigation.py → consumer_check.py candidate → model_probe.py connected → close_probe.py → adr_structure final validation.']
meta=(A/'README.md').read_text().split('---',2)[1]
(A/'README.md').write_text('---'+meta+'---\n\n# ADR-0813 근거 선행 비교·재개·초기 위치 완전성\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,texts),1))+'\n');(A/'RESULT.txt').write_text('\n\n'.join(texts)+'\n')
(A/'실험/README.md').write_text('# 고정 모의 비교 관찰\n\n제품 실제 비교 adapter/gateway와 영구 원장으로 실행. 이전0812는 보정 없는 진단이므로 순서 변경 단독 효과나 법률 정확도 향상률로 해석하지 않습니다. 기대판정은 제품 입력과 분리합니다.\n')
files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and not p.name.endswith(('-wal','-shm','.lock'))]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0813','created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen source, contracts, actual gateway and model records','contains_raw_prompts_and_outputs':'model-real-stack' in p.parts} for p in files]})
print(json.dumps({'correct':correct,'model_calls':model['model_calls'],'reuse':reuse,'tests':counts}))
