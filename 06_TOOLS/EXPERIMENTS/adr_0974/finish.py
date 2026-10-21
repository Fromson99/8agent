"""Finalize only the actual qualified frozen candidate; no threshold changes."""
from common import *
import statistics,gzip
m=read(ADR/'실험/manifest.json');a=read(ART/'analysis.json');assert a['strict_success'] and all(a['checks'].values())
f=read(ART/'design-freeze.json');s=read(ART/'stage.json');contracts=read(ART/'contracts-final.json')
assert contracts['passed'] and contracts['tests']==199
for kind in ('script_bindings','test_bindings'):
 for n,h in f['design'][kind].items():assert sha(ROOT/n)==h,n
assert all(sha(ROOT/n)==h and sha(ROOT/s['roots']['candidate']/n)==h for n,h in s['files']['candidate'].items())
for mode in ('candidate','working'):
 c=read(ART/f'consumer-{mode}.json');assert c['status']=='PASS' and all(c['checks'].values())
counts={arm:sum(x['pass'] for x in ts) for arm,ts in a['by_arm'].items()}
usage={k:sum(u.get(k) or 0 for u in a['usage']) for k in ('input_tokens','output_tokens','thinking_tokens','cost_usd')};usage['physical_model_calls']=a['physical_model_calls']
provider_errors=[{'arm':arm,'case_id':r['case_id'],'error':r['error']} for arm,ts in a['by_arm'].items() for r in ts if r['error'] and r['error']['type']=='ExperimentProviderError']
latency={arm:{'p50_seconds':statistics.median(r['seconds'] for r in ts),'p95_seconds':sorted(r['seconds'] for r in ts)[round((len(ts)-1)*.95)]} for arm,ts in a['by_arm'].items()}
def bound(p):return {'path':str(p.relative_to(ROOT)),'sha256':sha(p)}
checks={**a['checks'],'all199_contracts':True,'candidate_working_native_consumers':True,'all419_working_candidate_files_match':True,'frozen_scripts_and_tests':True}
result={'strict_success':True,'checks':checks,'status':'QUALIFIED_FOR_MAIN','correct':counts,'total_per_arm':32,'physical_model_calls':a['physical_model_calls'],'usage':usage,'latency':latency,'contracts':contracts['tests'],'contracts_result':bound(ART/'contracts-final.json'),'analysis':bound(ART/'analysis.json'),'consumers':{x:bound(ART/f'consumer-{x}.json') for x in ('candidate','working')},
 'prior_failures':[{'adr':'ADR-0972','result':bound(ROOT/'04_EXPERIMENTS/ADR/ADR-0972-structured-selection-qualification/artifacts/result.json')},{'adr':'ADR-0973','result':bound(ROOT/'04_EXPERIMENTS/ADR/ADR-0973-required-structural-selection/artifacts/result.json')}],
 'quality_certified':False,'genos_verified':False,'provider_errors':provider_errors,'response_count':a['physical_model_calls']-len(provider_errors),
 'contract_metadata_errata':{'field':'extra_recovery_audit.added_after_model_freeze','original_value':True,'correct_value':False,'evidence':'The design-freeze.json test_bindings already contains this exact test hash. The runner metadata copied from ADR0973 is stale; tests, outcomes and thresholds are unchanged.'},
 'limits':['32 new developer-authored synthetic expressions are not statistically representative user traffic.',
 'The live model metric covers one native structured decision plus bounded repair and actual original READ, not complete answer generation or legal-answer correctness.',
 'Actual service consumer verifies HEALTH and exact helper/code/profile/data/selection binding under2GiB address space. Full local original corpus was not loaded concurrently with the existing unrelated embedding job; original READ/ACL/reuse paths are independently covered by exact-code synthetic API contracts.',
 'Qwen3.8 external results do not certify GENOS internal models or field deployment. No performance/general legal-quality uplift is claimed.',
 'Earlier trials are rejected and immutable: ADR0972 candidate16/32, ADR0973 candidate31/32. Prior failures are not replaced by this fresh sample.',
 'Global historical graph/old test failures outside this199-test qualification are not declared fixed.',
 'Physical request count includes a baseline HTTP429 provider failure. It is retained without retry, counted as baseline failure, and is not evidence of semantic inferiority.']}
save(ART/'result.json',result);m['decision_eligible']=True;m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'))
m['results'].update(status='complete',by_arm={arm:{'status':'complete','correct':counts[arm],'total':32,'strict_success':arm=='candidate'} for arm in counts},comparisons=[a['comparison']],judge_disagreements=0,usage=usage,latency=latency,error_taxonomy=['No frozen critical-scope violation in qualified candidate; prior failed trials retained separately','Provider failures retained without retry: '+json.dumps(provider_errors,ensure_ascii=False)])
ret=m['retrieval_accounting']
for metric in ('presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity'):ret[metric]={arm:r[metric] for arm,r in a['retrieval'].items()}
ret['before_filter']={arm:8*32 for arm in counts};ret['after_filter']=ret['presented_total'];ret['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json')
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
paragraphs=['Accepted / promotion-candidate. 고정한 범위 선택 기준과199계약·419파일·서비스 연결 검사를 통과했다. 실제 MAIN 포인터 전환과 GENOS ZIP 검증은 별도 감사 기록으로 확인한다.',
 'MAIN98은 자연어 범위 집합을 한 구조화 결정으로 고정하지 못했다. 기존 자연어 판별 수정과 집합 선택 위에서 ADR0972의 필드 생략, ADR0973의 적용 조건/읽기 제외 혼동을 보완했다. 원문을 어디까지 읽을지와 읽은 조항을 적용할지는 별도의 의미 판단이며 둘 모두 LLM이 수행한다. 정규표현식으로 사용자 의미를 추측하거나 모델 출력을 바꾸지 않는다.',
 m['design']['success_criteria'],m['design']['sampling']+'\n\n'+m['design']['arms'][0]['changes']+'\n\n부모 ADR0973/candidate는 완료됐으나 승격 거절된 후보다. 그 실패를 상속 성공으로 보지 않고, 새 후보를 새 문장으로 전부 검증했다.',
 '새 합성 문서2개·조8개·저장노드232개, 질문32개×2arm. 원문/제품 질문과 채점 데이터는 분리했고 제품 실행기는 grading-only.json을 읽지 않는다. Qwen3.8 / qwen/qwen3.8-27b / OpenRouter Parasail FP8 / reasoning none / fallback 없음. 코드·입출력 계약·스크립트·모델·데이터·기준은 첫 호출 전에 동결했다.',
 json.dumps({'correct':counts,'checks':checks,'comparison':a['comparison'],'contracts':contracts['tests']},ensure_ascii=False,indent=2),
 '단일·범위·열거·제외·열린 경계·부모 항 여러 개·목·문서 여러 개·미존재·빈 선택·미해당 가정을 원문 블록 단위로 확인했다. 없는 범위를 명시적 미해결로 돌려 원문을 읽지 않은 경우를 안전한 음성 사례로 구분했다. 초기 필드 누락의 수정 성공·반복 실패·동일 요청 재개 예산은2개 추가 계약에서 검사했다. 모든 세부 결과와 원시 호출은 질문별 문서에 연결한다.',
 json.dumps({'usage':usage,'latency':latency,'retrieval':a['retrieval']},ensure_ascii=False,indent=2),
 '확인된 것은 이 합성 세트의 구조화 선택과 실제 READ 집합 일치다. 조 단위 recall만으로 호 범위 정확성을 주장하지 않고 별도 block set metric을 사용했다. 모델 정확도 일반화나 전체 법률 답변의 정답 인증으로 확대하지 않는다.',
 '\n\n'.join(result['limits']),
 '사용자가 요청한 조건부 MAIN 반영에 따라 품질 우회 없이 stable prepare/apply --confirm-main을 사용한다. 데이터·모델 프로필·검색 선택은 유지하고419파일을 평가 후보와 결속한다. 활성 service.service.application()의 코드/포인터/HEALTH 불일치 시 이전 MAIN98로 복원한다. GENOS 기존 DEV에 적용하는 ZIP은 별도 설치 모의 검사를 거치며 현장 반입·push·리비전 배포·내부 모델 확인과 구분한다.',
 '06_TOOLS/EXPERIMENTS/adr_0974/{implement,dataset,build_synthetic,freeze,run_case,run_trials,analyze,run_final_contracts,consumer,seal_release,integrate_working,finish}.py. 완료 호출을 덮어쓰지 않는다. stable adr_structure.py validate --final 및 graph를 실행한다. [결과](artifacts/result.json), [사전 기준](artifacts/design-freeze.json), [정확 코드](artifacts/stage.json), [원장](artifacts/retrieval-ledger.json), [통합](artifacts/integration.json).']
front=(ADR/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Accepted').replace('main_wiring: unchanged','main_wiring: promotion-candidate')
(ADR/'README.md').write_text('---'+front+'---\n\n# ADR-0974 원문 범위와 적용 조건의 구조화 분리\n\n'+''.join(f'## {i}. {h}\n\n{p}\n\n' for i,(h,p) in enumerate(zip(heads,paragraphs),1)))
cases={r['id']:r for r in read(ART/'cases.json')};gold={r['case_id']:r for r in read(ART/'grading-only.json')};ledger=read(ART/'retrieval-ledger.json')
index=['# ADR-0974 질문과 원시 호출',f'기준{counts["baseline"]}/32, 후보{counts["candidate"]}/32. 실제{a["physical_model_calls"]}호출.','| 질문 | 기준 | 후보 | 기록 |','|---|---:|---:|---|']
for q in m['questions']:
 cid=q['case_id'];sections=[f'# 질문 {q["number"]:03d} — {cid}','## 1. 실행 메타','run-001 / baseline,candidate / temperature0 / Parasail FP8 / reasoning none / 각1회; 기존 bounded owner의 수정 최대1회.','## 2. 사용자 질문 원문',cases[cid]['question'],'## 3. 기준답변 — 채점 전용, 제품 입력 비공개',json.dumps(gold[cid],ensure_ascii=False),'## 4. 제품 입력을 구성한 원값','[제품 질문](../artifacts/cases.json), [합성 원문](../artifacts/documents.json), [저장 좌표 검사](../artifacts/fixture-preflight.json).','### 회수·탈락 단계 원장 — run·arm별','[기사 root identity·추가·탈락·READ 원장](../artifacts/retrieval-ledger.json). 조 안의 범위는 별도 block set metric으로 평가했다.','| arm | stage | before→after | added/discarded | gold before→after |','|---|---|---:|---:|---:|']
 for ar in ledger['runs'][0]['arms']:
  rec=next(x for x in ar['cases'] if x['case_id']==cid)
  for st in rec['stages']:sections.append(f'| {ar["arm_id"]} | {st["stage_id"]} | {st["before_count"]}→{st["after_count"]} | {st["added_count"]}/{st["discarded_count"]} | {st["gold_before"]}→{st["gold_after"]} |')
 sections.append('## 5. 제품 모델 호출 — run·arm별 실제 원문');verdicts=[]
 for arm in ('baseline','candidate'):
  folder=ART/'trials'/cid/arm;sections.append(f'### run-001 / {arm}\n\n[전체 관찰·결정·원문 읽기](../artifacts/trials/{cid}/{arm}/result.json)')
  for call in sorted((folder/'model').glob('call-*')):sections.append(' '.join(f'[{call.name}/{p.name}](../artifacts/trials/{cid}/{arm}/model/{call.name}/{p.name})' for p in sorted(call.glob('*.json'))))
  v=next(x for x in a['by_arm'][arm] if x['case_id']==cid);verdicts.append(v['pass']);sections.append(json.dumps(v,ensure_ascii=False))
 sections+=['## 6. 중간 LLM 호출 — router/compiler/verifier/repair','초기 분류 또는 compact navigation과 bounded repair의 모든 입력·응답을 위에 연결했다. 숨은 호출·평가 모델은 없다.','## 7. 채점 호출과 반복 판정','LLM judge 없음. 선택 후 고정한 기대 원문 블록 집합과 대조했다. 결과 후 기준 변경·재생성·다수결 없음.','## 8. 사례 최종 판정',f'기준={verdicts[0]}, 후보={verdicts[1]}. 단계별 결과와 한계는 analysis/result에 남겼다.']
 p=ADR/'실험'/q['file'];p.write_text('\n\n'.join(sections)+'\n');q['sha256']=sha(p);index.append(f'| {cid} | {verdicts[0]} | {verdicts[1]} | [{q["file"]}]({q["file"]}) |')
(ADR/'실험/README.md').write_text('\n\n'.join(index[:2])+'\n\n'+'\n'.join(index[2:])+'\n');save(ADR/'실험/manifest.json',m)
expected={q['file'] for q in m['questions']}
for p in (ADR/'실험').glob('질문-*.md'):
 if p.name not in expected:
  with gzip.open(ART/('unused-scaffold-'+p.name+'.gz'),'wb') as f:f.write(p.read_bytes())
  p.unlink()
files=[]
for p in sorted(ART.rglob('*')):
 if not p.is_file() or p==ART/'manifest.json' or 'runtime' in p.parts or 'preflight' in p.parts:continue
 files.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen qualification or exact integration evidence','contains_raw_prompts_and_outputs':'model' in p.parts})
save(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'created_at':m['reservation']['created_at'],'files':files})
print('Qualified',counts,usage,'contracts',contracts['tests'])
