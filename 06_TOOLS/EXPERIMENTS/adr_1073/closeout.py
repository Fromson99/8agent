from pathlib import Path
import hashlib,json,re
from datetime import datetime,timezone
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1073-navigation-sql-main-qualification';D=A/'artifacts/design-r3'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
result=read(A/'artifacts/run-003/result.json');assert result['strict_success'] and all(result['checks'].values())
m=read(A/'실험/manifest.json');m['runs'][-1].update(status='complete',sha256=sha(A/'artifacts/run-003/result.json'),success_criteria_met=True)
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','mechanical_cases':628,'role':'Immutable MAIN103 comparator'},'optimized':{'status':'complete','strict_success':True,'mechanical_cases':628,'mechanical_mismatches':0,'supplemental_tests':11}},comparisons=[{'pair':['baseline','optimized'],'mechanical_equivalent':628,'mechanical_mismatch':0,'legal_accuracy':'not_measured'}],usage={'product_model_calls':0,'offline_evaluator_calls':0,'input_tokens':0,'output_tokens':0},latency={'audit_wall_seconds':result['wall_seconds'],'speed_effect':'not measured by this qualification'},error_taxonomy=[{'kind':'measurement_fixture_main_namespace','runs':['run-001'],'product_failure':False},{'kind':'fixture_expected_null_not_in','runs':['run-002'],'product_failure':False}],main_wiring='promotion-candidate',quality_certified=False,limitations=result['limitations'])
put(A/'실험/manifest.json',m)
old=(A/'README.md').read_text();meta=old.split('---',2)[1]
for key,value in [('status','Accepted'),('main_wiring','promotion-candidate'),('decision_eligible','true'),('in_sample','false')]:meta=re.sub(r'(?m)^'+key+r':.*$',key+': '+value,meta)
body='''
# ADR1073 — 211초 원인 SQL 수정의 MAIN103 결합 검증

## 1. 결정 요약

SQL 두 수정의 결정론적 동등성 범위에서 Accepted, promotion-candidate다. MAIN103의420개 서빙 파일 중 제품2개와 hash pin31개만 변경했다. 새로운 사전 고정 전수628조합에서 원래 MAIN103 결과/오류가 전부 일치했고, 기존11검사도 통과했다. 법률 답변 품질 또는 GENOS 속도 인증이 아니다. 실제 MAIN 적용과 적용 뒤 서비스 검사는 별도 실행 기록에 남긴다.

## 2. 문제와 변경 전 구조

정의에서 명시 참조를 찾을 때 전체 reference VIEW를 LEFT JOIN으로 먼저 구성하고, TEMP 권한뷰가 전체 ID 목록을 반복 조회했다. ADR1070~1072의 실제211초 대응 재현은 원인을 밝힌 기존 근거다. 그 알려진 질문을 새로운 holdout으로 다시 이름 붙이지 않는다. 이 ADR은 선택 MAIN103에 두 SQL 변경만 결합할 때의 별도 전수 기계 계약을 검증한다.

## 3. 가설과 사전 판정 기준

[최초 고정 기준](artifacts/design/criteria.json)의628개 조합 전체에서 결과·오류·권한·입력/DB 불변성·정렬이 같고, compact 조회가 ID색인을 사용하며,420개 서빙 파일 중 허용된2개와31핀 외에는 바뀌지 않아야 한다. 하나라도 불일치하면 승격을 막는다. 기준·제품 코드·case 집합은 세 실행 사이에 변경하지 않았다.

## 4. 실험 설계

| arm | 구현 | 평가 |
|---|---|---|
| baseline | 선택 MAIN103의 원래 두 모듈 | 명시적 불변 경로로 로드 |
| optimized | MAIN103+두 SQL 수정 | 동일 생성 fixture에서 실행 |

권한 행렬512개는 table/compact, 정의·참조의 visible/hidden/missing/null, endpoint4종, 중복1/2개, 순서2종의 전수곱이다. 정의 검증100개는25정상/오류 종류×저장구조2×순서2다. 빈 연결·개수·테이블 부재16개를 추가한다. 기존11개는 별도 회귀 근거다. `in_sample=false`와 decision eligibility는 이 사전 정의한 유한 SQL 계약에만 해당하며 법률 질문 분리 평가를 뜻하지 않는다.

## 5. 데이터·모델·재현성

실제 법령 원문·대형 색인을 적재하지 않고 tiny 생성 SQLite만 사용했다. 제품/평가 모델 호출0, 네트워크 금지. 최종 후보 `sql-main-r3/rev-001`,420서빙파일+2회귀테스트. 데이터 generation, profile, 출력 상한 없음, 검색 정책, 모델/provider, 호출/도구/시간 예산은 선택 MAIN103과 동일하다. [동결과 재결속](artifacts/design-r3/freeze.json), [release rebase](artifacts/design-r3/release-rebase.json).

## 6. 결과

- 최종 run003:628/628 기계적 동등, 회귀0. 법률 정답률은 측정하지 않았다.
- 정의 정상/실패100개에서 원문·hash·판본·위치·span·권한·대상 오류의 유형/메시지와 정상 반환 내용 일치.
- 기존11검사 통과, compact EXPLAIN의 단건색인 사용과 whole reference materialization 부재 확인.
- 420서빙파일,9232엔진 dependency pin, 명시적 import경로 확인. DB/입력 변경0.
- 모든14개 strict checks 통과. [원시 행렬](artifacts/run-003/matrix.json), [결과](artifacts/run-003/result.json).

## 7. 사례별 오류 분석

run001은 첫 baseline에서 SQLite iterdump의 비한정 테이블 SELECT가 TEMP 권한뷰를 읽어 원본 변경으로 잘못 판정했다. run002는 NULL reference_id가 숨긴 endpoint에 있으면 기존 NOT IN의3값 논리로 전체 참조가 숨겨지는 기존 동작을 예상행에서 빠뜨렸다. 두 실패는 제품 수정 없이 측정장치와 기대행만 교정하고 새 run/candidate로 동결했다. [run001실패](artifacts/run-001/FAILED.json), [run002실패](artifacts/run-002/FAILED.json)를 보존했다. run003은 같은628조합을 모두 끝냈다. NULL행이 기존처럼 fail-closed되는 것까지 같음을 확인했으며 이 기존 현상을 이번 최적화에서 고치거나 숨기지 않았다.

## 8. 비용·지연·회수 규모

최종 감사 실행 약1.58초, peak RSS58,832KiB. 실제 서비스 지연·p95·법률 회수율은 대상 밖이다. 모델 비용/토큰/호출0. 실데이터 복제나 병렬 대형 작업0. 기존211초 대응구간91.6% 감소 수치는 ADR1070~1072의 동일 계측 결과이며 이 synthetic audit의 측정값이 아니다.

## 9. 해석

필요한 참조 ID를 먼저 좁히고 권한을 같은 TEMP뷰에 단건 EXISTS로 묻도록 바꿔도, 선언한 유한 계약에서는 반환 원문·순서·권한·실패 동작을 보존한다. 현재 MAIN103의 다른 기능을 승격에 섞지 않고 이 코드만 공식 준비/적용 절차에 전달할 수 있다.

## 10. 한계와 일반화 가능 범위

모든 가능한 SQLite/Oracle 데이터베이스나 잘못된 스키마를 열거한 증명이 아니다. reference ID의 기존 primary key 계약을 전제한다. 새로운 모델 판단, 온톨로지 효과, 전체 응답속도, GENOS 현장성능을 측정하지 않았다. MAIN103의 기존 품질 우회를 이 결과의 통과 근거로 사용하지 않았고 quality_gate_override=false인 새 qualification을 만든다. 전체 legal quality는 quality_certified=false다.

## 11. 운영 결정·롤백 조건

사용자가 MAIN 반영을 명시했다. 완료 source·결과·후보·rebase·정확한420파일을 결속해 stable rag_main_promotion prepare/apply --confirm-main으로 반영한다. 원문/권한/hash/상태/서빙 회귀가 있으면 새 activation receipt를 남겨 MAIN103 바이트로 복귀한다. 이 ADR 기록은 적용 뒤 promoted로 고치지 않고 별도 activation receipt와 실제 서비스 binding을 남긴다. GENOS 반입·배포·검증은 별도다.

## 12. 재현 명령

완료된 실험을 덮어쓰는 재실행은 금지한다. 새로운 재현은 새ADR에 같은 동결 파일을 결속한다. 이 실행의 단계는 `prepare.py`, `freeze.py`, `audit.py`, 실패 보존 후 `prepare_r2.py/freeze_r2.py/audit_r2.py`, 다시 실패 보존 후 `prepare_r3.py/freeze_r3.py/audit_r3.py`다. 소스는 `06_TOOLS/EXPERIMENTS/adr_1073/`에 있으며 각 실행은 자기 freeze에 runner hash를 기록했다.

검증: `.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-1073-navigation-sql-main-qualification --final`

원시 증거: [artifact manifest](artifacts/manifest.json). 새 MAIN 실행 검사는 완료 source와 별개로 인계 기록에 연결한다.
'''
(A/'README.md').write_text('---'+meta+'---\n'+body)
(A/'실험/README.md').write_text('# SQL 전수 계약 검증\n\n질문별 법률평가는 없다. MAIN103과 후보의628개 생성SQL/권한/실패 조합을 모두 비교했다.\n\n| 실행 | 결과 | 증거 |\n|---|---|---|\n|run001|baseline에서 측정장치 범위 오류로 중단|[실패](../artifacts/run-001/FAILED.json)|\n|run002|baseline의 NULL NOT IN 기대행 오류로 중단|[실패](../artifacts/run-002/FAILED.json)|\n|run003|628/628동등, 기존11통과|[결과](../artifacts/run-003/result.json)|\n\n기존 성능문제의 알려진 법률질문을 새 holdout으로 세지 않는다. [행렬 원값](../artifacts/run-003/matrix.json), [사전기준](../artifacts/design/criteria.json).\n')
paths=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json']
paths+=list((R/'06_TOOLS/EXPERIMENTS/adr_1073').glob('*.py'))
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1073','created_at':m['reservation']['created_at'],'updated_at':datetime.now(timezone.utc).isoformat(),'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Prospectively frozen SQL census, unchanged product bytes, raw failure or completed result','contains_raw_prompts_and_outputs':False} for p in sorted(paths)]})
index=R/'04_EXPERIMENTS/ADR/README.md';text=index.read_text();line='- [ADR1073 SQL 최적화 MAIN 결합 검증](ADR-1073-navigation-sql-main-qualification/README.md) — MAIN103+SQL2개·31핀, 독립628전수 조합 동등·11회귀 통과. 실제 MAIN 적용은 별도 receipt.\n\n'
if 'ADR-1073-navigation-sql-main-qualification/README.md' not in text:index.write_text(text.replace('# ADR workspace\n\n','# ADR workspace\n\n'+line,1))
print('Final source drafted; explicit scoped Accepted qualification, historical failures preserved')
