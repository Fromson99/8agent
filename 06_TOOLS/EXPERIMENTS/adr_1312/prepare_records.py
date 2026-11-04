from common import *
m=read(ADR/'실험/manifest.json');m['llm_policy']['provider_override'].update(path=str((DES/'nearai-only.json').relative_to(ROOT)),sha256=sha(DES/'nearai-only.json'));put(ADR/'실험/manifest.json',m)
sections=[('결정 요약','현재는 사전 설계·구현·검사 단계다. 검증된 FINISH를 기존 최종 ASSESS에 넘기는 조건만 추가하며 답변 충분성을 서버가 승인하지 않는다.'),('문제와 변경 전 구조','1311로 동등 재생120.774→31.691초를 확인했다. 별도로 FINISH 뒤 감독이 주제 밖 연결조사를 확대하여 기존369에서2호출24.537초를 추가했다.'),('가설과 사전 판정 기준','필수 원문 확보·원래 요구 전부ANSWERABLE·열린 부족/충돌/미검토 원문 없음일 때 FINISH를 유지한다. 원문/ACL/wire 불일치나 새 회귀는 실패. 실제 기준3개가 질문별 유지되어야 한다.'),('실험 설계','성능수정 동일 before/after 각517파일, after만 감독1모듈+pin 변경. before369→after369→after365 각1회, 재실행 없음. 기존정답은 채점에만 사용한다.'),('데이터·모델·재현성','기존 SQLite 원문과 격리 SQLite 기록. Qwen3.8-27b/NearAI FP8 only/추론none/fallback0/ontologyOFF. 최종검토표OFF는 시험만 유지. 셀40/전체60물리호출 상한, UNKNOWN 즉시전체중단, 자원상한 유지.'),('결과','아직 실제 모델 미실행. 동결 후 계약/실제API로 검증하고 원응답·실패를 전부 보존한다.'),('사례별 오류 분석','새 fixture 또는 기존 실패는 원본과 전후 비교를 남긴다. 예외를 성공으로 바꾸거나 같은셀을 재호출하지 않는다.'),('비용·지연·회수 규모','총HTTP요청시간/물리모델시간/잔여시간/실제SELECT 관측을 분리한다. 잔여≠DB시간이며 순차모델1쌍의 확률적 차이를 일반 개선율로 확대하지 않는다.'),('해석','기존 source_goal_control이 먼저 필수 원문을 처리한다. 검증된 현재 read_judgment 상태에서 새원문 미검토·열린need/conflict를 확인하고 UNKNOWN/halt/pagingpending을 우회하지 않는다. 역사적 필요 장부는 최종 판단에 유지한다.'),('한계와 일반화 가능 범위','두 알려진 질문·단회이며 법률품질 인증이나 Oracle corpus 속도평가가 아니다. 초기metadata중복 로딩은 별도로 남는다.'),('운영 결정·롤백 조건','성공 계약 확인 후 검증한 supervisor 한 모듈만 작업에 통합할 수 있다. 후보 검토표OFF를 기본설정에 복사하지 않는다. MAIN136/Gold바인딩/DB/DDL/배포는 변경하지 않는다.'),('재현 명령','setup.py/edit.py→freeze.py→check.py→live.py/run_all.py→audit.py/ledger.py→원문대조→작업통합/검증→보관→최종ADR검사.')]
p=ADR/'README.md';front=p.read_text().split('\n---\n',1)[0]+'\n---\n';p.write_text(front+'\n# FINISH 판단 직행과 실제 시험\n\n'+'\n\n'.join(f'## {i}. {t}\n\n{b}' for i,(t,b) in enumerate(sections,1))+'\n')
for q in m['questions']:
 c=next(c for c in read(DES/'cases.json') if c['id']==q['case_id'])
 (ADR/'실험'/q['file']).write_text(f'''# {c['id']}

## 1. 실행 메타

run-001, 예정 arm: {c['arms']}. 셀1회, 실패 재시도0.

## 2. 사용자 질문 원문

{c['question']}

## 3. 기준답변 — 채점 전용

동일 artifact의 design/scoring-only-originals.json 원문·좌표를 최종 주장과 대조한다. 정답은 제품 입력에 주입하지 않는다.

## 4. 제품 입력을 구성한 원값

### 회수·탈락 단계 원장 — run·arm별

각 실제 셀에서 확보한 evidence_span과 실제 wire 전달만 별도 계수한다. 전체 원문 corpus의 해당 문서조문 inventory를 기준으로 원장 작성 예정.

## 5. 제품 모델 호출 — run·arm별 실제 원문

artifacts/live/{c['id']}-<arm>/raw 및 calls.json에 전체요청/응답/보고사용량을 보존한다. 현재미실행.

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

동일셀 canonical에 단계별 입력/출력과 실패 저장. 새judge0.

## 7. 채점 호출과 반복 판정

채점모델0; 원문 직접대조로 핵심3규칙·조건·수치·주체·대상 방향·인용을 확인한다.

## 8. 사례 최종 판정

현재미실행. 오류/미실행은 성공시간 평균에서 제외하며 따로기록한다.
''')
(ADR/'실험/README.md').write_text('# 질문 인덱스\n\n'+'\n'.join(f"- [{q['case_id']}]({q['file']})" for q in m['questions'])+'\n')
print('Prospective records prepared')
