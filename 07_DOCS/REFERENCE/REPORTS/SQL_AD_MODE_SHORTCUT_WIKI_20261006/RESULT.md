# 검증과 배선 결과

- 로컬 MAIN: **sql-ad-mode-v6-20261006-r1**, generation **41**. hash 고정 prepare/apply와 실제 활성 서비스 재검사 완료.
- 정식 구조·회귀 검사 **131개 통과**, 전체 감사 **34.598초**. 실제 모델 호출 0회. 모델 대역을 사용한 계약 검사는 실제 모델 품질 결과가 아니다.
- 배포 복사본 **253개 파일**, **30개 엔진**, **4438개 의존 edge**의 해시·파일 존재 확인.
- AD모드 안에서 법률 application 초기화 호출을 금지하는 검사, 실제 chat/workflow 어댑터의 여러 턴, SQL 상태/오류/복구 검사 통과.
- 일반 경로 health·검색·모델 없는 기록 저장 통과. AD 밖의 관리 API는 403. 실제 활성 경로의 AD 진입·도움말·현재 상태·목록·종료 통과.
- ADR-0657 final validation OK. 전체 과거 ADR graph 검사는 이전 ADR-0541/0542/0622/0638/0158 등의 오류를 보고하며, 이를 이번 작업에서 수정하거나 전체 graph 통과로 보고하지 않는다.
- GENOS 현장, 내부 모델 생성 품질, 상주 예약 시각 실행, 데이터 볼륨 유지: **미확인**. 이번 로컬 MAIN은 전체 MAIN의 서빙 부분이며 데이터 재구축·Git main 병합·GENOS 배포 완료를 뜻하지 않는다.

## 전달 범위

마지막 전체 RAG 메일은 2026-10-02의 R4(메일 ID 1a0fbcb36786bd26)다. 이를 기준으로 현재 유지되는 실행 코드 전체와 이번 AD 기능을 R5 누적본으로 보낸다. 원문·DB·인증키·JavaScript·과거 인계 산출물은 코드 첨부에서 제외한다. 기존 동결 코드 세대는 원래 바이트를 유지한다. 패키지별 변경 목록·설치/원복 검사·메일 영수증은 `08_DEPLOYMENT/GENOS/handoffs/sql_ad_cumulative_20261006_r5`에 남긴다.

## 확인 가능한 근거

- ADR: `04_EXPERIMENTS/ADR/ADR-0657-sql-ad-mode-control`
- 정식 결과: `artifacts/run-001/result.json`, `contracts.xml`, `ad-transcript.json`
- 실제 활성 확인: `artifacts/main-smoke.json`, `active-ad-transcript.json`
- 작업 코드 백업/설치: `artifacts/working-install-plan.json`, `working-install-receipt.json`
- 실제 릴리스: `08_DEPLOYMENT/RELEASES/sql-ad-mode-v6-20261006-r1/release.json`

설정·본문·오류를 모두 TEXT 한 덩어리로 저장하지 않는다. 검색·상태·관계·시간·선택은 SQL 열과 인덱스다. 상세 원문/불변 payload 및 응답 스냅샷의 JSON/TEXT 사용은 의도적으로 남긴다.
