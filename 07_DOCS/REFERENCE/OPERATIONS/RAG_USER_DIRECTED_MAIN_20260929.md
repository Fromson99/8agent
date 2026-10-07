# 사용자 지시 RAG 통합 MAIN — 2026-09-29

이번 통합은 사용자 지시 `실험 아직 돌리고 있는 다른 RAG 업데이트도 그냥 main에 반영하고 삼성메일로 보내라`에 따른다.
완료된 품질 실험의 자동 승격이 아니다. `quality_certified=false`, `USER_DIRECTED_CUTOVER`를 보존한다.
ADR0555의 Qwen 비교는 HTTP 이전 어댑터 오류로 중단되어 개선 결과가 없다. 동결 후보와 실패 이력은 바꾸지 않는다.

## 적용한 제품 경로

- 법령명·등록 약칭과 저장 조문 번호/표제가 유일하면 해당 원문을 먼저 READ한다.
  전체 지정 원문이 질문에 충분하면 작성하고, 부족·누락·문맥 한도 초과이면 fulltext로 확장한다.
- ADR0555 `catalogue-router`의 `rev-002` 제품 코드만 기존 구조 우선 경로와 병합한다.
  법률 검색, 허용 자료 현황/목차 탐색, 인사·역할 안내, 비법률 범위 안내를 구분한다.
  현황은 실제 browse/title/outline 관찰을 사용하고 내규는 저장 category로 한정한다.
  이미 인식하는 단순 목록 질문은 기존 모델 미사용 경로를 유지한다.
- GENOS 환경의 v5 모델 결속도 `bounded_source_selection_enabled=true`로 연결한다.
  이전 환경 기본은 false여서 후보 구현 파일만 복사하면 현장에서 선택되지 않았다.
  모델 도구 탐색 프로필은 호환용으로 보존하고 구조 원문 사전 읽기도 유지한다.
- PeCab 1.0.8의 공개 145문서/26,599 원문 색인을 가진 새 데이터 세대를 선택한다.
  원문·용어집·정의·명시 참조·compact navigation은 같은 검증 바이트다.
  내부 전체 검색은 GENOS에서 동일 `genos_fulltext_repair.py --rebuild`로 새 세대를 생성해야 한다.
- 기존 답변 생성 SSE, 판단·짧은 사유 표시, fulltext 위치 최적화와 최종 검토 생략도 현재 코드에 함께 결속한다.
  워크플로우 Python은 별도 편집기에 교체해야 한다.

연결은 `service → Pipeline → ServingLegalAgent → BoundedSourceSession`이다.
외부 Qwen 실험 어댑터·모델 설정은 제품에 복사하지 않는다. 로컬 공개 모델 설정과 GENOS 내부 모델 설정은 각각 유지한다.
감사 기록은 `09_ARTIFACTS/AUDITS/20260929-rag-user-directed-main/`에 둔다.

## 상태와 현장 인계

로컬 MAIN은 새 immutable 릴리스 `legal-agent-structure-catalogue-pecab-20260929-r1`로 전환한다.
코드·manifest·선택 세대·계약 검사·사용자 지시 영수증을 결속하며 이전 릴리스는 보존한다.
Git의 `main` 브랜치 병합과 GENOS 리비전 배포는 이 전환과 별개다.

코드 ZIP과 실행 TXT는 기존 `~/DEV`를 실제 Git root로 해석한 뒤 백업·적용한다.
첫 단계부터 로그/실패 파일을 남기며 재실행은 기존 해시와 영수증을 확인한다.
색인 구축은 내부 전체 범위를 사용하고, 이미 검증된 complete PeCab 세대는 재사용한다.
원본 세대·공유 receipt·CURRENT를 수정하지 않는다.
실제 checkout에서 diff 검사·commit 후 `genos_release_gate.py`로 ZIP 전체 파일과 generation을 확인하고,
통과한 commit을 push하여 같은 generation을 선택하는 새 코드서빙 리비전을 배포한다.
배포와 워크플로우 저장·배포 이후에는 워크플로우 테스트 화면에서만 질문을 확인한다.

코드/세대 gate는 모델 분류 정확도나 법률 정답률을 인증하지 않는다.
실제 GENOS 내부 자료 검색·SSE 지원·응답 속도·새 리비전·워크플로우 성공은 현장 미확인이다.
복구는 기록된 코드 백업과 PeCab으로 검증한 세대 쌍을 사용한다. 과거 Kiwi 파일은 감사 근거로 보존한다.
