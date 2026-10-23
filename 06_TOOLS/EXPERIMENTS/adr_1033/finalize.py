from common import *
import sys,re
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
from adr_structure import ADR_HEADINGS
s=read(ART/'stage.json');c=ROOT/s['root'];f=read(sorted(ART.glob('design-rev-*.json'))[-1]);m=read(ADR/'실험/manifest.json')
assert all(sha(c/n)==sha(ROOT/n)==h for n,h in f['files'].items())
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['pointer_sha256']
logs=['contracts-final.log','regression-final.log','working-contracts.log'];counts={}
for n in logs:
 t=(ART/n).read_text();assert 'FAILURES' not in t and 'ERRORS' not in t,n
 counts[n]=int(re.findall(r'(\d+) passed',t)[-1])
result={'status':'complete','verdict':'IMPLEMENTED_CONTRACT_VERIFIED_MODEL_EFFECT_UNMEASURED',
 'preexisting_expanded_test_failures':40,'baseline_failure_comparison':read(ART/'baseline-failure-comparison.json'),
 'tests':counts,'unique_candidate_tests':counts[logs[0]]+counts[logs[1]],
 'final_revision':m['design']['code_isolation']['candidates'][0]['revision_id'],
 'candidate_working_identical_files':len(f['files']),'integration':read(ART/'working-integration.json'),
 'real_external_model_calls':0,'synthetic_api_normal_calls':6,'additional_review_only_calls':0,
 'main_changed':False,'genos_changed':False,'quality_certified':False,'decision_eligible':False,
 'limitations':['No live model question run or legal-correctness assessment in this implementation task.',
 'Mechanical omission/identity/state checks do not detect every semantic contradiction; LLM findings remain provisional.',
 'Unresolved needs/conflicts may yield a limited answer. Existing call/deadline/token budgets still apply; newly read originals at budget exit are marked unreviewed for final assessment.',
 'Final schema repair exhaustion retains prior investigation in the journal but uses the existing pending/failed response; it does not fabricate a legal answer.',
 'Per-source ledger size adds input/output tokens within the same calls. Live latency/token effects are unmeasured.',
 'State is request-bound and source-linked. This is not a cross-question approved ontology or reusable legal-truth store.']}
save(ART/'result.json',result)
m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'),executed_arm_ids=['candidate'])
m['results'].update(status='complete',by_arm={
 'baseline':{'status':'complete','correct':None,'total':0,'accuracy':None,'reason':'Historical completed implementation parent, no paired live comparison.'},
 'candidate':{'status':'complete','correct':None,'total':0,'accuracy':None,'contract_tests_passed':result['unique_candidate_tests']}},
 judge_disagreements=0,usage={'physical_calls':0,'input_tokens':0,'output_tokens':0},
 latency={'model_latency':None,'reason':'No real model calls; deterministic API fixture timings in logs.'},
 error_taxonomy=['rev001 internal saved-result schema rejected new receipt; repaired consumer contract.',
 'rev001 conflict ID prefix C collided with generated claim C1 handle; changed conflict namespace to X and added regression.',
 'Expanded regression initially55 failures:40 reproduced on unchanged working baseline;15 new optional-policy test-double errors fixed.'])
save(ADR/'실험/manifest.json',m)
front=(ADR/'README.md').read_text().split('---',2)[1]
parts=[result['verdict']+' — 작업 코드 통합·활성화. 선택 MAIN102·GENOS 불변.',
 '기존 경로는 다음 도구의 이유만 남겼으며 원문별 의견·부족·충돌의 누적 검토 계약이 없었다. ADR1032 실제 질문에서는 반복 조사와 세부 근거 미확인이 남았다.',
 m['design']['hypothesis']+'\n\n'+m['design']['success_criteria']+'\n\n'+m['design']['failure_criteria'],
 '합성 상태·원문·API 계약 검사. 실제 질문/모델 성능 비교 아님. 새 판단 모드와 기존 모드의 회귀를 따로 확인한다. 실패 원인 수정은 revision과 원본 로그를 보존한다.',
 'ADR1032 완료 후보를 정확한 부모로 삼고 현재 작업507파일에서 격리한 snapshot을 수정했다. 원문·모델 정책·예산 불변. 각 검사 전에 후보 revision과 runner를 동결했다. [최종 동결](artifacts/'+sorted(ART.glob('design-rev-*.json'))[-1].name+').',
 json.dumps(counts,ensure_ascii=False)+'\n\n신규 판단·API 검사와 기존 연결/복구/원문 검사 통과. 작업 통합 뒤 같은 파일·pin으로 실제 API 소비자를 재확인했다. 확대277검사에서 최초55실패 중40은 수정 전133검사에서도 같은 ID로 재현됐다. 신규15실패는 정책 미제공 객체 처리 한 지점을 고쳤다. 기존40은 별도 미해결 이력이며 통과로 포함하지 않는다. [대조](artifacts/baseline-failure-comparison.json).',
 '최초 단위24검사 통과 뒤 실제 API에서 저장 스키마 누락과 충돌 ID/답변 주장 ID 충돌을 재현했다. 소비자 스키마·합성 ID 공간을 고치고 실패 기록을 보존했다. 후속 검사에서 생략·수정·철회·해결/재개·부분 원문·원문변조·권한·stale·중복·재개·수정 실패·출력 길이 중단을 확인했다.',
 '실제 외부 LLM 호출0. 정상 합성 API는 요청 이해1 + 기존 원문/행동 판단4 + 기존 최종 검토1 =6회다. 판단 전용 호출0. 순차 검사·주소공간3GiB 상한, 가용 RAM약11GiB·테스트RSS약0.3GiB를 관찰했다. 실제 입력 토큰·지연·정답률 미측정.',
 '새 원문 묶음 판단과 다음 행동을 기존 compact READ 선택 호출에 결속한다. 생략은 유지, SET/KEEP/WITHDRAW는 이유·원문에 결속한 새 판본이다. 부족과 충돌은 독립 ID로 유지하며 양쪽 근거 없이 충돌 해결을 인정하지 않는다. 최종 ASSESS는 모든 판단·부족·충돌을 다시 확인하고 실제 claim과 근거를 연결한다. 불확실성은 제한 답변으로 표시할 수 있다.',
 '\n\n'.join(result['limitations']),
 '검증한 변경만 작업 코드에 통합하고 read_judgment=true로 활성화했다. 이 모드에서는2개 이하 연결도 자동 확보하지 않고 판단 후 선택하며 상위 자체 본문 문맥은 유지한다. service.py의 선택 MAIN102 포인터는 불변이다. 코드상 API 검증과 실행 중 선택 릴리스·GENOS 현장 적용은 다르다. [통합·복원](artifacts/working-integration.json).',
 '재현: .venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1033/run_contracts.py <snapshot test paths> -q. 작업 코드 검증은 --working. 각 실행은 동결 파일/runner 해시를 먼저 확인한다. validate --final과 graph 결과는 final-checks.json.']
assert len(parts)==len(ADR_HEADINGS)
(ADR/'README.md').write_text('---'+front+'---\n\n# 원문 읽기 판단 누적과 최종 검토\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(ADR_HEADINGS,parts)))
(ADR/'실험/README.md').write_text('# 구현 계약 검사\n\n실제 질문·모델 실행 없이 합성 상태/원문/실제 API 경로를 검사했다. 판단 전용 호출은 없다. 결과와 실패 이력은 ../artifacts/ 에 보존했다.\n')
(ADR/'RESULT.txt').write_text('원문 읽기 판단·누적 이력·최종 검토 구현 및 작업 코드 통합 완료.\n\n'
 '기존 다음 행동 LLM 응답에 원문별 판단, 이유, 부족, 다음 행동과 연결한 판단 ID를 추가했다. 판단 전용 LLM 호출은 추가하지 않았다.\n'
 '기존 판단 생략은 유지. 수정·철회는 이유와 근거를 요구하고 이전 판본을 보존한다. 부족·충돌은 독립 상태이며 빈 목록이나 다른 판단으로 삭제되지 않는다.\n'
 '최종 검토는 사용·조건부·미해결·미사용과 그 이유를 모든 판단에 남기며 부족·충돌도 모두 처리한다. 중요한 미확인은 제한 답변에 표시한다. 충돌 해결에는 양쪽 원문이 필요하다.\n'
 'read_judgment 모드에서 연결 대상 자동 확보를 끄고 다음 행동 선택으로 연결했다. 상위 자체 본문 문맥은 유지한다.\n\n'
 f"신규 {counts[logs[0]]} + 기존 회귀 {counts[logs[1]]} = {result['unique_candidate_tests']} 검사 통과. 작업 통합 후 {counts[logs[2]]} 검사 통과. 후보·작업 {len(f['files'])}파일 해시 일치.\n"
 '실제 외부 모델 호출0. 합성 정상 API6회, 판단 전용 호출0. 실제 질문의 판단 정확도·토큰·지연 개선은 미검증이다. 의미 충돌 전부를 코드가 탐지하는 것은 아니다.\n'
 '확대 검사에서 기존 실패40건을 수정 전 코드에서도 재현했다. 해당 이력은 별도 보존하며 이번 통과 수에 포함하지 않는다.\n'
 '선택 MAIN102와 GENOS 변경 없음. 복원: artifacts/working-integration.json 및 working-before.tar.gz.\n')
p=ROOT/'04_EXPERIMENTS/ADR/README.md';t=p.read_text();link='ADR-1033-read-judgment-continuity/README.md'
assert link not in t
p.write_text(t.replace('# ADR workspace\n','# ADR workspace\n- [ADR1033 원문 판단 누적·최종 검토]('+link+') — 작업 구현·합성 API 검증, MAIN/GENOS 불변.\n'))
print(json.dumps({'tests':counts,'files':len(f['files'])},ensure_ascii=False))
