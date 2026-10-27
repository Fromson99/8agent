from common import *
from copy import deepcopy
from datetime import datetime,timezone
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1048-ontology-mvp-r10-restart'
old=read(prior/'실험/manifest.json');m=read(ADR/'실험/manifest.json')
m['design']=deepcopy(old['design']);d=m['design']
d['code_isolation']['candidates']=[]
d['hypothesis']+=' Operational hypothesis: an explicit same-model FP8 provider chain completes requests rejected by the prior shared pool without resetting budgets or changing evidence.'
d['operational_success_criteria']='Known pre-generation upstream429 switches to the next approved provider, preserving exact messages/schema/reasoning, physical40 and deadline1800. Record all attempted providers. No hidden retries; no automatic cell replay.'
d['provider_policy']=read(ART/'provider-authorization.json')
d['live_execution_gate']='User-approved provider-only failover. Run after candidate/API checks and exact freeze. No MAIN promotion.'
d['criteria_frozen_before_run']=False
m['dataset']=deepcopy(old['dataset']);m['dataset']['frozen_source']=str((ART/'dataset-freeze-r1.json').relative_to(ROOT))
m['lineage']['hypothesis_delta']='Preserve r10 input/output optimization and ontology37x3 conditions; add explicit same-model FP8 provider failover only on identified HTTP429.'
m['llm_policy']['provider_exception']=deepcopy(d['provider_policy'])
m['runs'][0].update(selection_rule='All37 approved cases × A0/A1/A2, inherited six counterbalanced orders; fresh sequential cells; never replay a started cell',artifact_path=str((ART/'matrix-summary.json').relative_to(ROOT)),sha256='PENDING')
m['retrieval_accounting']=deepcopy(old['retrieval_accounting'])
m['retrieval_accounting']['stage_ledger'].update(artifact_path=str((ART/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING')
m['questions']=deepcopy(old['questions'])
for q in m['questions']:
 for key,value in list(q.items()):
  if isinstance(value,str):q[key]=value.replace('ADR-1048-ontology-mvp-r10-restart','ADR-1049-ontology-mvp-provider-failover')
 # Reporting regenerates all bodies from this experiment before observation.
 path=ROOT/q['path'] if 'path' in q else None
 if path is not None:
  path.parent.mkdir(parents=True,exist_ok=True);path.write_text('Execution pending; populated by frozen reporter.\n')
# Some standard versions use relative question paths.
for path in (prior/'실험').glob('질문-*.md'):
 dest=ADR/'실험'/path.name
 if not dest.exists():dest.write_text('Execution pending; populated by frozen reporter.\n')
save(ADR/'실험/manifest.json',m)
readme=ADR/'README.md';front=readme.read_text().split('---',2)[1]
body='''
# ADR-1049: 동일 모델 복수 제공자 전환과 MVP37×3

## 1. 결정 요약
사용자 승인에 따라 Parasail → Reka → Wafer → Mancer 2 → CoreWeave 순서로 같은 Qwen3.8 FP8을 사용한다. 격리 후보와 새111셀 실행이며 MAIN은 변경하지 않는다. 현재는 실행 전 검증 단계다.

## 2. 문제와 변경 전 구조
ADR1047·1048은 Parasail 공유 풀429로 중단됐다. 원본 실패 이력과 비용은 해당 ADR에 보존한다. 미완료 실행을 부모 complete arm이나 새 결과로 재사용하지 않는다.

## 3. 가설과 사전 판정 기준
기존 온톨로지 필수근거 확보·전달·인용 및34문항 의미평가 기준을 유지한다. 같은 입력으로 알려진 제공자429를 복구하되 원문·권한·상태·호출 예산을 보존한다. 제공자별 분포가 달라지면 순수한 동일 제공자 비교로 해석하지 않는다. 상세 기준은 실험 manifest와 design-freeze에 동결한다.

## 4. 실험 설계
A0 온톨로지 없음, A1 승인31묶음 조립 전 전달, A2 동일 정보의 결정적 컴파일 전달. 기존37문항·조건 순서 유지,111셀 순차 실행. 모든 조건에 같은 제공자 정책을 적용한다. 각 셀은 Parasail에서 시작하며 알려진429 때 다음 제공자로 이동하고 이후 단계도 그 제공자를 사용한다.

## 5. 데이터·모델·재현성
기존1536문서, CM27·FSC7·근거만3문항, 현행 FSC 기준답변을 유지한다. 미확보 두 법률은 추가하지 않으며 별도 상태를 보존한다. 제품에 기준답변을 노출하지 않는다. Qwen3.8 FP8, reasoning none, 출력 상한 없음. 최대40물리호출·1024도구·1800초, 평가문항당21물리호출. 실제 응답 제공자까지 검증한다. 후보 공통 클라이언트만 범위 한정 정책을 읽으며 루트 정책·MAIN은 보존한다.

## 6. 결과
실행 전. 결과 확인 후 artifacts/RESULT.md와 matrix-summary.json에 기록한다. 실제 모의/API 검사 결과와 외부111셀 결과는 구분한다.

## 7. 사례별 오류 분석
제품 gateway가 재시도를 담당하며 클라이언트의 숨은 재시도는0회다. 오류 본문이 지정한 해당 제공자의 생성 전 HTTP429 거절만 다음 제공자로 전환한다. 전환은 셀당최대4회, 각 전송은40회 예산에 포함한다. 같은 모델 입력을 다시 보내며 실패기록·요청해시를 보존한다. Retry-After 없으면1초,1~30초만 허용한다. 알려지지 않은 수신 상태,500,네트워크,부분출력,형식·근거·권한·해시·상태 오류는 제공자 전환으로 우회하지 않는다. 마지막 제공자 거절 또는 미분류 운영 오류는 기록 후 전체 중단한다. 오프라인 평가기는 별도21회 예산 안에서 동일 정책을 사용한다.

## 8. 비용·지연·회수 규모
모든 물리요청과 실제 제공자별 상태·토큰·비용을 집계한다. 실패 응답에 사용량이 없으면 미확인으로 남긴다. provider-summary.json과 원본 call별 기록이 정본이다. 제공자별 가격이 달라질 수 있으며 가격 추정치를 실제 비용으로 쓰지 않는다.

## 9. 해석
이 실험은 제공자 전환을 포함한 운영 정책 아래 온톨로지 비교다. 제공자 혼합이 다른 조건끼리의 지연·비용·품질 차이를 온톨로지만의 효과로 단정하지 않는다.

## 10. 한계와 일반화 가능 범위
probe/in_sample=true/decision_eligible=false. 알려진37문항 및 같은 모델 오프라인평가. 실제 제공자의 구조화 출력 호환성은 메타데이터 확인과 모의검사만으로 완료가 아니며 실호출로 관찰한다. GENOS 내부모델 결과로 일반화하지 않는다.

## 11. 운영 결정·롤백 조건
활성 MAIN103, 데이터 세대, GENOS, 전역 모델 정책은 변경하지 않는다. 제공자 전환 상태는 셀·freeze에 결속하고 이미 시작한 셀은 자동 재실행하지 않는다. 원문·권한·해시·상태 검증 실패와 예산·시간·RAM 한도를 보존한다. 모의 검증과 동결 후 새 실험을 실행한다.

## 12. 재현 명령
WSL 저장소에서 .venv/bin/python -B 06_TOOLS/EXPERIMENTS/adr_1049/run_matrix.py --inspect-only로 동결을 검사한다. 실행은 run_matrix.py, 제품 완료 후 evaluate_matrix.py --execute, 보고는 report_results.py --write 및 provider_report.py다. 중단된 셀과 sticky stop을 삭제하여 우회하지 않는다. 정확한 실행·정책·코드·테스트·입력 해시는 design-freeze.json을 따른다.
'''
readme.write_text('---'+front+'---\n'+body)
print('Pre-execution design saved; no model calls.')
