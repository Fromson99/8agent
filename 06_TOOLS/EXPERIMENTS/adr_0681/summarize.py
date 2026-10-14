"""Accept only unchanged evaluated bytes and complete prespecified contracts."""
from pathlib import Path
import json,hashlib,xml.etree.ElementTree as E
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0681-session-runtime-no-user-wiki-signing';D=A/'artifacts/design';O=A/'artifacts/run-001'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def suite(name):
 tree=E.parse(O/name).getroot();cases=list(tree.iter('testcase'))
 return {'artifact':str((O/name).relative_to(R)),'sha256':sha(O/name),'tests':len(cases),'failures':[x.get('name') for x in cases if x.find('failure') is not None or x.find('error') is not None]}
freeze=read(D/'freeze.json');code=R/freeze['code_root']
for f,h in freeze['files'].items():assert sha(R/f)==h,f
for f,h in freeze['serving_files'].items():assert sha(code/f)==h,f
primary=suite('session.xml');baseline=suite('baseline.xml');reg=suite('regression-session-r2.xml');base_reg=suite('regression-baseline-r2.xml')
checks={'all_new_session_contracts_pass':primary['tests']==30 and not primary['failures'],'same_88_regressions_pass':reg['tests']==base_reg['tests']==88 and not reg['failures'] and not base_reg['failures'],'frozen_serving_inventory_unchanged':True,'active_parent_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(D/'baseline.json')['pointer_sha256'],'no_model_calls_or_quality_claim':True}
result={'schema_version':'session-contract-audit-v1','strict_success':all(checks.values()),'checks':checks,'primary':primary,'baseline_new_contracts':baseline,'regression_candidate':reg,'regression_baseline':base_reg,'model_calls':0,'usage':{'input_tokens':0,'output_tokens':0,'cost_usd':0},'quality_certified':False,'limitations':['Synthetic state/ingress/repository contracts, not semantic quality or field certification','Initial shared collection was invalid due historical ADR conftest replacing module paths; logs preserved and no-conftest runner fixed before valid regression calls','Unrelated pending latency and router files are not promoted or overwritten','Old signature behavior tests are intentionally outside the new unsigned contract; original records remain intact']}
assert result['strict_success'];put(O/'result.json',result)
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(O/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','contract_tests':22,'passed':0,'regression_tests':88,'regression_passed':88},'session':{'status':'complete','contract_tests':30,'passed':30,'regression_tests':88,'regression_passed':88}},comparisons=[{'baseline':'baseline','candidate':'session','metric':'No regressions among 88 unchanged contracts; removal/session criteria pass','baseline_value':88,'candidate_value':88}],judge_disagreements=None,usage=result['usage'],latency={'measurement':'Pytest timings in XML; not service latency'},error_taxonomy=['Historical conftest collection interference (runner only, preserved)'])
put(A/'실험/manifest.json',m)
meta=f'''---
adr_id: ADR-0681
title: 세션 멀티턴의 user_wiki와 별도 signing 제거
status: Accepted
decision_date: 2026-10-07
phase: audit
in_sample: false
decision_eligible: true
main_wiring: promotion-candidate
created_at: {m['reservation']['created_at']}
updated_at: {m['reservation']['updated_at']}
owner: Codex
work_status: completed
---
'''
(A/'README.md').write_text(meta+'''\n# 세션 멀티턴 유지, user_wiki·추가 HMAC 제거

사용자 지시대로 user_wiki 생성·조회·모델 context와 개인 질문 이력의 자동 입력을 제거한다. 별도 앱 signing 발급·검증·환경키 의존성을 제거하며 기존 플랫폼/API 접근 경계를 사용한다. 식별자는 저장 분할·세션 소유자·문서 선택을 위한 값이며 인증 권한이 아니다. 외부 모델 공개 범위와 서버 AD 진입 검사를 유지한다.

현재 선택된 ADR0680의 generation44와 동일 데이터·검색·판단 코드를 기준으로 scope를 동결하고 후보 snapshot에서 구현했다. 신규 모의 계약30개(세션 selector 검증·정정·확인·shortcut 기록·법률 위키 생성·삭제된 조회·직접 JSON/SSE), 동일 회귀88개(조사 완료·인용·오류 경계·shortcut와 wiki 컴파일·재구축·복구)를 검증했다. 후보118개 통과, 기존 MAIN의 동일 회귀88개 통과. 기존 MAIN은 새로운 unsigned/removal 계약22개를 지원하지 않는다. API 함수명 변경으로 실패한 경우도 포함하므로 이 수치는 품질 향상률이 아니다. 외부 LLM 호출0회·토큰0·비용0, 법률 정답률·성능 향상·현장 품질 인증을 주장하지 않는다.

현행 shortcut DB와 legal_wiki compiler는 그대로 유지하며 개인 위키 파일의 과거 기록은 삭제하지 않는다. 서명 필드는 구 입력 호환을 위해 허용되지만 무시·제거되며 키 검사나 인증 grant로 사용하지 않는다. 사용자·세션의 전체 식별자를 해시하는 기존 방식과 문서 선택·세션 충돌 검사를 보존한다. 새 세션에 기존 질문 이력을 자동 주입하지 않는다. AD에서 명시적으로 원기록을 관리하거나 사건 ID로 연결하는 기능은 유지한다.

병행 작업의 미선택 latency/engine 변경은 후보에 섞지 않았고 작업 파일을 덮어쓰지 않는다. 현재 no-socket workflow 변경은 그대로 이어서 통합했다. 최초 회귀 수집의 과거 ADR conftest 간섭 로그를 보존했고 일반 단위 테스트 runner만 고쳐 같은 동결 제품 코드로 비교했다. 신규 모델 실험이나 소급 판정 기준 변경은 없다.

- [사전 기준·현재 MAIN binding](artifacts/design/criteria.json)
- [고정 서빙 inventory·원복 기준](artifacts/design/release-rebase.json)
- [실제 검사 결과와 한계](artifacts/run-001/result.json)
- [작업 시작·완료의 append-only 상태와 부모 arm](실험/manifest.json)

승격은 stable rag_main_promotion.py의 hash 고정 prepare/apply --confirm-main을 사용한다. 이전 포인터는 stable rollback --confirm-main으로, 이번 변경 파일은 저장된 작업 백업과 hash 검사로 원복한다. DB·완료 release·실험 이력은 보존한다. 심각한 scope/state/hash/source 무결성 문제 또는 세션/shortcut/legal_wiki 회귀는 롤백 조건이다. 로컬 MAIN과 GENOS 배포·내부 모델 현장 검증은 별도 상태다.

재현: `.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0681/run_contracts.py <고정 code root> <계약 파일> --noconftest`. 질문별 법률 채점은 수행하지 않았고 이 감사는 새 모의 상태/API 계약과 회귀 검사에 한정된다.
''')
(A/'실험/README.md').write_text('''# ADR-0681 계약 감사

질문별 실제 LLM 호출·법률 채점을 수행하지 않았다. 사전에 고정한 새 모의 상태/API 계약과 유지해야 할 기존 회귀를 동결 코드로 확인했다.
선점·부모 ADR0680 integrated·실행·완료 상태는 [manifest.json](manifest.json)의 append-only reservation과 lineage를 따른다.
신규 후보30개와 동일 후보/기준 회귀88개 통과. 원 실행 로그·검사별 XML과 집계는 [원결과](../artifacts/run-001/result.json)에 보존한다.
모델 호출·토큰·비용0. 검색 정책 변경과 법률 질의 gold 채점이 없으므로 retrieval stage ledger·judge 불일치는 해당 없다.
''')
files=[D/'criteria.json',D/'freeze.json',D/'release-rebase.json',D/'working-drift.json',D/'upstream-rebind.json',O/'result.json',*sorted(O.glob('*.xml')),*sorted(O.glob('*.log'))]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0681','created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Prespecified session/removal contract and regression audit','contains_raw_prompts_and_outputs':False} for p in files]})
print('Accepted:',primary['tests']+reg['tests'],'candidate contracts')
